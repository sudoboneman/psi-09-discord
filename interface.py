# official_interface.py
import contextlib
import discord
from discord.ext import commands
from flask import Flask
import threading
import os
import aiohttp
import asyncio
import re
import traceback
import logging
import sys
from dotenv import load_dotenv

# Configure Logging for Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PSI09-Official")

load_dotenv()

# --- Flask App for Render Keep-Alive ---
app = Flask(__name__)


@app.route("/")
def home():
    return "PSI-09 Official Bot Interface is Active", 200


def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask keep-alive on port {port}")
    app.run(host="0.0.0.0", port=port)


# --- Discord Official Bot Configuration ---
# Official bots require explicit Intents to see message content
intents = discord.Intents.default()
intents.message_content = True  # CRITICAL: Must be enabled in Dev Portal too
intents.members = True  # Recommended for member display names

bot = commands.Bot(command_prefix="!", intents=intents, chunk_guilds_at_startup=True)

http_session = None


async def get_http_session():
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    return http_session


@bot.event
async def on_ready():
    logger.info(
        f"SUCCESS: PSI-09 Official Bot Online as {bot.user.name} (ID: {bot.user.id})"
    )


@bot.event
async def on_message(message):
    # Don't roast yourself
    if message.author == bot.user:
        return

    # 1. Identify Context
    # Note: Official bots cannot be in standard Group DMs, only Servers and 1-on-1 DMs
    is_dm = isinstance(message.channel, discord.DMChannel)

    # Mention detection for official bots is more robust
    is_mentioned = bot.user in message.mentions or str(bot.user.id) in message.content

    # Define the group name
    if is_dm:
        group_name = "Discord_DM"
    else:
        # For official bots, guild.name is always available if it's not a DM
        group_name = (
            str(message.guild.name)
            if message.guild
            else f"Private_Channel_{message.channel.id}"
        )

    # 2. Payload Construction
    payload = {
        "message": message.content,
        "sender": message.author.display_name,
        "group_name": group_name,
    }

    # 3. Typing & Relay Logic
    should_reply_active = is_dm or is_mentioned

    if should_reply_active:
        logger.info(
            f"Active message from {message.author.display_name} in {group_name}"
        )
        typing_context = message.channel.typing()
    else:
        logger.info(
            f"Passive chatter logged from {message.author.display_name} in {group_name}"
        )
        typing_context = contextlib.nullcontext()

    # 4. The Relay (Your fine-tuned logic)
    try:
        async with typing_context:
            backend_url = os.getenv("PSI09_API_URL")
            session = await get_http_session()
            async with session.post(backend_url, json=payload, timeout=25) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    reply = data.get("reply", "")

                    if reply:
                        logger.info(f"Sending reply: {reply[:50]}...")
                        # Use bot's native reference reply
                        try:
                            await message.reply(reply)
                        except:
                            await message.channel.send(reply)
                else:
                    if should_reply_active:
                        logger.error(f"Backend Error: {resp.status}")
    except Exception as e:
        logger.error(f"Relay Error: {e}")

    # Ensure commands still work if you add any later
    await bot.process_commands(message)


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()

    token = os.getenv("BOT_TOKEN")  # Replace USER_TOKEN in Render environment variables
    if not token:
        logger.error("CRITICAL: BOT_TOKEN not found in environment variables.")
        sys.exit(1)

    try:
        bot.run(token)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        logger.error(traceback.format_exc())
