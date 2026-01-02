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
    if message.author == client.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions

    if is_dm or is_mentioned:
        logger.info(
            f"Message detected from {message.author.display_name} in {'DM' if is_dm else 'Server'}"
        )

        clean_text = re.sub(r"<@!?\d+>", "", message.content).strip()

        payload = {
            "message": clean_text or "[empty_mention]",
            "sender": message.author.display_name,
            "group_name": str(message.guild.name) if message.guild else "Discord_DM",
        }

        async with message.channel.typing():
            try:
                backend_url = os.getenv("PSI09_API_URL")
                logger.info(f"Relaying to backend: {backend_url}")

                session = await get_http_session()
                # Use a slightly longer timeout (25s) for OpenAI latency
                async with session.post(backend_url, json=payload, timeout=25) as resp:
                    logger.info(f"Backend status: {resp.status}")

                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("reply", "")

                        if reply:
                            logger.info(f"Sending reply: {reply[:50]}...")
                            try:
                                # Try to reply with reference
                                await message.channel.send(reply, reference=message)
                                logger.info("Reply sent successfully.")
                            except Exception as discord_err:
                                logger.warning(
                                    f"Failed to send as reference, trying plain send: {discord_err}"
                                )
                                await message.channel.send(reply)
                        else:
                            logger.warning(
                                "Backend returned 200 but 'reply' key was empty."
                            )
                    else:
                        error_body = await resp.text()
                        logger.error(f"Backend Error ({resp.status}): {error_body}")

            except asyncio.TimeoutError:
                logger.error("Request to backend timed out (25s limit reached).")
            except Exception as e:
                logger.error(f"Critical Interface Error: {str(e)}")
                logger.error(traceback.format_exc())


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
