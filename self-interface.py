import discord
from discord.ext import commands
from flask import Flask
import threading
import os
import aiohttp
import asyncio
import re
from dotenv import load_dotenv

load_dotenv()

# --- Flask App for Render Keep-Alive ---
app = Flask(__name__)

@app.route('/')
def home():
    # Health check endpoint for Render and UptimeRobot
    return "PSI-09 Self-Bot Interface is Active", 200

def run_web_server():
    # Render binds to a dynamic port; default to 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# --- Discord Self-Bot Configuration ---
# Optimization: Disable heavy caches to save RAM on free tier VPS/Render
client = commands.Bot(
    command_prefix="!", 
    self_bot=True, 
    chunk_guilds_at_startup=False, 
    max_messages=None  # Disables message cache for memory efficiency
)

# Persistent session to avoid socket exhaustion
http_session = None

async def get_http_session():
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    return http_session

@client.event
async def on_ready():
    print(f"PSI-09 Self-Bot Online: {client.user.name}")

@client.event
async def on_message(message):
    # Do not respond to your own messages
    if message.author == client.user:
        return

    # Trigger logic: Respond in DMs or if you are @mentioned in a server
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions

    if is_dm or is_mentioned:
        # 1. Clean mentions out of the content (converts <@ID> to empty string)
        clean_text = re.sub(r'<@!?\d+>', '', message.content).strip()
        
        # 2. Map data to main.py expected POST arguments
        payload = {
            "message": clean_text or "[empty_mention]",
            "sender": message.author.display_name,
            "group_name": str(message.guild.name) if message.guild else "Discord_DM"
        }

        # 3. Relay to Roastbot Backend
        async with message.channel.typing():
            try:
                session = await get_http_session()
                async with session.post(os.getenv("PSI09_API_URL"), json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("reply", "")
                        if reply:
                            # Send response as a reply to the original message
                            await message.channel.send(reply, reference=message)
            except Exception as e:
                print(f"Relay Error: {e}")

if __name__ == "__main__":
    # Start the Flask server in a background thread to satisfy Render's port binding
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Run the Discord self-bot
    try:
        client.run(os.getenv("USER_TOKEN"))
    except Exception as e:
        print(f"Failed to start bot: {e}")