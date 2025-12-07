import nextcord
import os
import asyncio
from nextcord.ext import commands, application_checks, tasks
from nextcord import SlashOption
from dotenv import load_dotenv
from gtts import gTTS
import yt_dlp
import random
import re
import time
import atexit
import urllib.parse, urllib.request
from typing import Dict, List, Any, Union, Optional
import logging
from datetime import datetime, timedelta
import requests
import sys
from enum import Enum
import json
import aiofiles
import sqlite3

# Load environment variables from .env file
load_dotenv()

# Retrieve bot token from environment variables
token = os.getenv("E2TOKEN")

# Raise an error if the token is not found
if token is None:
    raise ValueError("❌ Bot token is missing! Ensure 'E2TOKEN' is set in the .env file.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configure Nextcord intents
intents = nextcord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# Initialize the bot with a command prefix and intents
bot = commands.Bot(command_prefix="え", intents=intents, help_command=None)

# Configure logging for yt-dlp to suppress warnings/info messages
yt_dlp.utils.bug_reports_message = lambda: ''

# yt-dlp options for audio extraction
ytdl_format_options: dict[str, Any] = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'no-playlist': False,
    'nocheckcertificate': True,
    'ignoreerrors': True,
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
    'extract_flat': False,
    'writethumbnail': False,
    'writeinfojson': False,
}

# FFmpeg options for audio processing
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -sn'
}

