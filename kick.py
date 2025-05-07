import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} запущен!')

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx):
    guild = ctx.guild
    kicked_count = 0
    
    await ctx.send("Начинаю кикать пользователей без ролей...")
    
    for member in guild.members:
        if len(member.roles) == 1:
            try:
                await member.kick(reason="Отсутствие ролей")
                kicked_count += 1
                print(f'Кикнут пользователь {member.name} без ролей.')
            except discord.Forbidden:
                print(f'Не удалось кикнуть {member.name}, недостаточно прав.')
            except Exception as e:
                print(f'Ошибка при кике {member.name}: {e}')
    
    await ctx.send(f'Кикнуто {kicked_count} пользователей без ролей.' if kicked_count > 0 else "Нет пользователей для кика.")

bot.run(TOKEN)
