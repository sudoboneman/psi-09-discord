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
    command_prefix="!", self_bot=True, chunk_guilds_at_startup=False, max_messages=None
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
    # Ignore messages sent by the bot itself
    if message.author == client.user:
        return

    # 1. Identify Context
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions

    # Define the group/context name for MongoDB
    if is_dm:
        group_name = "Discord_DM"
    else:
        # Use server name for collective tracking
        group_name = str(message.guild.name) if message.guild else "Unknown_Server"

    # 2. Passive Listener Logic
    # We relay EVERY message in a server to the backend so it can build 'Group Memory'
    # We also relay all DMs.
    should_relay = is_dm or not is_dm  # Effectively always True for DMs and Servers

    if should_relay:
        clean_text = re.sub(r"<@!?\d+>", "", message.content).strip()

        # Log based on whether it's a passive listen or an active reply
        if is_dm or is_mentioned:
            logger.info(
                f"Active message from {message.author.display_name} in {group_name}"
            )
        else:
            logger.info(
                f"Passive chatter logged from {message.author.display_name} in {group_name}"
            )

        payload = {
            "message": clean_text or "[chatter]",
            "sender": message.author.display_name,
            "group_name": group_name,
        }

        # 3. Typing & Relay Logic
        # Only show 'typing...' if the bot is actually going to respond
        typing_manager = (
            message.channel.typing()
            if (is_dm or is_mentioned)
            else contextlib.nullcontext()
        )

        try:
            async with typing_manager:
                backend_url = os.getenv("PSI09_API_URL")
                session = await get_http_session()

                async with session.post(backend_url, json=payload, timeout=25) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("reply", "")

                        # 4. Reply Logic
                        # Only send a message back to Discord if the backend generated a roast
                        if reply:
                            logger.info(f"Sending reply: {reply[:50]}...")
                            try:
                                await message.channel.send(reply, reference=message)
                                logger.info("Reply sent successfully.")
                            except Exception as discord_err:
                                logger.warning(
                                    f"Reference reply failed, sending plain: {discord_err}"
                                )
                                await message.channel.send(reply)
                    else:
                        # Only log errors if we were expecting a reply
                        if is_dm or is_mentioned:
                            error_body = await resp.text()
                            logger.error(f"Backend Error ({resp.status}): {error_body}")

        except asyncio.TimeoutError:
            if is_dm or is_mentioned:
                logger.error("Request to backend timed out.")
        except Exception as e:
            logger.error(f"Critical Interface Error: {str(e)}")


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
