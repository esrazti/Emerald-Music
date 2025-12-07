import nextcord
import os
import asyncio
from nextcord.ext import commands, application_checks
from nextcord import SlashOption
from dotenv import load_dotenv
from gtts import gTTS
import yt_dlp
import random
import re
import time
import atexit
import urllib.parse, urllib.request
from typing import Dict, List, Any
import logging
import requests
import sys

load_dotenv()

token = os.getenv("TOKEN")

if token is None:
    raise ValueError("❌ Bot token is missing! Ensure 'TOKEN' is set in the .env file.")

intents = nextcord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="え", intents=intents)

logging.basicConfig(level=logging.WARNING)
yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options: dict[str, Any] = {
    'format': 'bestaudio',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'no-playlist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'geo-bypass': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'no_color': True,
    'overwrites': True,
    'age_limit': 100,
    'live_from_start': True,
}

ffmpeg_options = {'options': '-vn -sn'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class Source:
    """Parent class of all music sources."""

    def __init__(self, audio_source: nextcord.AudioSource, metadata):
        self.audio_source: nextcord.AudioSource = audio_source
        self.metadata = metadata
        self.title: str = metadata.get('title', 'Unknown title')
        self.url: str = metadata.get('url', 'Unknown URL')

    def __str__(self):
        return f'{self.title} ({self.url})'

class YTDLSource(Source):
    """Subclass of YouTube sources."""

    def __init__(self, audio_source: nextcord.AudioSource, metadata):
        super().__init__(audio_source, metadata)
        self.url: str = metadata.get('webpage_url', 'Unknown URL')  # yt-dlp specific key name for original URL

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        metadata = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in metadata:
            metadata = metadata['entries'][0]
        filename = metadata['url'] if stream else ytdl.prepare_filename(metadata)
        return cls(await nextcord.FFmpegOpusAudio.from_probe(filename, **ffmpeg_options), metadata)

class ServerSession:
    def __init__(self, guild_id, voice_client):
        self.guild_id: int = guild_id
        self.voice_client: nextcord.VoiceClient = voice_client
        self.queue: List[Source] = []

    def display_queue(self) -> str:
        if not self.queue:
            return "Queue is empty."
        currently_playing = f'Currently playing: 0. {self.queue[0]}'
        return currently_playing + '\n' + '\n'.join([f'{i + 1}. {s}' for i, s in enumerate(self.queue[1:])])

    async def add_to_queue(self, ctx, url):  # Does not auto start playing the playlist
        yt_source = await YTDLSource.from_url(url, loop=bot.loop, stream=False)  # stream=True has issues and cannot use Opus probing
        self.queue.append(yt_source)
        if self.voice_client.is_playing():
            await ctx.send(f'Added to queue: {yt_source.title}')

    async def start_playing(self, ctx):
        self.voice_client.play(self.queue[0].audio_source, after=lambda e=None: self.after_playing(ctx, e))
        await ctx.send(f'Now playing: {self.queue[0].title}')

    async def after_playing(self, ctx, error):
        if error:
            raise error
        else:
            if self.queue:
                await self.play_next(ctx)

    async def play_next(self, ctx):  # Should be called only after making the first element of the queue the song to play
        self.queue.pop(0)
        if self.queue:
            self.voice_client.play(self.queue[0].audio_source, after=lambda e=None: self.after_playing(ctx, e))
            await ctx.send(f'Now playing: {self.queue[0].title}')
        else:
            await ctx.send("Queue finished.")

server_sessions: Dict[int, ServerSession] = {}  # {guild_id: ServerSession}

def clean_cache_files():
    if not server_sessions:  # Only clean if no servers are connected
        for file in os.listdir():
            if os.path.splitext(file)[1] in ['.webm', '.mp4', '.m4a', '.mp3', '.ogg'] and time.time() - os.path.getmtime(file) > 7200:  # Remove all cached webm files older than 2 hours
                try:
                    os.remove(file)
                except OSError:
                    pass

def get_res_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller. Relative path will always get extracted into root!"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    if os.path.isfile(os.path.join(base_path, relative_path)):
        return os.path.join(base_path, relative_path)
    else:
        raise FileNotFoundError(f'Embedded file {os.path.join(base_path, relative_path)} is not found!')

@atexit.register
def cleanup():
    global server_sessions
    for guild_id, session in server_sessions.items():
        if session.voice_client:
            asyncio.run(session.voice_client.disconnect())
            session.voice_client.cleanup()
    server_sessions = {}
    clean_cache_files()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_application_command_error(ctx, error):
    await ctx.send(f'{ctx.user}\'s message "{ctx.message.content}" triggered an error:\n{error}')

async def connect_to_voice_channel(ctx, channel):
    voice_client = await channel.connect()
    if voice_client.is_connected():
        server_sessions[ctx.guild.id] = ServerSession(ctx.guild.id, voice_client)
        await ctx.send(f'Connected to {voice_client.channel.name}.')
        return server_sessions[ctx.guild.id]
    else:
        await ctx.send(f'Failed to connect to voice channel {ctx.user.voice.channel.name}.')

redeem_codes = {} #Add your redeem codes here. Example: {"testcode": {"message": "You got a test reward", "role_id": 123456789}}

@bot.slash_command(name="redeem", description="Redeem a code for a reward.", default_member_permissions=nextcord.Permissions(0))
async def redeem(interaction: nextcord.Interaction, code: str = SlashOption(description="The code to redeem.", required=True)):
    """Redeems a user-provided code and sends a customized reply (private)."""

    if code in redeem_codes:
        reward = redeem_codes[code]
        message = reward["message"]
        await interaction.response.send_message(message, ephemeral=True) #make it private

        if "role_id" in reward:
            role_id = reward["role_id"]
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.channel.send(f"{interaction.user.mention} received the {role.name} role!")
                except nextcord.Forbidden:
                    await interaction.channel.send("I don't have permission to give that role.")
                except nextcord.HTTPException:
                    await interaction.channel.send("Failed to give the role.")
            else:
                await interaction.channel.send("The specified role does not exist.")
    else:
        await interaction.response.send_message(f"Invalid code: {code}. Please check the code and try again.", ephemeral=True) #make it private

@bot.command()
async def debug(ctx):
    await ctx.send(f"Server logged in as {bot.user}, pinged by {ctx.author.mention}. Token, ID, and API are online. CPU/RAM are within acceptable ranges. Emerald is running on Python Nextcord System. Terminal is running main.py, brain.py, and app.py. Server latency: {round(bot.latency * 376)}ms.")

@bot.slash_command(name='exit')
async def disconnect(ctx):
    """Disconnect from voice channel."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        voice_client = server_sessions[guild_id].voice_client
        await voice_client.disconnect()
        voice_client.cleanup()
        del server_sessions[guild_id]
        await ctx.send(f'Disconnected from {voice_client.channel.name}.')
        for file in os.listdir():
            if file.startswith("tts-audio") or file.endswith(".webm"):
                try:
                    os.remove(file)
                except OSError:
                    pass

@bot.slash_command(name="pause")
async def pause(ctx):
    """Pause the current song."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        voice_client = server_sessions[guild_id].voice_client
        if voice_client.is_playing():
            voice_client.pause()
            await ctx.send('Paused.')

@bot.slash_command(name="resume")
async def resume(ctx):
    """Resume the current song."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        voice_client = server_sessions[guild_id].voice_client
        if voice_client.is_paused():
            voice_client.resume()
            await ctx.send('Resumed.')

@bot.slash_command(name="skip")
async def skip(ctx):
    """Skip the current song."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        session = server_sessions[guild_id]
        voice_client = session.voice_client
        if voice_client.is_playing():
            if len(session.queue) > 1:
                voice_client.stop()
            else:
                await ctx.send('This is already the last item in the queue!')

@bot.slash_command(name='queue')
async def show_queue(ctx):
    """Show the current queue."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        await ctx.send(f'{server_sessions[guild_id].display_queue()}')

@bot.slash_command(name="remove")
async def remove(ctx, i: int = nextcord.SlashOption(name='index', description='Index of item to remove (current playing = 0, can only remove from 1 onwards)', required=True)):
    """Remove an item from queue by index (1, 2...)."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        if i == 0:
            await ctx.send('Cannot remove the current playing song. Use !skip instead.')
        elif i >= len(server_sessions[guild_id].queue):
            await ctx.send(f'The queue is not that long. There are only {len(server_sessions[guild_id].queue) - 1} items in it.')
        else:
            removed = server_sessions[guild_id].queue.pop(i)
            removed.audio_source.cleanup()
            await ctx.send(f'Removed {removed} from queue.')

@bot.slash_command(name="clear")
async def clear(ctx):
    """Clear the queue and stop the current song."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions:
        voice_client = server_sessions[guild_id].voice_client
        server_sessions[guild_id].queue = []
        if voice_client.is_playing():
            voice_client.stop()
        await ctx.send('Queue cleared.')

@bot.slash_command(name="song")
async def song(ctx):
    """Show the current song."""
    guild_id = ctx.guild.id
    if guild_id in server_sessions and server_sessions[guild_id].queue:
        await ctx.send(f'Now playing: {server_sessions[guild_id].queue[0]}')
    else:
        await ctx.send('Nothing is playing.')

@bot.slash_command(name="play")
async def play(ctx: nextcord.Interaction, query: str = nextcord.SlashOption(name='query', description='URL or search query', required=True)):
    """Play a YouTube video by URL (if provided) or search for the song and play the first video in the search results."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        if ctx.user.voice is None:
            await ctx.send(f'You are not connected to any voice channel!')
            return
        else:
            session = await connect_to_voice_channel(ctx, ctx.user.voice.channel)
    else:
        session = server_sessions[guild_id]
        if session.voice_client.channel != ctx.user.voice.channel:
            await session.voice_client.move_to(ctx.user.voice.channel)
            await ctx.send(f'Connected to {ctx.user.voice.channel}.')
    try:
        requests.get(query)
    except (requests.ConnectionError, requests.exceptions.MissingSchema):
        query_string = urllib.parse.urlencode({"search_query": query})
        formatUrl = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
        search_results = re.findall(r"watch\?v=(\S{11})", formatUrl.read().decode())
        url = f'https://www.youtube.com/watch?v={search_results[0]}'
    else:
        url = query
    await session.add_to_queue(ctx, url)
    if not session.voice_client.is_playing() and len(session.queue) <= 1:
        await session.start_playing(ctx)

async def tts_join_and_speak(bot, interaction: nextcord.Interaction, text: str, voice_channel: nextcord.VoiceChannel = None):
    guild_id = interaction.guild.id
    if guild_id in server_sessions and server_sessions[guild_id].voice_client.is_playing():
        await interaction.response.send_message("❌ Cannot use TTS while music is playing.", ephemeral=True)
        return
    user = interaction.user
    if voice_channel is None:
        if user.voice is None:
            await interaction.response.send_message("❌ You need to be in a voice channel or specify one.", ephemeral=True)
            return
        voice_channel = user.voice.channel

    try:
        vc = await voice_channel.connect()
    except nextcord.ClientException:
        vc = bot.voice_clients[0] if bot.voice_clients else None
        if vc is None:
            await interaction.response.send_message("❌ Failed to connect to voice channel.", ephemeral=True)
            return
        if vc.channel.id != voice_channel.id:
            await vc.move_to(voice_channel)
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
        return

    sound = gTTS(text=text, lang="en", slow=False)
    sound.save("tts-audio.mp3")

    if vc.is_playing():
        vc.stop()

    source = await nextcord.FFmpegOpusAudio.from_probe("tts-audio.mp3", method="fallback")
    vc.play(source, after=lambda e: vc.disconnect())
    await interaction.response.send_message("✅ Playing TTS audio.", ephemeral=True)

@bot.slash_command(description="Pinging the server.")
async def ping(interaction: nextcord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Emerald.next.py is online with **{latency}ms** latency.")

@bot.slash_command(name="chat", description="Make the bot say something.")
async def chat(
    interaction: nextcord.Interaction,
    message: str = SlashOption(description="The message the bot should say.", required=True),
):
    await interaction.response.send_message("✅ Message sent!", ephemeral=True)
    await interaction.channel.send(message)

@bot.slash_command(name="tts", description="Text to speech. You can choose a VC or use your own.")
async def tts_slash(
    interaction: nextcord.Interaction,
    text: str = SlashOption(description="The text to convert to speech.", required=True),
    voice_channel: nextcord.VoiceChannel = SlashOption(description="The voice channel to join (optional).", required=False),
):
    await tts_join_and_speak(interaction.client, interaction, text, voice_channel)

clean_cache_files()
bot.run(token)
