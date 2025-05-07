import re
import os
import discord
import asyncio
import aiohttp
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
WATCHED_CHANNEL_ID = int(os.getenv("WATCHED_CHANNEL_ID"))
FORWARD_CHANNEL_ID = int(os.getenv("FORWARD_CHANNEL_ID"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))

ROLE_ID = int(os.getenv("ROLE_ID"))
REVOKE_ROLE_ID = int(os.getenv("REVOKE_ROLE_ID"))

CHECK_INTERVAL = 60
KICK_TIME = 3600

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def remove_links(text):
    return re.sub(r'https?://\S+', '', text)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    bot.loop.create_task(check_members())

@bot.event
async def on_guild_channel_create(channel):
    await asyncio.sleep(2)
    messages = [message async for message in channel.history(limit=10)]
    for message in messages:
        if message.embeds:
            for embed in message.embeds:
                for field in embed.fields:
                    if "Пользователь" in field.name:
                        user_mention = field.value.strip()
                        user_id = int(user_mention.strip("<@!>"))
                        guild = bot.get_guild(GUILD_ID)
                        member = guild.get_member(user_id)
                        if member:
                            role = guild.get_role(ROLE_ID)
                            if role:
                                await member.add_roles(role)
                                print(f'Выдана роль {role.name} пользователю {member.name}')

async def check_members():
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Guild not found!")
        return
    
    while not bot.is_closed():
        for member in guild.members:
            if len(member.roles) == 1:
                join_duration = (discord.utils.utcnow() - member.joined_at).total_seconds()
                if join_duration >= KICK_TIME:
                    try:
                        await member.kick(reason="Отсутствие ролей")
                        print(f'Кикнут {member.name} за отсутствие ролей')
                    except Exception as e:
                        print(f'Ошибка при кике {member.name}: {e}')
        await asyncio.sleep(CHECK_INTERVAL)

@bot.event
async def on_message(message):
    if message.channel.id == WATCHED_CHANNEL_ID and message.embeds:
        embed = message.embeds[0]
        user_id = None
        reason = ""
        decision = ""
        
        for field in embed.fields:
            if "Пользователь" in field.name:
                user_mention = field.value.strip()
                user_id = int(user_mention.strip("<@!>"))
            if "Причина" in field.name:
                reason = field.value.strip()
            if "Принял" in field.name:
                decision = "accepted"
            if "Отклонил" in field.name:
                decision = "denied"
        
        if user_id:
            guild = bot.get_guild(GUILD_ID)
            member = guild.get_member(user_id)
            if member:
                if decision == "denied":
                    revoke_role = guild.get_role(REVOKE_ROLE_ID)
                    if revoke_role and revoke_role in member.roles:
                        await member.remove_roles(revoke_role)
                        print(f'Забрана роль {revoke_role.name} у пользователя {member.name}')
                    try:
                        await member.send(f'Причина отказа: {reason}')
                        print(f'Отправлено сообщение пользователю {member.name} с причиной отказа')
                    except Exception as e:
                        print(f'Ошибка при отправке сообщения пользователю {member.name}: {e}')
    
    if message.channel.id == FORWARD_CHANNEL_ID:
        await forward_to_telegram(message)

async def get_telegram_admins():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatAdministrators?chat_id={TELEGRAM_CHAT_ID}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return [f"@{admin['user']['username']}" for admin in data.get("result", []) if "username" in admin["user"] and not admin["user"].get("is_bot", False)]
            else:
                print(f"Ошибка при получении администраторов Telegram: {response.status}")
                return []

async def forward_to_telegram(message):
    admin_mentions = " ".join(await get_telegram_admins())
    clean_text = remove_links(message.content)
    text = f"{admin_mentions}\nСообщение от {message.author.name}:\n{clean_text}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            if response.status == 200:
                print("Сообщение успешно отправлено в Telegram с тегами администраторов")
            else:
                print(f"Ошибка при отправке в Telegram: {response.status}")

bot.run(TOKEN)
