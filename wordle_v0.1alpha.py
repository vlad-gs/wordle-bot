import discord
from discord.ext import commands
import re
from datetime import datetime, timedelta
import pytz
import os
import json

# Set Discord privileges
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# File to store Wordle data
DATA_FILE = "wordle_data.json"

# Ensure the file exists
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"users": {}}, f)

def load_data():
    """Load data from the JSON file."""
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    """Save data to the JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_game_date(game_number):
    """Calculate the date corresponding to a Wordle game number."""
    return wordle_start_date + timedelta(days=(game_number - wordle_start_game))

# Define the Hawaii timezone
hawaii_tz = pytz.timezone('Pacific/Honolulu')

# Initialize global variables for tracking the current month and the Wordle game starting point
current_month = datetime.now(hawaii_tz).month
wordle_start_date = datetime(2021, 6, 19)  # Adjust based on Wordle's actual start date
wordle_start_game = 1  # The first Wordle game number

# Data structure to store Wordle stats and leaderboard
wordle_leaderboard = {}

# Regex to detect Wordle entries
wordle_regex = re.compile(r"^Wordle (?P<day>\d{1,4}[,.]?\d{0,3}) (?P<result>[Xx1-6])/6", re.MULTILINE)

# Define the allowed Wordle channel
WORDLE_CHANNEL_NAME = "CHANNEL_NAME"  # Replace with your specific channel name

# Define what to do on login
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    data = load_data()
    if not data["users"]:  # If the data file is empty, process message history
        print("Populating data from message history...")
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name == WORDLE_CHANNEL_NAME:
                    if channel.permissions_for(guild.me).read_message_history:
                        try:
                            async for message in channel.history(limit=None):
                                if message.author.bot:
                                    continue

                                if message.content.startswith("Wordle"):
                                    matches = wordle_regex.findall(message.content)
                                    for day, result in matches:
                                        day = day.replace(",", "").replace(".", "")
                                        attempts = 7 if result.upper() == "X" else int(result)
                                        user_id = str(message.author.id)

                                        if user_id not in data["users"]:
                                            data["users"][user_id] = {}

                                        data["users"][user_id][day] = attempts
                        except Exception as e:
                            print(f"Error fetching history in #{channel.name}: {e}")
        save_data(data)

# Define how to process Wordle entries
@bot.event
async def on_message(message):
    if message.channel.name != WORDLE_CHANNEL_NAME:
        return

    if message.author.bot:
        return

    if message.content.startswith("Wordle"):
        data = load_data()
        matches = wordle_regex.findall(message.content)
        for day, result in matches:
            day = day.replace(",", "").replace(".", "")
            attempts = 7 if result.upper() == "X" else int(result)
            user_id = str(message.author.id)

            if user_id not in data["users"]:
                data["users"][user_id] = {}

            data["users"][user_id][day] = attempts  # Overwrite or add entry
        save_data(data)

        if matches:
            await message.add_reaction("✅")
        else:
            await message.add_reaction("❌")

    await bot.process_commands(message)

# Define !leaderboard command
@bot.command()
async def leaderboard(ctx):
    data = load_data()
    if not data["users"]:
        await ctx.send("The leaderboard is empty!")
        return

    now = datetime.now(hawaii_tz)
    embed = discord.Embed(
        title=f"Wordle Leaderboard for {now.strftime('%B %Y')}",
        color=discord.Color.blue(),
        timestamp=now,
    )
    leaderboard_message = ""
    aggregated_stats = {}

    for user_id, games in data["users"].items():
        total_attempts = sum(games.values())
        total_games = len(games)
        aggregated_stats[user_id] = (total_attempts, total_games)

    sorted_leaderboard = sorted(
        aggregated_stats.items(),
        key=lambda x: (x[1][0] / x[1][1], -x[1][1])
    )

    for rank, (user_id, (total_attempts, total_games)) in enumerate(sorted_leaderboard, start=1):
        average_attempts = total_attempts / total_games
        member = ctx.guild.get_member(int(user_id))
        name = member.display_name if member else f"User ID: {user_id}"
        leaderboard_message += f"#{rank}: {name} - {average_attempts:.2f} ({total_games}/{now.day})\n"

    embed.description = leaderboard_message
    await ctx.send(embed=embed)

# Define !stats command
@bot.command()
async def stats(ctx, member: discord.Member = None):
    data = load_data()
    member = member or ctx.author
    user_id = str(member.id)

    if user_id not in data["users"]:
        await ctx.send(f"No stats available for {member.display_name}.")
        return

    user_stats = data["users"][user_id]
    total_attempts = sum(user_stats.values())
    total_games = len(user_stats)
    average_attempts = total_attempts / total_games

    sorted_days = sorted(int(day) for day in user_stats.keys())
    streak = 0
    longest_streak = 0
    current_streak = 0
    unsuccessful_or_missed = 0

    for i in range(len(sorted_days)):
        current_day = sorted_days[i]
        if i > 0 and current_day != sorted_days[i - 1] + 1:
            missed_days = current_day - sorted_days[i - 1] - 1
            unsuccessful_or_missed += missed_days
            streak = 0

        attempts = user_stats[str(current_day)]
        if attempts == 7:
            unsuccessful_or_missed += 1
            streak = 0
        else:
            streak += 1
            longest_streak = max(longest_streak, streak)

    current_streak = streak

    stats_embed = discord.Embed(
        title=f"{member.display_name}'s Wordle Stats",
        color=discord.Color.purple(),
    )
    stats_embed.add_field(name="Games Played", value=str(total_games), inline=False)
    stats_embed.add_field(name="Average Attempts", value=f"{average_attempts:.2f}", inline=False)
    stats_embed.add_field(name="Longest Streak", value=str(longest_streak), inline=False)
    stats_embed.add_field(name="Current Streak", value=str(current_streak), inline=False)
    stats_embed.add_field(name="Misses", value=str(unsuccessful_or_missed), inline=False)

    await ctx.send(embed=stats_embed)

# Daily leaderboard
async def post_daily_leaderboard():
    now = datetime.now(hawaii_tz)
    data = load_data()
    if not data["users"]:
        return  # No data to process

    leaderboard_message = f"**Daily Wordle Leaderboard for {now.strftime('%B %d, %Y')}**\n"
    aggregated_stats = {}

    # Calculate daily stats
    for user_id, games in data["users"].items():
        total_attempts = sum(games.values())
        total_games = len(games)
        aggregated_stats[user_id] = (total_attempts, total_games)

    sorted_leaderboard = sorted(
        aggregated_stats.items(),
        key=lambda x: (x[1][0] / x[1][1], -x[1][1])
    )

    for rank, (user_id, (total_attempts, total_games)) in enumerate(sorted_leaderboard, start=1):
        average_attempts = total_attempts / total_games
        leaderboard_message += f"#{rank}: User ID {user_id} - {average_attempts:.2f} ({total_games}/{now.day})\n"

    # Send the message to the Wordle channel
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.name == WORDLE_CHANNEL_NAME:
                await channel.send(leaderboard_message)

# Monthly leaderboard
async def post_final_leaderboard():
    now = datetime.now(hawaii_tz)
    data = load_data()
    if not data["users"]:
        return  # No data to process

    leaderboard_message = f"**Final Wordle Leaderboard for {now.strftime('%B %Y')}**\n"
    aggregated_stats = {}

    # Calculate final stats
    for user_id, games in data["users"].items():
        total_attempts = sum(games.values())
        total_games = len(games)
        aggregated_stats[user_id] = (total_attempts, total_games)

    sorted_leaderboard = sorted(
        aggregated_stats.items(),
        key=lambda x: (x[1][0] / x[1][1], -x[1][1])
    )

    winner = None
    for rank, (user_id, (total_attempts, total_games)) in enumerate(sorted_leaderboard, start=1):
        average_attempts = total_attempts / total_games
        if rank == 1:
            winner = f"Congratulations to User ID {user_id} for winning this month's leaderboard!"
        leaderboard_message += f"#{rank}: User ID {user_id} - {average_attempts:.2f} ({total_games}/{now.day})\n"

    # Send the message to the Wordle channel
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.name == WORDLE_CHANNEL_NAME:
                await channel.send(leaderboard_message)
                if winner:
                    await channel.send(winner)

# Run the bot
bot.run('BOT_TOKEN')  # Replace with token from dev page