# Initialize YoutubeDL with the specified options
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Database setup
def init_database():
    """Initialize SQLite database for persistent data."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            commands_used INTEGER DEFAULT 0,
            songs_requested INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            default_volume REAL DEFAULT 0.5,
            max_queue_size INTEGER DEFAULT 100,
            auto_disconnect_timeout INTEGER DEFAULT 300,
            dj_role_id INTEGER,
            music_channel_id INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS redeemed_codes (
            user_id INTEGER,
            code TEXT,
            redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, code)
        )
    ''')
    
    conn.commit()
    conn.close()

init_database()

class Source:
    """Parent class for all music sources, holding common metadata."""
    def __init__(self, audio_source: nextcord.AudioSource, metadata: Dict[str, Any]):
        self.audio_source: nextcord.AudioSource = audio_source
        self.metadata = metadata
        self.title: str = metadata.get('title', 'Unknown title')
        self.url: str = metadata.get('url', 'Unknown URL')
        self.duration: int = metadata.get('duration', 0)
        self.thumbnail: str = metadata.get('thumbnail', '')
        self.requester: Optional[nextcord.Member] = None

    def __str__(self):
        return f'{self.title} ({self.url})'

class YTDLSource(Source):
    """Enhanced subclass for YouTube and YouTube Music sources."""
    def __init__(self, audio_source: nextcord.AudioSource, metadata: Dict[str, Any], file_path: str):
        super().__init__(audio_source, metadata)
        self.url: str = metadata.get('webpage_url', 'Unknown URL')
        self._file_path: str = file_path
        self.uploader: str = metadata.get('uploader', 'Unknown')
        self.view_count: int = metadata.get('view_count', 0)

    @classmethod
    async def from_url(cls, url: str, *, loop=None, stream: bool = False, is_search: bool = False, 
                      is_youtube_music_search: bool = False, requester: nextcord.Member = None) -> List['YTDLSource']:
        """Enhanced version with better error handling and metadata."""
        loop = loop or asyncio.get_event_loop()

        if is_search:
            if is_youtube_music_search:
                query_str = f"ytsearchm:{url}"
            else:
                query_str = f"ytsearch:{url}"
        else:
            query_str = url

        try:
            info = await loop.run_in_executor(None, lambda: ytdl.extract_info(query_str, download=not stream))

            sources = []
            if 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        try:
                            filename = entry['url'] if stream else ytdl.prepare_filename(entry)
                            audio_source = await nextcord.FFmpegOpusAudio.from_probe(filename, **ffmpeg_options)
                            source = cls(audio_source, entry, filename)
                            source.requester = requester
                            sources.append(source)
                        except Exception as e:
                            logger.warning(f"Could not process entry '{entry.get('title', 'Unknown')}': {e}")
            elif info:
                filename = info['url'] if stream else ytdl.prepare_filename(info)
                audio_source = await nextcord.FFmpegOpusAudio.from_probe(filename, **ffmpeg_options)
                source = cls(audio_source, info, filename)
                source.requester = requester
                sources.append(source)
            
            return sources
        except Exception as e:
            logger.error(f"yt-dlp error during extraction: {e}")
            return []

class LoopMode(Enum):
    NONE = 0
    SONG = 1
    QUEUE = 2
    RANDOM_CONTINUOUS = 3

class ServerSession:
    """Enhanced server session with more features."""
    def __init__(self, guild_id: int, voice_client: nextcord.VoiceClient):
        self.guild_id: int = guild_id
        self.voice_client: nextcord.VoiceClient = voice_client
        self.queue: List[Source] = []
        self.loop_mode: LoopMode = LoopMode.NONE
        self.current_song: Source | None = None
        self.bound_channel: nextcord.TextChannel | None = None
        self.volume: float = 0.5
        self.skip_votes: set = set()
        self.last_activity: datetime = datetime.now()
        self.auto_disconnect_task: Optional[asyncio.Task] = None
        self.history: List[Source] = []  # Keep track of played songs

    def display_queue(self, page: int = 1, items_per_page: int = 10) -> tuple[str, int]:
        """Returns a paginated formatted string of the current queue."""
        if not self.queue and not self.current_song:
            return "Queue is empty.", 1
        
        total_pages = max(1, (len(self.queue) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        currently_playing_str = ""
        if self.current_song:
            duration_str = self.format_duration(self.current_song.duration) if self.current_song.duration else "Live"
            requester_str = f" (requested by {self.current_song.requester.display_name})" if self.current_song.requester else ""
            currently_playing_str = f'🎵 **Now Playing:** [{self.current_song.title}]({self.current_song.url}) `{duration_str}`{requester_str}'
        else:
            currently_playing_str = "Nothing playing."
        
        queue_list = []
        for i in range(start_idx, min(end_idx, len(self.queue))):
            s = self.queue[i]
            duration_str = self.format_duration(s.duration) if s.duration else "Live"
            requester_str = f" - {s.requester.display_name}" if s.requester else ""
            queue_list.append(f'`{i + 1}.` [{s.title}]({s.url}) `{duration_str}`{requester_str}')
        
        queue_content = currently_playing_str
        if queue_list:
            queue_content += f'\n\n**Queue (Page {page}/{total_pages}):**\n' + '\n'.join(queue_list)
        
        if len(self.queue) > items_per_page:
            queue_content += f'\n\n*Showing {len(queue_list)} of {len(self.queue)} queued songs*'
            
        return queue_content, total_pages

    @staticmethod
    def format_duration(seconds: int) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS."""
        if seconds == 0:
            return "Live"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    async def add_to_queue(self, ctx: nextcord.Interaction, sources: List[Source]):
        """Enhanced add to queue with better feedback."""
        if not self.bound_channel:
            self.bound_channel = ctx.channel

        if not sources:
            await ctx.followup.send('❌ No songs were found or could be added.')
            return

        # Check queue size limit
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT max_queue_size FROM guild_settings WHERE guild_id = ?', (ctx.guild.id,))
        result = cursor.fetchone()
        max_queue_size = result[0] if result else 100
        conn.close()

        if len(self.queue) + len(sources) > max_queue_size:
            await ctx.followup.send(f'❌ Queue is full! Maximum queue size is {max_queue_size}.')
            return

        if len(sources) == 1:
            song_added = sources[0]
            self.queue.append(song_added)
            
            embed = nextcord.Embed(
                title="✅ Added to Queue",
                description=f"[{song_added.title}]({song_added.url})",
                color=nextcord.Color.green()
            )
            
            if song_added.duration:
                embed.add_field(name="Duration", value=self.format_duration(song_added.duration), inline=True)
            if song_added.requester:
                embed.add_field(name="Requested by", value=song_added.requester.mention, inline=True)
            embed.add_field(name="Queue Position", value=f"{len(self.queue)}", inline=True)
            
            if song_added.thumbnail:
                embed.set_thumbnail(url=song_added.thumbnail)
            
            await ctx.followup.send(embed=embed)
        else:
            # Handle playlist
            for song in sources:
                self.queue.append(song)

            embed = nextcord.Embed(
                title=f"✅ Added {len(sources)} Songs",
                description=f"From playlist to the queue.",
                color=nextcord.Color.green()
            )
            
            if sources[0].thumbnail:
                embed.set_thumbnail(url=sources[0].thumbnail)

            await ctx.followup.send(embed=embed)

        # Update user stats
        if hasattr(ctx, 'user') and ctx.user:
            await self.update_user_stats(ctx.user.id, ctx.guild.id, songs_requested=len(sources))

        # Start playing if nothing is currently playing
        if not self.voice_client.is_playing() and self.current_song is None:
            await self.start_playing()

    async def start_playing(self):
        """Enhanced start playing with better error handling."""
        if self.voice_client.is_playing():
            self.voice_client.stop()

        if self.loop_mode == LoopMode.RANDOM_CONTINUOUS and self.queue:
            random_index = random.randrange(len(self.queue))
            self.current_song = self.queue.pop(random_index)
        elif self.queue:
            self.current_song = self.queue.pop(0)
        else:
            self.current_song = None
            if self.bound_channel and self.loop_mode not in [LoopMode.QUEUE, LoopMode.RANDOM_CONTINUOUS]:
                embed = nextcord.Embed(
                    title="Queue Finished",
                    description="No more songs in queue.",
                    color=nextcord.Color.blue()
                )
                await self.bound_channel.send(embed=embed)
            return

        try:
            fresh_audio_source = await nextcord.FFmpegOpusAudio.from_probe(
                self.current_song._file_path, **ffmpeg_options
            )
            self.current_song.audio_source = fresh_audio_source
        except Exception as e:
            logger.error(f"Error re-probing audio source for {self.current_song.title}: {e}")
            if self.bound_channel:
                embed = nextcord.Embed(
                    title="❌ Playback Error",
                    description=f"Failed to load **{self.current_song.title}**. Skipping to next song.",
                    color=nextcord.Color.red()
                )
                await self.bound_channel.send(embed=embed)
            
            self.current_song = None
            if self.loop_mode == LoopMode.SONG:
                self.loop_mode = LoopMode.NONE
            
            await self.start_playing()
            return

        # Apply volume
        if hasattr(self.current_song.audio_source, 'volume'):
            self.current_song.audio_source.volume = self.volume

        self.voice_client.play(
            self.current_song.audio_source,
            after=lambda e=None: asyncio.run_coroutine_threadsafe(self.after_playing(e), bot.loop)
        )
        
        # Add to history
        if self.current_song not in self.history:
            self.history.append(self.current_song)
            if len(self.history) > 50:  # Keep only last 50 songs
                self.history.pop(0)

        # Update last activity
        self.last_activity = datetime.now()
        
        if self.bound_channel:
            embed = nextcord.Embed(
                title="🎵 Now Playing",
                description=f"[{self.current_song.title}]({self.current_song.url})",
                color=nextcord.Color.orange()
            )
            
            if self.current_song.duration:
                embed.add_field(name="Duration", value=self.format_duration(self.current_song.duration), inline=True)
            if self.current_song.requester:
                embed.add_field(name="Requested by", value=self.current_song.requester.mention, inline=True)
            if hasattr(self.current_song, 'uploader') and self.current_song.uploader:
                embed.add_field(name="Uploader", value=self.current_song.uploader, inline=True)
            
            if self.current_song.thumbnail:
                embed.set_thumbnail(url=self.current_song.thumbnail)

            await self.bound_channel.send(embed=embed)

    async def after_playing(self, error):
        """Enhanced after playing callback."""
        if error:
            logger.error(f"Playback error: {error}")
            if self.bound_channel:
                embed = nextcord.Embed(
                    title="❌ Playback Error",
                    description=f"An error occurred: {error}",
                    color=nextcord.Color.red()
                )
                await self.bound_channel.send(embed=embed)
            return

        # Clear skip votes
        self.skip_votes.clear()

        if self.loop_mode == LoopMode.SONG and self.current_song:
            await self.start_playing()
        elif self.loop_mode == LoopMode.QUEUE and self.current_song:
            finished_song = self.current_song
            self.queue.append(finished_song)
            self.current_song = None
            await self.start_playing()
        elif self.loop_mode == LoopMode.RANDOM_CONTINUOUS and self.current_song:
            finished_song = self.current_song
            self.queue.append(finished_song)
            self.current_song = None
            await self.start_playing()
        elif self.queue:
            await self.start_playing()
        else:
            self.current_song = None
            if self.bound_channel:
                embed = nextcord.Embed(
                    title="Queue Finished",
                    description="No more songs to play.",
                    color=nextcord.Color.blue()
                )
                await self.bound_channel.send(embed=embed)

    async def update_user_stats(self, user_id: int, guild_id: int, commands_used: int = 0, songs_requested: int = 0):
        """Update user statistics in database."""
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO user_stats (user_id, guild_id) VALUES (?, ?)
        ''', (user_id, guild_id))
        
        cursor.execute('''
            UPDATE user_stats 
            SET commands_used = commands_used + ?, 
                songs_requested = songs_requested + ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ? AND guild_id = ?
        ''', (commands_used, songs_requested, user_id, guild_id))
        
        conn.commit()
        conn.close()

# Dictionary to hold ServerSession objects for each guild
server_sessions: Dict[int, ServerSession] = {}

# Enhanced redeem codes system
async def load_redeem_codes():
    """Load redeem codes from JSON file."""
    try:
        if os.path.exists('redeem_codes.json'):
            async with aiofiles.open('redeem_codes.json', 'r') as f:
                content = await f.read()
                return json.loads(content)
        else:
            # Default codes
            default_codes = {
                "testcode": {"message": "test reward"},
                "IamImportantGuy": {"message": "You Got VIP role", "role_id": 849663098280345600},
                "JohnFreedom": {"message": "hahaha look funny clown! haha! I funny me clowny haha!", "role_id": 1323059158634860699},
                "GuLuemKhianChue": {"message": "Bro forgot his name", "role_id": 1348987205871206460},
                "ObserverIsObserving": {"message": "👁️ 👁️", "role_id": 1157312044161314939},
                "Brainrot": {"message": "You are my Sigma, Gay, Skibidi, GenAlpha, GigaChad, Nigga, Pedo, Brainrot, Crazy, Gambler, Furry, Gyatt", "role_id": 1296820911038660629},
                "gggggggggg": {"message": "Why i got ban from saying 5 gg?", "role_id": 1190637367531413554},
                "ミクミクビーム": {"message": "3 2 1 Ready! MIKU MIKU BEAMM!!!", "role_id": 1378979251914543175},
            }
            await save_redeem_codes(default_codes)
            return default_codes
    except Exception as e:
        logger.error(f"Error loading redeem codes: {e}")
        return {}

async def save_redeem_codes(codes: dict):
    """Save redeem codes to JSON file."""
    try:
        async with aiofiles.open('redeem_codes.json', 'w') as f:
            await f.write(json.dumps(codes, indent=2))
    except Exception as e:
        logger.error(f"Error saving redeem codes: {e}")

# Load redeem codes at startup
redeem_codes = {}

def clean_cache_files():
    """Enhanced cache cleaning with better error handling."""
    if server_sessions:
        return  # Don't clean while sessions are active

    cleaned_count = 0
    for file in os.listdir():
        try:
            if os.path.splitext(file)[1] in ['.webm', '.mp4', '.m4a', '.mp3', '.ogg', '.opus']:
                if time.time() - os.path.getmtime(file) > 3600:  # 1 hour
                    os.remove(file)
                    cleaned_count += 1
        except OSError as e:
            logger.warning(f"Failed to remove cached file {file}: {e}")
    
    if cleaned_count > 0:
        logger.info(f"Cleaned up {cleaned_count} cached files")

# Auto-disconnect task
@tasks.loop(minutes=5)
async def check_inactive_sessions():
    """Check for inactive voice sessions and disconnect them."""
    now = datetime.now()
    sessions_to_remove = []
    
    for guild_id, session in server_sessions.items():
        # Check if bot is alone in voice channel
        if len(session.voice_client.channel.members) <= 1:  # Only bot
            if now - session.last_activity > timedelta(minutes=5):
                sessions_to_remove.append(guild_id)
        # Check for general inactivity
        elif now - session.last_activity > timedelta(minutes=30):
            sessions_to_remove.append(guild_id)
    
    for guild_id in sessions_to_remove:
        session = server_sessions[guild_id]
        if session.bound_channel:
            embed = nextcord.Embed(
                title="Auto Disconnect",
                description="Disconnecting due to inactivity.",
                color=nextcord.Color.orange()
            )
            try:
                await session.bound_channel.send(embed=embed)
            except:
                pass  # Channel might be deleted
        
        try:
            await session.voice_client.disconnect()
            session.voice_client.cleanup()
        except:
            pass
        
        del server_sessions[guild_id]

@check_inactive_sessions.before_loop
async def before_check_inactive_sessions():
    await bot.wait_until_ready()

@atexit.register
def cleanup():
    """Enhanced cleanup function."""
    logger.info("Running atexit cleanup...")
    for guild_id, session in server_sessions.items():
        if session.voice_client:
            try:
                asyncio.run(session.voice_client.disconnect())
                session.voice_client.cleanup()
            except:
                pass
    server_sessions.clear()
    clean_cache_files()

@bot.event
async def on_ready():
    """Enhanced on_ready event with startup tasks."""
    global redeem_codes
    logger.info(f'✅ {bot.user} is now online!')
    
    # Load redeem codes
    redeem_codes = await load_redeem_codes()
    
    # Start background tasks
    check_inactive_sessions.start()
    
    # Initial cleanup
    clean_cache_files()
    
    # Update bot status
    await bot.change_presence(
        activity=nextcord.Activity(type=nextcord.ActivityType.listening, name="your commands!")
    )

@bot.event
async def on_application_command_error(ctx: nextcord.Interaction, error: Exception):
    """Enhanced global error handler."""
    logger.error(f"Command error in {ctx.command.name if ctx.command else 'unknown'}: {error}", exc_info=True)
    
    error_embed = nextcord.Embed(
        title="❌ Command Error",
        description="An unexpected error occurred while processing your command.",
        color=nextcord.Color.red()
    )
    
    if isinstance(error, commands.MissingPermissions):
        error_embed.description = "You don't have permission to use this command."
    elif isinstance(error, commands.BotMissingPermissions):
        error_embed.description = "I don't have the required permissions to execute this command."
    elif isinstance(error, commands.CommandOnCooldown):
        error_embed.description = f"This command is on cooldown. Try again in {error.retry_after:.1f}s."
    
    try:
        if ctx.response.is_done():
            await ctx.followup.send(embed=error_embed, ephemeral=True)
        else:
            await ctx.response.send_message(embed=error_embed, ephemeral=True)
    except:
        pass  # Interaction might have expired

@bot.event
async def on_voice_state_update(member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
    """Handle voice state updates to update activity tracking."""
    if member.bot:
        return
    
    guild_id = member.guild.id
    if guild_id in server_sessions:
        session = server_sessions[guild_id]
        if before.channel == session.voice_client.channel or after.channel == session.voice_client.channel:
            session.last_activity = datetime.now()

# Enhanced command implementations

@bot.slash_command(name="play", description="Play music from YouTube or search for a song")
@commands.cooldown(1, 3, commands.BucketType.user)
async def play(ctx: nextcord.Interaction, 
               query: str = SlashOption(description="URL or search query", required=True)):
    """Enhanced play command with better feedback and error handling."""
    await ctx.response.defer()
    
    guild_id = ctx.guild.id
    session = None

    # Voice connection logic
    if guild_id not in server_sessions:
        if not ctx.user.voice:
            embed = nextcord.Embed(
                title="❌ Voice Channel Required",
                description="You need to be in a voice channel to use this command!",
                color=nextcord.Color.red()
            )
            await ctx.followup.send(embed=embed)
            return
        
        try:
            voice_client = await ctx.user.voice.channel.connect()
            session = ServerSession(guild_id, voice_client)
            session.bound_channel = ctx.channel
            server_sessions[guild_id] = session
            
            embed = nextcord.Embed(
                title="🔗 Connected",
                description=f"Connected to {voice_client.channel.name}",
                color=nextcord.Color.green()
            )
            await ctx.followup.send(embed=embed, delete_after=5)
        except Exception as e:
            logger.error(f"Failed to connect to voice channel: {e}")
            embed = nextcord.Embed(
                title="❌ Connection Failed",
                description="Failed to connect to voice channel.",
                color=nextcord.Color.red()
            )
            await ctx.followup.send(embed=embed)
            return
    else:
        session = server_sessions[guild_id]
        if ctx.user.voice and session.voice_client.channel != ctx.user.voice.channel:
            await session.voice_client.move_to(ctx.user.voice.channel)
            embed = nextcord.Embed(
                title="🔄 Moved",
                description=f"Moved to {ctx.user.voice.channel.name}",
                color=nextcord.Color.blue()
            )
            await ctx.followup.send(embed=embed, delete_after=5)

    # Determine search type
    is_url = query.startswith(("http://", "https://"))
    is_youtube_music_search = False
    
    if not is_url:
        query_lower = query.lower()
        if query_lower.startswith(("ytm:", "youtube music:")):
            is_youtube_music_search = True
            query = query[query_lower.find(":") + 1:].strip()

    try:
        sources = await YTDLSource.from_url(
            query, 
            loop=bot.loop, 
            stream=False,
            is_search=not is_url,
            is_youtube_music_search=is_youtube_music_search,
            requester=ctx.user
        )
        
        if not sources:
            embed = nextcord.Embed(
                title="❌ No Results",
                description=f"Could not find any results for: `{query}`",
                color=nextcord.Color.red()
            )
            await ctx.followup.send(embed=embed)
            return
        
        await session.add_to_queue(ctx, sources)
        await session.update_user_stats(ctx.user.id, ctx.guild.id, commands_used=1)
        
    except Exception as e:
        logger.error(f"Error in play command: {e}")
        embed = nextcord.Embed(
            title="❌ Playback Error",
            description=f"An error occurred while trying to play: {str(e)[:100]}...",
            color=nextcord.Color.red()
        )
        await ctx.followup.send(embed=embed)

@bot.slash_command(name="queue", description="Show the current music queue")
async def show_queue(ctx: nextcord.Interaction, 
                    page: int = SlashOption(description="Page number", required=False, default=1)):
    """Enhanced queue command with pagination."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    queue_content, total_pages = session.display_queue(page)

    embed = nextcord.Embed(
        title="🎵 Music Queue",
        description=queue_content,
        color=nextcord.Color.purple()
    )
    
    if total_pages > 1:
        embed.set_footer(text=f"Page {page}/{total_pages} • Use /queue <page> to view other pages")
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="skip", description="Skip the current song or vote to skip")
async def skip(ctx: nextcord.Interaction):
    """Enhanced skip command with vote skipping."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    if not session.voice_client.is_playing():
        embed = nextcord.Embed(
            title="❌ Nothing Playing",
            description="No song is currently playing to skip.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    # Check if user has DJ permissions or is alone with bot
    voice_channel = session.voice_client.channel
    human_members = [m for m in voice_channel.members if not m.bot]
    
    # Skip immediately if only one human or user has manage_channels permission
    if len(human_members) <= 1 or ctx.user.guild_permissions.manage_channels:
        session.voice_client.stop()
        embed = nextcord.Embed(
            title="⏭️ Skipped",
            description=f"Skipped **{session.current_song.title}**",
            color=nextcord.Color.green()
        )
        await ctx.response.send_message(embed=embed)
        return
    
    # Vote skip system
    if ctx.user.id in session.skip_votes:
        embed = nextcord.Embed(
            title="❌ Already Voted",
            description="You have already voted to skip this song.",
            color=nextcord.Color.orange()
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    
    session.skip_votes.add(ctx.user.id)
    votes_needed = len(human_members) // 2 + 1
    
    if len(session.skip_votes) >= votes_needed:
        session.voice_client.stop()
        embed = nextcord.Embed(
            title="⏭️ Vote Skip Successful",
            description=f"Skipped **{session.current_song.title}** ({len(session.skip_votes)}/{votes_needed} votes)",
            color=nextcord.Color.green()
        )
    else:
        embed = nextcord.Embed(
            title="🗳️ Skip Vote Added",
            description=f"Vote added! ({len(session.skip_votes)}/{votes_needed} votes needed)",
            color=nextcord.Color.blue()
        )
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="pause", description="Pause the current song")
async def pause(ctx: nextcord.Interaction):
    """Pause command with better feedback."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    voice_client = server_sessions[guild_id].voice_client
    if voice_client.is_playing():
        voice_client.pause()
        embed = nextcord.Embed(
            title="⏸️ Paused",
            description="Music has been paused.",
            color=nextcord.Color.orange()
        )
    else:
        embed = nextcord.Embed(
            title="❌ Nothing Playing",
            description="No music is currently playing to pause.",
            color=nextcord.Color.red()
        )
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="resume", description="Resume the paused song")
async def resume(ctx: nextcord.Interaction):
    """Resume command with better feedback."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    voice_client = server_sessions[guild_id].voice_client
    if voice_client.is_paused():
        voice_client.resume()
        embed = nextcord.Embed(
            title="▶️ Resumed",
            description="Music has been resumed.",
            color=nextcord.Color.green()
        )
    else:
        embed = nextcord.Embed(
            title="❌ Not Paused",
            description="Music is not currently paused.",
            color=nextcord.Color.red()
        )
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="volume", description="Set the music volume (0-100)")
async def volume(ctx: nextcord.Interaction, 
                volume: int = SlashOption(description="Volume level (0-100)", required=True, min_value=0, max_value=100)):
    """Set the music volume."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    session.volume = volume / 100.0
    
    # Apply volume to current song if playing
    if session.current_song and hasattr(session.current_song.audio_source, 'volume'):
        session.current_song.audio_source.volume = session.volume
    
    embed = nextcord.Embed(
        title="🔊 Volume Changed",
        description=f"Volume set to **{volume}%**",
        color=nextcord.Color.blue()
    )
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="nowplaying", description="Show the currently playing song")
async def nowplaying(ctx: nextcord.Interaction):
    """Show current song with enhanced information."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions or not server_sessions[guild_id].current_song:
        embed = nextcord.Embed(
            title="❌ Nothing Playing",
            description="No song is currently playing.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    song = session.current_song
    
    embed = nextcord.Embed(
        title="🎵 Now Playing",
        description=f"[{song.title}]({song.url})",
        color=nextcord.Color.blue()
    )
    
    if song.duration:
        embed.add_field(name="Duration", value=session.format_duration(song.duration), inline=True)
    if song.requester:
        embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
    if hasattr(song, 'uploader') and song.uploader:
        embed.add_field(name="Uploader", value=song.uploader, inline=True)
    if hasattr(song, 'view_count') and song.view_count:
        embed.add_field(name="Views", value=f"{song.view_count:,}", inline=True)
    
    # Loop mode indicator
    loop_text = {
        LoopMode.NONE: "Off",
        LoopMode.SONG: "Current Song",
        LoopMode.QUEUE: "Queue",
        LoopMode.RANDOM_CONTINUOUS: "Random"
    }
    embed.add_field(name="Loop Mode", value=loop_text[session.loop_mode], inline=True)
    embed.add_field(name="Volume", value=f"{int(session.volume * 100)}%", inline=True)
    
    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="remove", description="Remove a song from the queue")
async def remove(ctx: nextcord.Interaction, 
                position: int = SlashOption(description="Position in queue to remove", required=True, min_value=1)):
    """Remove a song from the queue."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    if position > len(session.queue):
        embed = nextcord.Embed(
            title="❌ Invalid Position",
            description=f"Queue only has {len(session.queue)} songs.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    removed_song = session.queue.pop(position - 1)
    embed = nextcord.Embed(
        title="🗑️ Song Removed",
        description=f"Removed **{removed_song.title}** from position {position}",
        color=nextcord.Color.green()
    )
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="clear", description="Clear the entire queue")
async def clear(ctx: nextcord.Interaction):
    """Clear the music queue."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    cleared_count = len(session.queue)
    session.queue.clear()
    session.loop_mode = LoopMode.NONE
    
    embed = nextcord.Embed(
        title="🗑️ Queue Cleared",
        description=f"Removed {cleared_count} songs from the queue.",
        color=nextcord.Color.green()
    )
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="shuffle", description="Shuffle the current queue")
async def shuffle(ctx: nextcord.Interaction):
    """Shuffle the music queue."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    if len(session.queue) < 2:
        embed = nextcord.Embed(
            title="❌ Not Enough Songs",
            description="Need at least 2 songs in queue to shuffle.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    random.shuffle(session.queue)
    embed = nextcord.Embed(
        title="🔀 Queue Shuffled",
        description=f"Shuffled {len(session.queue)} songs in the queue.",
        color=nextcord.Color.green()
    )
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="loop", description="Set loop mode for the music player")
async def loop(ctx: nextcord.Interaction,
              mode: str = SlashOption(
                  description="Loop mode",
                  required=True,
                  choices=["off", "song", "queue", "random"]
              )):
    """Enhanced loop command."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ No Active Session",
            description="No music session is currently active.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    
    mode_map = {
        "off": (LoopMode.NONE, "Loop disabled"),
        "song": (LoopMode.SONG, "Looping current song"),
        "queue": (LoopMode.QUEUE, "Looping entire queue"),
        "random": (LoopMode.RANDOM_CONTINUOUS, "Random continuous playback enabled")
    }
    
    loop_mode, description = mode_map[mode]
    
    if mode == "song" and not session.current_song:
        embed = nextcord.Embed(
            title="❌ No Current Song",
            description="No song is currently playing to loop.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return
    
    if mode in ["queue", "random"] and not (session.queue or session.current_song):
        embed = nextcord.Embed(
            title="❌ Empty Queue",
            description="Queue is empty. Add songs first.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return
    
    session.loop_mode = loop_mode
    embed = nextcord.Embed(
        title="🔄 Loop Mode Changed",
        description=description,
        color=nextcord.Color.blue()
    )
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="disconnect", description="Disconnect the bot from voice channel")
async def disconnect(ctx: nextcord.Interaction):
    """Enhanced disconnect command."""
    guild_id = ctx.guild.id
    if guild_id not in server_sessions:
        embed = nextcord.Embed(
            title="❌ Not Connected",
            description="Bot is not connected to any voice channel.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed)
        return

    session = server_sessions[guild_id]
    channel_name = session.voice_client.channel.name
    
    await session.voice_client.disconnect()
    session.voice_client.cleanup()
    del server_sessions[guild_id]
    
    embed = nextcord.Embed(
        title="👋 Disconnected",
        description=f"Disconnected from **{channel_name}**",
        color=nextcord.Color.blue()
    )
    await ctx.response.send_message(embed=embed)
    
    # Clean up audio files
    clean_cache_files()

@bot.slash_command(name="stats", description="Show user statistics")
async def stats(ctx: nextcord.Interaction, 
               user: nextcord.Member = SlashOption(description="User to check stats for", required=False)):
    """Show user statistics."""
    target_user = user or ctx.user
    
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT commands_used, songs_requested, first_seen, last_seen 
        FROM user_stats 
        WHERE user_id = ? AND guild_id = ?
    ''', (target_user.id, ctx.guild.id))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        embed = nextcord.Embed(
            title="📊 User Statistics",
            description=f"No statistics found for {target_user.display_name}",
            color=nextcord.Color.orange()
        )
    else:
        commands_used, songs_requested, first_seen, last_seen = result
        embed = nextcord.Embed(
            title=f"📊 Statistics for {target_user.display_name}",
            color=nextcord.Color.blue()
        )
        embed.add_field(name="Commands Used", value=str(commands_used), inline=True)
        embed.add_field(name="Songs Requested", value=str(songs_requested), inline=True)
        embed.add_field(name="First Seen", value=first_seen[:10], inline=True)
        embed.set_thumbnail(url=target_user.display_avatar.url)
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="redeem", description="Redeem a special code")
async def redeem(ctx: nextcord.Interaction, 
                code: str = SlashOption(description="Code to redeem", required=True)):
    """Enhanced redeem system with tracking."""
    if code not in redeem_codes:
        embed = nextcord.Embed(
            title="❌ Invalid Code",
            description="The provided code is invalid or expired.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check if already redeemed
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM redeemed_codes WHERE user_id = ? AND code = ?', (ctx.user.id, code))
    if cursor.fetchone():
        embed = nextcord.Embed(
            title="❌ Already Redeemed",
            description="You have already redeemed this code.",
            color=nextcord.Color.orange()
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)
        conn.close()
        return
    
    # Add to redeemed codes
    cursor.execute('INSERT INTO redeemed_codes (user_id, code) VALUES (?, ?)', (ctx.user.id, code))
    conn.commit()
    conn.close()
    
    reward = redeem_codes[code]
    embed = nextcord.Embed(
        title="✅ Code Redeemed",
        description=reward["message"],
        color=nextcord.Color.green()
    )
    await ctx.response.send_message(embed=embed, ephemeral=True)
    
    # Give role if specified
    if "role_id" in reward:
        role = ctx.guild.get_role(reward["role_id"])
        if role:
            try:
                await ctx.user.add_roles(role)
                await ctx.channel.send(f"🎉 {ctx.user.mention} received the **{role.name}** role!")
            except nextcord.Forbidden:
                await ctx.channel.send("❌ I don't have permission to assign that role.")
            except Exception as e:
                logger.error(f"Error assigning role: {e}")

@bot.slash_command(name="tts", description="Text to speech in voice channel")
async def tts(ctx: nextcord.Interaction,
             text: str = SlashOption(description="Text to speak", required=True),
             channel: nextcord.VoiceChannel = SlashOption(description="Voice channel", required=False)):
    """Enhanced TTS with better error handling."""
    if not ctx.user.voice and not channel:
        embed = nextcord.Embed(
            title="❌ Voice Channel Required",
            description="You need to be in a voice channel or specify one.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    
    target_channel = channel or ctx.user.voice.channel
    
    # Check if music is playing
    guild_id = ctx.guild.id
    if guild_id in server_sessions and server_sessions[guild_id].voice_client.is_playing():
        embed = nextcord.Embed(
            title="❌ Music Playing",
            description="Cannot use TTS while music is playing.",
            color=nextcord.Color.red()
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    
    await ctx.response.defer(ephemeral=True)
    
    try:
        # Connect to voice if needed
        voice_client = ctx.guild.voice_client
        if not voice_client:
            voice_client = await target_channel.connect()
        elif voice_client.channel != target_channel:
            await voice_client.move_to(target_channel)
        
        # Generate TTS
        tts = gTTS(text=text, lang="th", slow=False)
        filename = f"tts_{ctx.user.id}_{int(time.time())}.mp3"
        tts.save(filename)
        
        # Play TTS
        if voice_client.is_playing():
            voice_client.stop()
        
        source = await nextcord.FFmpegOpusAudio.from_probe(filename)
        voice_client.play(source)
        
        embed = nextcord.Embed(
            title="🔊 TTS Playing",
            description=f"Playing TTS in {target_channel.name}",
            color=nextcord.Color.green()
        )
        await ctx.followup.send(embed=embed)
        
        # Clean up file after playing
        while voice_client.is_playing():
            await asyncio.sleep(1)
        
        try:
            os.remove(filename)
        except:
            pass
        
        if guild_id not in server_sessions:
            await voice_client.disconnect()
        
    except Exception as e:
        logger.error(f"TTS error: {e}")
        embed = nextcord.Embed(
            title="❌ TTS Error",
            description="Failed to generate or play TTS.",
            color=nextcord.Color.red()
        )
        await ctx.followup.send(embed=embed)

@bot.slash_command(name="ping", description="Check bot latency")
async def ping(ctx: nextcord.Interaction):
    """Enhanced ping command."""
    latency = round(bot.latency * 1000)
    
    # Determine latency status
    if latency < 100:
        status = "Excellent"
        color = nextcord.Color.green()
    elif latency < 200:
        status = "Good"
        color = nextcord.Color.orange()
    else:
        status = "Poor"
        color = nextcord.Color.red()
    
    embed = nextcord.Embed(
        title="🏓 Pong!",
        description=f"**{latency}ms** - {status}",
        color=color
    )
    embed.add_field(name="Guilds", value=len(bot.guilds), inline=True)
    embed.add_field(name="Active Sessions", value=len(server_sessions), inline=True)
    
    await ctx.response.send_message(embed=embed)

@bot.slash_command(name="help", description="Show help information")
async def help_command(ctx: nextcord.Interaction, 
                      category: str = SlashOption(
                          description="Help category",
                          required=False,
                          choices=["music", "utility", "fun"]
                      )):
    """Enhanced help command with categories."""
    if not category:
        embed = nextcord.Embed(
            title="🤖 Bot Help",
            description="Select a category to see available commands:",
            color=nextcord.Color.blue()
        )
        embed.add_field(
            name="🎵 Music Commands",
            value="Use `/help music` to see music-related commands",
            inline=False
        )
        embed.add_field(
            name="🔧 Utility Commands", 
            value="Use `/help utility` to see utility commands",
            inline=False
        )
        embed.add_field(
            name="🎉 Fun Commands",
            value="Use `/help fun` to see fun commands", 
            inline=False
        )
    elif category == "music":
        embed = nextcord.Embed(
            title="🎵 Music Commands",
            color=nextcord.Color.blue()
        )
        music_commands = [
            ("/play", "Play music from YouTube or search"),
            ("/queue", "Show the current music queue"),
            ("/skip", "Skip the current song"),
            ("/pause", "Pause the current song"),
            ("/resume", "Resume paused music"),
            ("/volume", "Set music volume (0-100)"),
            ("/nowplaying", "Show currently playing song"),
            ("/loop", "Set loop mode (off/song/queue/random)"),
            ("/shuffle", "Shuffle the queue"),
            ("/remove", "Remove a song from queue"),
            ("/clear", "Clear the entire queue"),
            ("/disconnect", "Disconnect from voice channel")
        ]
        for cmd, desc in music_commands:
            embed.add_field(name=cmd, value=desc, inline=False)
    elif category == "utility":
        embed = nextcord.Embed(
            title="🔧 Utility Commands",
            color=nextcord.Color.green()
        )
        utility_commands = [
            ("/ping", "Check bot latency"),
            ("/stats", "Show user statistics"),
            ("/help", "Show this help message")
        ]
        for cmd, desc in utility_commands:
            embed.add_field(name=cmd, value=desc, inline=False)
    elif category == "fun":
        embed = nextcord.Embed(
            title="🎉 Fun Commands",
            color=nextcord.Color.orange()
        )
        fun_commands = [
            ("/tts", "Text to speech in voice channel"),
            ("/redeem", "Redeem special codes")
        ]
        for cmd, desc in fun_commands:
            embed.add_field(name=cmd, value=desc, inline=False)
    
    await ctx.response.send_message(embed=embed)

if __name__ == "__main__":
    logger.info("Starting bot...")
    bot.run(token)
