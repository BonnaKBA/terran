import re
import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from collections import defaultdict
import logging

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
WATCHED_CHANNEL_ID = int(os.getenv("WATCHED_CHANNEL_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

CHECK_INTERVAL = 60
KICK_TIME = 3600

partial_embeds = defaultdict(list)  # user_id -> list of embeds


@bot.event
async def on_ready():
    logging.info("on_ready вызван")
    print("Бот запущен", flush=True)
    logging.info(f"Токен используется для: {bot.user}")
    activity = discord.Activity(type=discord.ActivityType.watching, name="@bonnaKBA")
    bot.loop.create_task(check_members())
    await bot.change_presence(status=discord.Status.online, activity=activity)


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

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx):
    logging.info("Команда kick вызвана")
    guild = ctx.guild
    kicked_count = 0

    await ctx.send("Начинаю кикать пользователей без ролей...")

    for member in guild.members:
        logging.debug(f"Проверяю пользователя {member.name}, роли: {len(member.roles)}")
        if len(member.roles) == 1:
            try:
                await member.kick(reason="Отсутствие ролей")
                kicked_count += 1
                logging.info(f'Кикнут пользователь {member.name} без ролей.')
            except discord.Forbidden:
                logging.warning(f'Не удалось кикнуть {member.name}, недостаточно прав.')
            except Exception as e:
                logging.error(f'Ошибка при кике {member.name}: {e}')

    await ctx.send(f'Кикнуто {kicked_count} пользователей без ролей.' if kicked_count > 0 else "Нет пользователей для кика.")

def extract_id_from_mention(mention: str):
    match = re.match(r'<#(\d+)>', mention)
    if match:
        return int(match.group(1))
    return None

async def process_embeds_for_user(user_id, embeds):
    second_embed = None
    decision_embed = None

    for embed in embeds:
        for field in embed.fields:
            if "Канал" in field.name:
                second_embed = embed
            if "Принял" in field.name or "Отклонил" in field.name:
                decision_embed = embed

    if not second_embed or not decision_embed:
        logging.warning("❌ Не удалось найти нужные эмбеды")
        return

    target_channel_id = None
    decision = None
    decision_made_by = None

    logging.debug("📥 Парсим второй embed")
    for field in second_embed.fields:
        logging.debug(f"Поле: {field.name} = {field.value}")
        if "Канал" in field.name:
            match = re.search(r"<#(\d+)>", field.value)
            if match:
                target_channel_id = int(match.group(1))
                logging.debug(f"✅ Извлечён channel_id: {target_channel_id}")

    logging.debug("📥 Парсим embed с решением")
    for field in decision_embed.fields:
        logging.debug(f"Поле: {field.name} = {field.value}")
        if "Принял" in field.name:
            decision = "accepted"
        elif "Отклонил" in field.name:
            decision = "denied"
        match = re.search(r"<@!?(\d+)>", field.value)
        if match:
            decision_made_by = int(match.group(1))
            logging.debug(f"✅ Извлечён decision_made_by: {decision_made_by}")

    logging.debug(f"Итоговые значения: user_id={user_id}, channel_id={target_channel_id}, decision={decision}, decision_by={decision_made_by}")

    if not all([user_id, target_channel_id, decision]):
        logging.warning("❌ Не хватает данных для обработки решения")
        return

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        logging.error("❌ Guild не найден")
        return

    member = guild.get_member(user_id)
    if not member:
        logging.error(f"❌ Пользователь с ID {user_id} не найден")
        return

    target_channel = guild.get_channel(target_channel_id)
    if not target_channel:
        logging.error(f"❌ Канал с ID {target_channel_id} не найден")
        return

    try:
        await target_channel.set_permissions(member, overwrite=None)
        logging.info(f"✅ Сняты пермишены у {member.name} в #{target_channel.name}, решение: {decision}")
    except Exception as e:
        logging.error(f"❌ Ошибка при снятии прав: {e}")

@bot.event
async def on_message(message):
    if message.channel.id != WATCHED_CHANNEL_ID:
        return

    logging.debug(f"on_message вызван: канал={message.channel.id}, автор={message.author}, embeds={len(message.embeds)}")

    await bot.process_commands(message)

    if not message.embeds:
        return

    embed = message.embeds[0]

    # Извлекаем user_id из embed (поле "Кого" или "Пользователь")
    user_id = None
    for field in embed.fields:
        if "Кого" in field.name or "Пользователь" in field.name:
            match = re.search(r"<@!?(\d+)>", field.value)
            if match:
                user_id = int(match.group(1))
                logging.debug(f"✅ Извлечён user_id: {user_id}")
                break

    if not user_id:
        logging.warning("❌ Не удалось извлечь user_id из embed")
        return

    partial_embeds[user_id].append(embed)
    logging.debug(f"📥 Добавлен embed для user_id={user_id}, всего {len(partial_embeds[user_id])} embeds")

    # Проверяем, есть ли embed с решением (Принял или Отклонил)
    decision_present = any(
        any("Принял" in field.name or "Отклонил" in field.name for field in e.fields)
        for e in partial_embeds[user_id]
    )

    if decision_present:
        embeds_to_process = partial_embeds.pop(user_id)
        await process_embeds_for_user(user_id, embeds_to_process)

print("🚀 Запуск бота...", flush=True)
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Ошибка при запуске бота: {e}", flush=True)