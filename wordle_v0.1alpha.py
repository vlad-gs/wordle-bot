import discord
from discord.ext import commands
import re
from datetime import datetime, time, timedelta
from discord.ext.tasks import loop
import pytz
import os
import json
import calendar

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


# Define the Hawaii timezone
hawaii_tz = pytz.timezone('Pacific/Honolulu')

# Initialize global variables for tracking the current month and the Wordle game starting point
current_month = datetime.now(hawaii_tz).month
wordle_start_date = datetime(2021, 6, 19)  # Adjust based on Wordle's actual start date
wordle_start_date = hawaii_tz.localize(wordle_start_date)
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
        print("Done!")


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


# Function to generate the leaderboard message
def generate_leaderboard_message(ctx=None):
    data = load_data()
    if not data["users"]:
        return

    now = datetime.now(hawaii_tz)
    current_year = now.year
    current_month = now.month
    current_day = now.day

    # Exception for 1st day of month to facilitate monthly call
    if current_day == 1:
        if current_month == 1:  # January
            current_month = 12
            current_year -= 1
        else:
            current_month -= 1
        _, days_passed_this_month = calendar.monthrange(current_year, current_month)

    # Calculate the first and last Wordle days for the current month in Hawaii
    first_of_month_hawaii = datetime(current_year, current_month, 1, tzinfo=hawaii_tz)
    first_wordle_day_of_month = (first_of_month_hawaii - wordle_start_date).days
    if current_day > 1:
        days_passed_this_month = current_day - 1  # Days passed in the current Hawaii month

    leaderboard_message = ""

    aggregated_stats = {}

    # Check if player has submitted results this month and create stats
    for user_id, games in data["users"].items():
        total_attempts = 0
        games_played = 0

        for day_str, attempts in games.items():
            day = int(day_str)
            if first_wordle_day_of_month <= day < first_wordle_day_of_month + days_passed_this_month:
                total_attempts += attempts
                games_played += 1

        if games_played > 0:
            if games_played < days_passed_this_month:
                total_attempts += (days_passed_this_month - games_played) * 7
            aggregated_stats[user_id] = (total_attempts, games_played)

    # Sort leaderboard by average attempts (lower is better), then by games played (higher is better)
    sorted_leaderboard = sorted(
        aggregated_stats.items(),
        key=lambda x: (x[1][0] / days_passed_this_month, -x[1][1]),
    )

    # Generate leaderboard message
    for rank, (user_id, (total_attempts, games_played)) in enumerate(sorted_leaderboard, start=1):
        average_attempts = total_attempts / days_passed_this_month
        member = ctx.guild.get_member(int(user_id))
        name = member.display_name if member else f"User ID: {user_id}"
        leaderboard_message += f"{rank}. {name} - {average_attempts:.2f} ({games_played}/{days_passed_this_month})\n"

    return leaderboard_message


# Define !leaderboard command
@bot.command()
async def leaderboard(ctx):
    leaderboard_message = generate_leaderboard_message(ctx)

    # Initialize Discord message
    now = datetime.now(hawaii_tz)
    if now.day == 1:
        now = datetime.now(hawaii_tz) - timedelta(days=1)
    embed = discord.Embed(
        title=f"Wordle Leaderboard for {now.strftime('%B %Y')}",
        color=discord.Color.blue(),
    )

    if leaderboard_message:
        embed.description = leaderboard_message
        await ctx.send(embed=embed)
    else:
        await ctx.send("No valid entries for this month yet!")


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
@loop(time=time(hour=0, tzinfo=hawaii_tz))
async def daily_leaderboard_task():
    leaderboard_message = generate_leaderboard_message()

    now = datetime.now(hawaii_tz)
    if now.day == 1:
        await post_final_leaderboard()
        return  # Skip sending the daily leaderboard message, use monthly call instead

    # Initialize Discord message

    embed = discord.Embed(
        title=f"**Daily Wordle Leaderboard for {now.strftime('%B %d, %Y')}**",
        color=discord.Color.blue(),
    )
    if leaderboard_message:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name == WORDLE_CHANNEL_NAME:
                    embed.description = leaderboard_message
                    await channel.send(embed=embed)


# Monthly leaderboard
async def post_final_leaderboard():
    leaderboard_message = generate_leaderboard_message()

    data = load_data()
    if not data["users"]:
        return  # No data to process

    now = datetime.now(hawaii_tz) - timedelta(days=1)
    if leaderboard_message:
        # Initialize the Discord embed message for the monthly leaderboard
        embed = discord.Embed(
            title=f"**Final Wordle Leaderboard for {now.strftime('%B %Y')}**",
            color=discord.Color.green(),
        )

        # Send the message to the Wordle channel
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name == WORDLE_CHANNEL_NAME:
                    embed.description = leaderboard_message
                    await channel.send(embed=embed)  # Send the message to the correct channel

# Run the bot
bot.run('YOUR_TOKEN')  # Replace with token from dev page
