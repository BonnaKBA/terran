import re
import os
import disnake
from dotenv import load_dotenv
from disnake.ext import commands
from disnake.ui import Button, View
from disnake import MessageInteraction

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
ALLOWED_ROLES = int(os.getenv("ALLOWED_ROLES"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_choices = {}
vote_message_ids = {}
locked_users = set()
vote_choices = {}
locked_users = set()

async def yes_callback(interaction):
    if interaction.user.id in locked_users:
        await interaction.response.send_message("Вы не можете менять выбор, так как он был изменён администратором.", ephemeral=True)
        return
    
    vote_id = interaction.message.id
    reason = interaction.message.content.split("\n")[0]
    reason = reason.replace("@everyone", "").strip()

    if vote_id not in vote_choices:
        vote_choices[vote_id] = {}
    
    old_choice = vote_choices[vote_id].get(interaction.user.id, None)
    vote_choices[vote_id][interaction.user.id] = '✅'
    
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    
    if old_choice != '✅':
        if log_channel:
            if old_choice is None:
                await log_channel.send(f"Сбор {reason}: @{interaction.user.mention} сделал первый выбор ✅.")
            else:
                await log_channel.send(f"Сбор {reason}: @{interaction.user.mention} изменил свой выбор с {old_choice} на ✅.")
    
    embed = interaction.message.embeds[0]
    await update_vote_message(embed, interaction.message, old_choice=old_choice, new_choice='✅', ctx=interaction, reason=reason)
    await interaction.response.defer()

async def no_callback(interaction):
    if interaction.user.id in locked_users:
        await interaction.response.send_message("Вы не можете менять выбор, так как он был изменён администратором.", ephemeral=True)
        return
    
    vote_id = interaction.message.id
    reason = interaction.message.content.split("\n")[0]
    reason = reason.replace("@everyone", "").strip()
    
    if vote_id not in vote_choices:
        vote_choices[vote_id] = {}
    
    old_choice = vote_choices[vote_id].get(interaction.user.id, None)
    vote_choices[vote_id][interaction.user.id] = '❌'
    
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if old_choice != '❌':
        if log_channel:
            if old_choice is None:
                await log_channel.send(f"Сбор {reason}: @{interaction.user.mention} сделал первый выбор ❌.")
            else:
                await log_channel.send(f"Сбор {reason}: @{interaction.user.mention} изменил свой выбор с {old_choice} на ❌.")
    
    embed = interaction.message.embeds[0]
    await update_vote_message(embed, interaction.message, old_choice=old_choice, new_choice='❌', ctx=interaction, reason=reason)
    await interaction.response.defer()

async def close_callback(interaction):
    member = interaction.guild.get_member(interaction.user.id)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if any(role.id in ALLOWED_ROLES for role in member.roles):
        vote_id = interaction.message.id
        if vote_id in vote_choices and vote_choices[vote_id]:
            participants_list = "\n".join(
                [f"{i + 1}. {bot.get_user(user_id).mention}: {choice}" for i, (user_id, choice) in enumerate(vote_choices[vote_id].items())]
            )
        else:
            participants_list = "Нет участников."
        embed = disnake.Embed(
            title="Голосование закрыто",
            description=f"**Участники:**\n{participants_list}",
            color=disnake.Color.red()
        )
        embed.set_footer(text=f"Закрыто администратором: {interaction.user.display_name}")
        
        if log_channel:
            await log_channel.send(f"{interaction.user.mention} закрыл сбор, в котором участвовали:", embed=embed)
        await interaction.message.delete()
        await interaction.response.send_message("Голосование закрыто.", ephemeral=True)
    else:
        await interaction.response.send_message("У вас нет прав на закрытие голосования.", ephemeral=True)

async def edit_callback(interaction):
    member = interaction.guild.get_member(interaction.user.id)
    if any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message(
            "Введите номер участника и новый выбор в формате `!edit <номер участника> <новый выбор (✅/❌ или 1/2)>.`", ephemeral=True
        )
    else:
        await interaction.response.send_message("У вас нет прав на редактирование голосов.", ephemeral=True)

@bot.command(name="vote")
async def vote(ctx, *, reason: str = None):
    if reason is None:
        await ctx.send("Ошибка: нужно указать причину сбора. `Пример: !vote <причина>.`", delete_after=10)
        await ctx.message.delete()
        return
    await ctx.message.delete()

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"{ctx.author.mention} начал сбор: {reason}")

    embed = disnake.Embed(
        description="**Участники:**\n",
        color=disnake.Color.blurple()
    )

    mention_message = f"{ctx.author.mention} начал сбор."

    yes_button = Button(label="Отметиться ✅", style=disnake.ButtonStyle.success)
    no_button = Button(label="Покинуть ❌", style=disnake.ButtonStyle.danger)
    close_button = Button(label="Закрыть 🛑", style=disnake.ButtonStyle.secondary)
    edit_button = Button(label="Редактировать ✏️", style=disnake.ButtonStyle.secondary)

    yes_button.callback = yes_callback
    no_button.callback = no_callback
    close_button.callback = close_callback
    edit_button.callback = edit_callback

    message = await ctx.send(content=f"# {reason} @everyone\n{mention_message}", embed=embed, view=create_vote_view(yes_button, no_button, close_button, edit_button))

    vote_message_ids[ctx.guild.id] = message.id

def create_vote_view(yes_button, no_button, close_button, edit_button):
    view = View()
    view.add_item(yes_button)
    view.add_item(no_button)
    view.add_item(close_button)
    view.add_item(edit_button)
    return view

async def update_vote_message(embed, message, ctx=None, is_admin_edit=False, old_choice=None, new_choice=None, reason=None):
    vote_id = message.id
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if vote_id not in vote_choices:
        vote_choices[vote_id] = {}

    user_id = ctx.user.id if ctx else None

    if user_id:
        old_choice = vote_choices[vote_id].get(user_id, None)
        if old_choice != new_choice:
            vote_choices[vote_id][user_id] = new_choice
        participants_list = []
        user_number_map = {}
        for i, (user_id, choice) in enumerate(vote_choices[vote_id].items()):
            participant = bot.get_user(user_id)
            if participant:
                participants_list.append(f"{i + 1}. {participant.mention}: {choice}")
                user_number_map[i + 1] = user_id
        participants_str = "\n".join(participants_list) if participants_list else "Нет участников"
        if len(embed.fields) > 0:
            embed.set_field_at(0, name="Участники", value=participants_str)
        else:
            embed.add_field(name="Участники", value=participants_str)
        await message.edit(embed=embed)

        if ctx:
            if old_choice is None:
                if log_channel:
                    await log_channel.send(f"Сбор {reason}: @{ctx.author.mention} сделал первый выбор {new_choice}.")

            elif old_choice != new_choice:
                if log_channel:
                    await log_channel.send(f"Сбор {reason}: @{ctx.author.mention} изменил свой выбор с {old_choice} на {new_choice}.")

        return user_number_map

    if is_admin_edit:
        locked_users.add(ctx.author.id)
        for button in message.components[0].children:
            if button.label == 'Отметиться ✅' or button.label == 'Покинуть ❌':
                button.disabled = True
        await message.edit(view=create_vote_view(*message.components[0].children))

@bot.command(name="edit")
async def edit(ctx, number: int = None, new_choice: str = None):
    await ctx.message.delete()

    if number is None or new_choice is None:
        await ctx.send("Ошибка: нужно указать номер участника и новый выбор. Пример: `!edit <номер участника> <новый выбор (✅/❌ или 1/2)>`", delete_after=10)
        return

    if new_choice == '1':
        new_choice = '✅'
    elif new_choice == '2':
        new_choice = '❌'
    if new_choice not in ['✅', '❌']:
        await ctx.send("Ошибка: новый выбор должен быть ✅ или ❌ (или 1 для ✅ и 2 для ❌).", delete_after=10)
        return

    member = ctx.guild.get_member(ctx.author.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await ctx.send("Ошибка: У вас нет прав на редактирование выборов.", delete_after=10)
        return

    if ctx.guild.id not in vote_message_ids:
        await ctx.send("Ошибка: ID сообщения голосования не найдено.", delete_after=10)
        return

    message_id = vote_message_ids[ctx.guild.id]
    channel = ctx.channel

    try:
        message = await channel.fetch_message(message_id)
        embed = message.embeds[0]
    except disnake.NotFound:
        await ctx.send("Ошибка: Сообщение с голосованием не найдено.", delete_after=10)
        return

    vote_id = message.id
    if vote_id not in vote_choices:
        await ctx.send("Ошибка: Голосование еще не началось.", delete_after=10)
        return

    participants = list(vote_choices[vote_id].items())
    if number < 1 or number > len(participants):
        await ctx.send("Ошибка: Участник с таким номером не найден.", delete_after=10)
        return

    user_id, old_choice = participants[number - 1]

    if old_choice == new_choice:
        await ctx.send("Ошибка: Новый выбор совпадает с текущим. Изменение не требуется.", delete_after=10)
        return

    vote_choices[vote_id][user_id] = new_choice

    edited_member = ctx.guild.get_member(user_id)

    if not any(role.id in ALLOWED_ROLES for role in edited_member.roles):
        locked_users.add(user_id)
    participants_list = [
        f"{i + 1}. {bot.get_user(uid).mention}: {choice}" for i, (uid, choice) in enumerate(vote_choices[vote_id].items())
    ]
    participants_str = "\n".join(participants_list) if participants_list else "Нет участников"

    if len(embed.fields) > 0:
        embed.set_field_at(0, name="Участники", value=participants_str)
    else:
        embed.add_field(name="Участники", value=participants_str)
    await message.edit(embed=embed)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(
            f"{ctx.author.mention} изменил выбор {edited_member.mention} с {old_choice} на {new_choice}."
        )

class VotingView(View):
    def __init__(self, vote_id):
        super().__init__()
        self.vote_id = vote_id

    @disnake.ui.button(label="Отметиться ✅", style=disnake.ButtonStyle.green)
    async def confirm(self, button: Button, interaction: MessageInteraction):
        user_id = interaction.user.id

        if user_id in locked_users:
            await interaction.response.send_message(
                "Вы не можете менять выбор, так как он был изменён администратором.", ephemeral=True
            )
            return

        if self.vote_id not in vote_choices:
            await interaction.response.send_message(
                "Ошибка: голосование еще не началось.", ephemeral=True
            )
            return

        vote_choices[self.vote_id][user_id] = "✅"
        await update_vote_embed(interaction.message)

    @disnake.ui.button(label="Покинуть ❌", style=disnake.ButtonStyle.red)
    async def leave(self, button: Button, interaction: MessageInteraction):
        user_id = interaction.user.id

        if user_id in locked_users:
            await interaction.response.send_message(
                "Вы не можете менять выбор, так как он был изменён администратором.", ephemeral=True
            )
            return

        if self.vote_id not in vote_choices:
            await interaction.response.send_message(
                "Ошибка: голосование еще не началось.", ephemeral=True
            )
            return

        vote_choices[self.vote_id].pop(user_id, None)
        await update_vote_embed(interaction.message)


async def update_vote_embed(message):
    """
    Обновляет embed сообщения с текущим списком участников.
    """
    vote_id = message.id
    if vote_id not in vote_choices:
        return

    embed = message.embeds[0]
    participants_list = [
        f"{i + 1}. {bot.get_user(uid).mention}: {choice}" for i, (uid, choice) in enumerate(vote_choices[vote_id].items())
    ]
    participants_str = "\n".join(participants_list) if participants_list else "Нет участников"

    if len(embed.fields) > 0:
        embed.set_field_at(0, name="Участники", value=participants_str)
    else:
        embed.add_field(name="Участники", value=participants_str)
    await message.edit(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"Ошибка: команда не найдена. Используйте !vote для начала голосования.", delete_after=10)
    else:
        raise error

bot.run(TOKEN)