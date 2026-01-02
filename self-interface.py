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

# Configure Logging to show in Render Console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PSI09-Interface")

load_dotenv()

# --- Flask App for Render Keep-Alive ---
app = Flask(__name__)


@app.route("/")
def home():
    return "PSI-09 Self-Bot Interface is Active", 200


def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask keep-alive on port {port}")
    app.run(host="0.0.0.0", port=port)


# --- Discord Self-Bot Configuration ---
client = commands.Bot(
    command_prefix="!", self_bot=True, chunk_guilds_at_startup=True, max_messages=None
)

http_session = None


async def get_http_session():
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    return http_session


@client.event
async def on_ready():
    logger.info(
        f"SUCCESS: PSI-09 Self-Bot Online as {client.user.name} (ID: {client.user.id})"
    )


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # 1. Identify Context
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_group_dm = isinstance(message.channel, discord.GroupChannel)

    # RELIABLE MENTION DETECTION
    # Checks if you are tagged OR if your numeric ID is in the text
    is_mentioned = client.user in message.mentions
    if not is_mentioned:
        # Fallback: check raw text for your ID (Discord sometimes misses this in Group DMs)
        is_mentioned = str(client.user.id) in message.content

    # Define the group name
    if is_dm:
        group_name = "Discord_DM"
    elif is_group_dm:
        group_name = (
            message.channel.name
            if message.channel.name
            else f"GroupDM_{message.channel.id}"
        )
    else:
        group_name = (
            str(message.guild.name) if message.guild else f"Server_{message.guild_id}"
        )

    # 2. Payload Construction
    # We send RAW content so the backend can run its own regex
    payload = {
        "message": message.content,
        "sender": message.author.display_name,
        "group_name": group_name,
    }

    # 3. Typing & Relay Logic
    # Always show typing if it's a DM or a Mention
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

    # 4. The Relay
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
                        try:
                            await message.channel.send(reply, reference=message)
                        except:
                            await message.channel.send(reply)
                else:
                    if should_reply_active:
                        logger.error(f"Backend Error: {resp.status}")
    except Exception as e:
        logger.error(f"Relay Error: {e}")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()

    token = os.getenv("USER_TOKEN")
    if not token:
        logger.error("CRITICAL: USER_TOKEN not found in environment variables.")
        sys.exit(1)

    try:
        client.run(token)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        logger.error(traceback.format_exc())
