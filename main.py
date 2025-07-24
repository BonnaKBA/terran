import re
import os
import discord
import asyncio
from discord.ext import commands
from discord import Embed, Interaction
from discord.ui import View, Button
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timedelta
import logging

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
WATCHED_CHANNEL_ID = int(os.getenv("WATCHED_CHANNEL_ID"))
AFK_CHANNEL_ID = int(os.getenv("AFK_CHANNEL_ID"))

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CHECK_INTERVAL = 60
KICK_TIME = 3600
MAX_SESSION_DURATION = timedelta(minutes=2)

partial_embeds = defaultdict(list)  # user_id -> list of embeds
voice_sessions = {}  # user_id -> start_time datetime
voice_ratings = defaultdict(timedelta)  # user_id -> total voice time (timedelta)


@bot.event
async def on_ready():
    logging.info("on_ready вызван")
    print("Бот запущен", flush=True)
    logging.info(f"Токен используется для: {bot.user}")
    activity = discord.Activity(type=discord.ActivityType.watching, name="@bonnaKBA")
    bot.loop.create_task(check_members())
    await bot.change_presence(status=discord.Status.online, activity=activity)


#Кик без ролей (автоматически)
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


#Кик без ролей (вручную)
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


#Удаление выданных пермишенов при обзвоне
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
    if message.author == bot.user:
        return

    logging.debug(f"on_message вызван: канал={message.channel.id}, автор={message.author}, embeds={len(message.embeds)}")

    await bot.process_commands(message)

    if message.channel.id != WATCHED_CHANNEL_ID:
        return
    if not message.embeds:
        return

    embed = message.embeds[0]

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

    decision_present = any(
        any("Принял" in field.name or "Отклонил" in field.name for field in e.fields)
        for e in partial_embeds[user_id]
    )

    if decision_present:
        embeds_to_process = partial_embeds.pop(user_id)
        await process_embeds_for_user(user_id, embeds_to_process)


#Голосовой рейтинг
def format_duration(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}ч {minutes}м {seconds}с"

from discord.ui import View, Button
from discord import Interaction

class VoiceRatingPaginator(View):
    def __init__(self, ctx, ratings, per_page=10):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.ratings = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(self.ratings) - 1) // per_page + 1

        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.total_pages - 1

    async def send_page(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_ratings = self.ratings[start:end]

        embed = discord.Embed(
            title="🎤 Топ голосовой активности",
            color=discord.Color.blurple()
        )

        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, duration) in enumerate(page_ratings, start=start + 1):
            member = self.ctx.guild.get_member(user_id)
            name = member.display_name if member else f"Пользователь с ID {user_id}"
            if i <= 3:
                place = medals[i - 1]
            else:
                place = f"{i}."
            embed.add_field(name=f"{place} {name}", value=format_duration(duration), inline=False)

        embed.set_footer(text=f"Страница {self.current_page + 1} из {self.total_pages}")

        if hasattr(self, 'message'):
            await self.message.edit(embed=embed, view=self)
        else:
            self.message = await self.ctx.send(embed=embed, view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Это не ваша сессия.", ephemeral=True)
            return
        self.current_page -= 1
        self.update_buttons()
        await self.send_page()
        await interaction.response.defer()

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Это не ваша сессия.", ephemeral=True)
            return
        self.current_page += 1
        self.update_buttons()
        await self.send_page()
        await interaction.response.defer()

@bot.command()
async def voice(ctx):
    if not voice_ratings:
        await ctx.send("Пока нет данных по голосовой активности.")
        return

    paginator = VoiceRatingPaginator(ctx, voice_ratings)
    await paginator.send_page()


def is_active(member):
    if not member.voice or not member.voice.channel:
        return False
    if member.voice.channel.id == AFK_CHANNEL_ID:
        return False
    if member.voice.self_mute or member.voice.self_deaf:
        return False
    if member.voice.mute or member.voice.deaf:
        return False
    return True

def count_active_members(channel):
    if channel is None:
        return 0
    return sum(is_active(m) for m in channel.members)

def should_track(channel):
    if channel is None:
        return False
    if channel.id == AFK_CHANNEL_ID:
        return False
    active_count = sum(is_active(m) for m in channel.members)
    logging.debug(f"Активных участников в канале {channel.name}: {active_count}")
    return active_count >= 2

@bot.event
async def on_voice_state_update(member, before, after):
    now = datetime.utcnow()
    uid = member.id

    logging.debug(f"on_voice_state_update вызван: member={member}, before.channel={before.channel}, after.channel={after.channel}")

    # Пользователь вышел из голосового канала или переключился
    if before.channel and before.channel != after.channel:
        logging.debug(f"Пользователь {member.display_name} покидает канал {before.channel.name}")
        session = voice_sessions.pop(uid, None)
        if session:
            if session["last_active"]:
                session["active"] += now - session["start"]
            total = session["active"]
            if total > MAX_SESSION_DURATION:
                total = MAX_SESSION_DURATION
            voice_ratings[uid] += total
            logging.info(f"{member.display_name} покинул {before.channel.name}, добавлено {total}")


    # Пользователь зашёл или переключился в канал
    if after.channel and should_track(after.channel):
        voice_sessions[uid] = {
            "start": now,
            "active": timedelta(),
            "last_active": not (member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf)
        }
        logging.info(f"{member.display_name} зашёл в {after.channel.name}, активность: {voice_sessions[uid]['last_active']}")

    # Пользователь остался в том же канале, но изменил mute/deaf статус
    elif before.channel and after.channel and before.channel == after.channel:
        session = voice_sessions.get(uid)
        if not session:
            return

        was_active = session["last_active"]
        now_active = not (member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf)

        if was_active and not now_active:
            session["active"] += now - session["start"]
            voice_ratings[uid] += session["active"]  # Добавляем в общий рейтинг
            session["active"] = timedelta()          # Обнуляем накопленное время, т.к. оно уже учтено
            logging.info(f"{member.display_name} стал неактивным, добавлено {now - session['start']}")
        elif not was_active and now_active:
            session["start"] = now
            logging.info(f"{member.display_name} стал активным")

        session["last_active"] = now_active



@bot.command()
async def test(ctx):
    await ctx.send("test")


print("🚀 Запуск бота...", flush=True)
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Ошибка при запуске бота: {e}", flush=True)