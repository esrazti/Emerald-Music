import nextcord
import os
import asyncio
import json
import time
import logging
import sys
import atexit
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from enum import Enum
from collections import deque
from contextlib import suppress
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import random

import yt_dlp
from gtts import gTTS
from ytmusicapi import YTMusic
from nextcord.ext import commands, tasks
from nextcord import SlashOption, Embed, Color, ui, ButtonStyle
from dotenv import load_dotenv

# ================== Configuration ==================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

class Config:
    TOKEN = os.getenv("TOKEN")
    DEFAULT_PREFIX = "!"
    MAX_QUEUE_SIZE = 2500 #Song limit in queue
    MAX_SONG_DURATION = 10800 # in seconds (3 hours)
    CACHE_CLEANUP_INTERVAL = 10800 #Clear file in downloads folder every 3 hours
    DEFAULT_VOLUME = 0.25
    PRELOAD_COUNT = 48 #Number of songs to preload
    MAX_DOWNLOAD_WORKERS = 24 
    MAX_RAM_MB = 8192
    RADIO_PRELOAD = 25
    
    # Features
    ENABLE_CONSOLE_MODE = True
    CONSOLE_REFRESH_RATE = 0.5
    CONSOLE_EPHEMERAL = True
    ENABLE_CROSSFADE = True
    CROSSFADE_DURATION = 6.0
    
    # Background Music
    ENABLE_BG_MUSIC = True
    BG_MUSIC_FOLDER = "bgmusic"
    BG_MUSIC_VOLUME = DEFAULT_VOLUME/5
    BG_MUSIC_IDLE_DELAY = 1.5  
    
    # Theme Colors
    THEME_MAIN = Color.from_rgb(89, 152, 255)    # Signature blue
    THEME_SUB = Color.from_rgb(147, 112, 219)    # Accent purple
    THEME_BG = Color.from_rgb(31, 41, 55)        # Dark background
    
    if not TOKEN:
        logger.critical("Bot token missing!")
        sys.exit(1)

# ================== YT-DLP Configuration ==================
class YTDLConfig:
    OPTIONS = {
        'format': 'bestaudio[ext=webm]/bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'restrictfilenames': False,
        'noplaylist': False,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0',
        'concurrent_fragment_downloads': 16,
        'buffersize': 8388608,
        'http_chunk_size': 4194304,
        'retries': 10,
        'fragment_retries': 10,
        'skip_unavailable_fragments': True,
        'noprogress': True,
        'cookiefile': 'cookies.txt',
        'extractor_args': {'youtube': {
            'player_client': ['android', 'web'],
            'skip': ['hls', 'dash']
        }},
    }

ytdl = yt_dlp.YoutubeDL(YTDLConfig.OPTIONS)
ytmusic = YTMusic()

# ================== Enums ==================
class LoopMode(Enum):
    NONE = "off"
    SONG = "song"
    QUEUE = "queue"
    RANDOM = "random"

class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"
    BG_MUSIC = "background"

# ================== Console Control View ==================
class ConsoleControlView(ui.View):
    def __init__(self, session, bot_instance):
        super().__init__(timeout=None)
        self.session = session
        self.bot = bot_instance
    
    @ui.button(label="⏸️", style=ButtonStyle.primary, custom_id="pause_btn")
    async def pause_button(self, button: ui.Button, interaction: nextcord.Interaction):
        if self.session.voice_client.is_playing():
            self.session.pause()
            await interaction.response.send_message("⏸️ Paused", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
        else:
            await interaction.response.send_message("❌ Nothing playing", ephemeral=True, delete_after=2)
    
    @ui.button(label="▶️", style=ButtonStyle.success, custom_id="resume_btn")
    async def resume_button(self, button: ui.Button, interaction: nextcord.Interaction):
        if self.session.voice_client.is_paused():
            self.session.resume()
            await interaction.response.send_message("▶️ Resumed", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
        else:
            await interaction.response.send_message("❌ Already playing", ephemeral=True, delete_after=2)
    
    @ui.button(label="⏭️", style=ButtonStyle.secondary, custom_id="skip_btn")
    async def skip_button(self, button: ui.Button, interaction: nextcord.Interaction):
        if self.session.current:
            self.session.skip()
            await interaction.response.send_message("⏭️ Skipped", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
        else:
            await interaction.response.send_message("❌ Nothing to skip", ephemeral=True, delete_after=2)
    
    @ui.button(label="🔁", style=ButtonStyle.secondary, custom_id="loop_btn")
    async def loop_button(self, button: ui.Button, interaction: nextcord.Interaction):
        modes = [LoopMode.NONE, LoopMode.SONG, LoopMode.QUEUE, LoopMode.RANDOM]
        current_idx = modes.index(self.session.loop_mode)
        next_mode = modes[(current_idx + 1) % len(modes)]
        self.session.loop_mode = next_mode
        
        mode_names = {
            LoopMode.NONE: "Off",
            LoopMode.SONG: "Song",
            LoopMode.QUEUE: "Queue",
            LoopMode.RANDOM: "Random"
        }
        await interaction.response.send_message(f"🔁 Loop: {mode_names[next_mode]}", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
    
    @ui.button(label="📻", style=ButtonStyle.secondary, custom_id="radio_btn")
    async def radio_button(self, button: ui.Button, interaction: nextcord.Interaction):
        if not self.session.current:
            await interaction.response.send_message("❌ Play a song first", ephemeral=True, delete_after=2)
            return
        
        if self.session.radio_mode:
            self.session.disable_radio_mode()
            await interaction.response.send_message("📻 Radio disabled", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
        else:
            await self.session.enable_radio_mode(self.session.current.video_id)
            await interaction.response.send_message("📻 Radio enabled", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
    
    @ui.button(label="🔀", style=ButtonStyle.secondary, custom_id="shuffle_btn")
    async def shuffle_button(self, button: ui.Button, interaction: nextcord.Interaction):
        if self.session.queue:
            self.session.shuffle()
            await interaction.response.send_message(f"🔀 Shuffled {len(self.session.queue)} songs", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
        else:
            await interaction.response.send_message("❌ Queue is empty", ephemeral=True, delete_after=2)
    
    @ui.button(label="🗑️", style=ButtonStyle.danger, custom_id="clear_btn")
    async def clear_button(self, button: ui.Button, interaction: nextcord.Interaction):
        queue_size = len(self.session.queue)
        self.session.clear_queue()
        await interaction.response.send_message(f"🗑️ Cleared {queue_size} songs", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)
    
    @ui.button(label="👋", style=ButtonStyle.danger, custom_id="leave_btn")
    async def leave_button(self, button: ui.Button, interaction: nextcord.Interaction):
        await self.bot.session_manager.destroy_session(interaction.guild.id)
        await interaction.response.send_message("👋 Disconnected", ephemeral=Config.CONSOLE_EPHEMERAL, delete_after=2)

# ================== AudioSource Class ==================
class AudioSource:
    def __init__(self, data: dict):
        self.data = data
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('webpage_url', data.get('url', ''))
        self.video_id = data.get('id', 'unknown')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail', '')
        self.uploader = data.get('uploader', 'Unknown')
        
        ext = data.get('ext', 'webm')
        self.filepath = f"downloads/{self.video_id}.{ext}"
        self.is_downloaded = False
        self.download_task = None

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop=None, download=True, is_playlist=False):
        loop = loop or asyncio.get_event_loop()
        
        if not search.startswith(('http://', 'https://')):
            if search.lower().startswith(('ytm:', 'youtube music:')):
                search = f"ytsearch:{search.split(':', 1)[1].strip()}"
            else:
                search = f"ytsearch:{search}"
        
        try:
            if is_playlist or ('playlist' in search.lower() or 'list=' in search):
                ytdl_flat = yt_dlp.YoutubeDL({**YTDLConfig.OPTIONS, 'extract_flat': 'in_playlist'})
                data = await loop.run_in_executor(None, partial(ytdl_flat.extract_info, search, download=False))
                
                if not data:
                    raise RuntimeError("Unable to extract playlist")
                
                sources = []
                if 'entries' in data:
                    for entry in data['entries']:
                        if entry:
                            minimal_source = cls.__new__(cls)
                            minimal_source.title = entry.get('title', 'Unknown')
                            minimal_source.url = entry.get('url') or entry.get('webpage_url') or f"https://youtube.com/watch?v={entry.get('id')}"
                            minimal_source.video_id = entry.get('id', 'unknown')
                            minimal_source.duration = entry.get('duration', 0)
                            minimal_source.thumbnail = entry.get('thumbnail', '')
                            minimal_source.uploader = entry.get('uploader', 'Unknown')
                            minimal_source.filepath = None
                            minimal_source.is_downloaded = False
                            minimal_source.download_task = None
                            minimal_source.data = entry
                            sources.append(minimal_source)
                
                if download and sources:
                    await sources[0].download(loop)
                
                return sources
            else:
                data = await loop.run_in_executor(None, partial(ytdl.extract_info, search, download=False))
                
                if not data:
                    raise RuntimeError("Unable to extract info")

                sources = []
                if 'entries' in data:
                    for entry in data['entries']:
                        if entry:
                            sources.append(cls(entry))
                else:
                    sources.append(cls(data))
                
                if download and sources:
                    await sources[0].download(loop)
                
                return sources
                
        except Exception as e:
            logger.error(f"Error extracting '{search}': {e}")
            if hasattr(ctx, 'followup'):
                await ctx.followup.send(f"❌ エラー: {str(e)[:100]}")
            raise

    async def download(self, loop=None):
        if self.is_downloaded or self.download_task:
            return await self.download_task if self.download_task else None
        
        loop = loop or asyncio.get_event_loop()
        
        async def _download():
            try:
                logger.info(f"Downloading: {self.title[:50]}")
                await loop.run_in_executor(None, partial(ytdl.extract_info, self.url, download=True))
                
                for ext in ['webm', 'opus', 'm4a', 'mp4', 'mp3', 'mkv']:
                    alt_path = f"downloads/{self.video_id}.{ext}"
                    if os.path.exists(alt_path):
                        self.filepath = alt_path
                        self.is_downloaded = True
                        logger.info(f"✓ Downloaded: {self.title[:50]}")
                        return
                
                raise RuntimeError(f"File not found: {self.video_id}")
            except Exception as e:
                logger.error(f"Download error: {e}")
                self.is_downloaded = False
                self.download_task = None
                raise
        
        self.download_task = asyncio.create_task(_download())
        await self.download_task

    def create_ffmpeg_source(self, volume: float = 1.0):
        if not self.filepath or not os.path.exists(self.filepath):
            for ext in ['webm', 'opus', 'm4a', 'mp4', 'mp3', 'mkv']:
                alt_path = f"downloads/{self.video_id}.{ext}"
                if os.path.exists(alt_path):
                    self.filepath = alt_path
                    break
            else:
                raise RuntimeError(f"File not found: {self.video_id}")

        return nextcord.FFmpegPCMAudio(os.path.abspath(self.filepath), options='-vn')

# ================== Background Music Manager ==================
class BackgroundMusicManager:
    def __init__(self):
        self.bg_tracks = []
        self.current_index = 0
        self.load_bg_music()
    
    def load_bg_music(self):
        """Load all background music files from folder"""
        if not os.path.exists(Config.BG_MUSIC_FOLDER):
            os.makedirs(Config.BG_MUSIC_FOLDER)
            logger.info(f"Created {Config.BG_MUSIC_FOLDER} folder")
            return
        
        supported_formats = ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.webm', '.opus')
        for file in os.listdir(Config.BG_MUSIC_FOLDER):
            if file.lower().endswith(supported_formats):
                self.bg_tracks.append(os.path.join(Config.BG_MUSIC_FOLDER, file))
        
        if self.bg_tracks:
            random.shuffle(self.bg_tracks)
            logger.info(f"Loaded {len(self.bg_tracks)} background tracks")
        else:
            logger.warning(f"No background music found in {Config.BG_MUSIC_FOLDER}")
    
    def get_next_track(self):
        """Get next background track"""
        if not self.bg_tracks:
            return None
        
        track = self.bg_tracks[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.bg_tracks)
        return track

# ================== Music Player ==================
class MusicPlayer:
    def __init__(self, ctx: nextcord.Interaction, voice_client: nextcord.VoiceClient, bg_manager):
        self.ctx = ctx
        self.channel = ctx.channel
        self.voice_client = voice_client
        self.queue: deque = deque()
        self.history: deque = deque(maxlen=50)
        self.current: Optional[AudioSource] = None
        self.loop_mode = LoopMode.NONE
        self.volume = Config.DEFAULT_VOLUME
        self.guild_id = voice_client.guild.id
        self._task = None
        self._event = asyncio.Event()
        self.state = PlaybackState.IDLE
        self.preload_tasks = []
        self.download_executor = ThreadPoolExecutor(max_workers=Config.MAX_DOWNLOAD_WORKERS)
        
        # Console
        self.console_message = None
        self.console_task = None
        
        # Crossfade
        self.crossfade_enabled = Config.ENABLE_CROSSFADE
        self.crossfade_duration = Config.CROSSFADE_DURATION
        self.next_source_ready = None
        self.crossfade_task = None
        
        # Radio
        self.radio_mode = False
        self.radio_seed_video_id = None
        self.radio_task = None
        
        # Background Music
        self.bg_manager = bg_manager
        self.bg_music_enabled = Config.ENABLE_BG_MUSIC
        self.bg_idle_task = None
        self.is_bg_playing = False

    async def start(self):
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self.player_loop())
        
        if Config.ENABLE_CONSOLE_MODE and not self.console_task:
            self.console_task = asyncio.create_task(self.console_updater())
        
    async def stop(self):
        for task in [*self.preload_tasks, self.radio_task, self.console_task, self._task, self.bg_idle_task, self.crossfade_task]:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
        
        await self.cleanup_files()
        self.download_executor.shutdown(wait=False)

    async def console_updater(self):
        refresh_rate = max(1, min(60, Config.CONSOLE_REFRESH_RATE))
        
        while True:
            try:
                if self.console_message:
                    embed = self.create_console_embed()
                    view = ConsoleControlView(self, self.bot)
                    await self.console_message.edit(embed=embed, view=view)
                
                await asyncio.sleep(refresh_rate)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Console error: {e}")
                await asyncio.sleep(refresh_rate)

    def create_console_embed(self):
        embed = Embed(
            title="🎵 Music Console",
            color=Config.THEME_MAIN,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Current song
        if self.current and not self.is_bg_playing:
            duration = str(timedelta(seconds=self.current.duration)) if self.current.duration else "Live"
            now_playing = f"**[{self.current.title[:45]}]({self.current.url})**\n"
            now_playing += f"*{self.current.uploader}* • `{duration}`"
            embed.add_field(name="🎵 Now Playing", value=now_playing, inline=False)
        elif self.is_bg_playing:
            embed.add_field(name="🎵 Now Playing", value="*Background Music ♪*", inline=False)
        else:
            embed.add_field(name="🎵 Now Playing", value="*Idle*", inline=False)
        
        # Queue
        if self.queue:
            queue_preview = "\n".join([
                f"`{i}.` {'✅' if s.is_downloaded else '⏳'} {s.title[:35]}"
                for i, s in enumerate(list(self.queue)[:5], 1)
            ])
            if len(self.queue) > 5:
                queue_preview += f"\n*...+{len(self.queue) - 5}*"
            embed.add_field(name="📜 Queue", value=queue_preview, inline=False)
        else:
            queue_status = "∞ Radio" if self.radio_mode else "*Empty*"
            embed.add_field(name="📜 Queue", value=queue_status, inline=False)
        
        # Status
        state_icon = "▶️" if self.voice_client.is_playing() else "⏸️" if self.voice_client.is_paused() else "⏹️"
        loop_icons = {LoopMode.NONE: "➡️", LoopMode.SONG: "🔂", LoopMode.QUEUE: "🔁", LoopMode.RANDOM: "🔀"}
        
        status = [
            f"{state_icon} {self.state.value.title()}",
            f"{loop_icons[self.loop_mode]} Loop",
            f"🔊 {int(self.volume * 100)}%"
        ]
        
        if self.crossfade_enabled:
            status.append(f"🎵 CF {self.crossfade_duration}s")
        if self.radio_mode:
            status.append("📻 Radio")
        
        embed.add_field(name="📊 Status", value=" • ".join(status), inline=False)
        embed.set_footer(text=f"Queue: {len(self.queue)} ✦ エメラルド ✵ ミュージック ✦")
        
        return embed

    async def cleanup_files(self):
        if self.current and self.current.filepath:
            with suppress(OSError):
                os.remove(self.current.filepath)

    async def enable_radio_mode(self, seed_video_id: str):
        self.radio_mode = True
        self.radio_seed_video_id = seed_video_id
        self.queue.clear()
        
        if self.radio_task:
            self.radio_task.cancel()
        self.radio_task = asyncio.create_task(self.radio_queue_filler())
        logger.info(f"📻 Radio enabled: {seed_video_id}")

    def disable_radio_mode(self):
        self.radio_mode = False
        self.radio_seed_video_id = None
        if self.radio_task:
            self.radio_task.cancel()

    async def radio_queue_filler(self):
        played_ids = set()
        
        while self.radio_mode:
            try:
                if len(self.queue) < Config.RADIO_PRELOAD:
                    seed = self.current.video_id if self.current else self.radio_seed_video_id
                    played_ids.add(seed)
                    
                    playlist = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ytmusic.get_watch_playlist(videoId=seed, limit=25)
                    )
                    
                    for track in playlist.get('tracks', [])[:Config.RADIO_PRELOAD]:
                        vid = track.get('videoId')
                        if vid and vid not in played_ids and not any(s.video_id == vid for s in self.queue):
                            played_ids.add(vid)
                            sources = await AudioSource.create_source(
                                self.ctx, f"https://youtube.com/watch?v={vid}", 
                                loop=asyncio.get_event_loop(), download=False
                            )
                            if sources:
                                self.queue.append(sources[0])
                    
                    await self.preload_songs()
                
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Radio error: {e}")
                await asyncio.sleep(5)

    async def preload_songs(self):
        for task in self.preload_tasks:
            if not task.done():
                task.cancel()
        self.preload_tasks.clear()
        
        limit = Config.RADIO_PRELOAD if self.radio_mode else Config.PRELOAD_COUNT
        for song in list(self.queue)[:limit]:
            if not song.is_downloaded and not song.download_task:
                self.preload_tasks.append(asyncio.create_task(self._safe_download(song)))
    
    async def _safe_download(self, song):
        try:
            await song.download()
        except Exception as e:
            logger.error(f"Preload failed: {e}")
            if song in self.queue:
                self.queue.remove(song)

    async def start_bg_music_after_delay(self):
        """Start background music after idle delay"""
        if self.bg_idle_task:
            self.bg_idle_task.cancel()
        
        async def _delayed_bg():
            await asyncio.sleep(Config.BG_MUSIC_IDLE_DELAY)
            if (not self.queue and not self.current and not self.voice_client.is_playing() 
                and self.state == PlaybackState.IDLE and self.bg_music_enabled):
                await self.play_bg_music()
        
        self.bg_idle_task = asyncio.create_task(_delayed_bg())

    async def start_bg_music_after_delay(self):
        """Start background music after idle delay"""
        if self.bg_idle_task:
            self.bg_idle_task.cancel()
        
        async def _delayed_bg():
            await asyncio.sleep(Config.BG_MUSIC_IDLE_DELAY)
            if (not self.queue and not self.current and not self.voice_client.is_playing() 
                and self.bg_music_enabled and not self.is_bg_playing):
                await self.play_bg_music()
        
        self.bg_idle_task = asyncio.create_task(_delayed_bg())

    async def play_bg_music(self):
        """Play background music with fade in"""
        track = self.bg_manager.get_next_track()
        if not track:
            logger.warning("No BG music tracks available")
            self.is_bg_playing = False
            return
        
        try:
            self.is_bg_playing = True
            self.state = PlaybackState.BG_MUSIC
            
            source = nextcord.FFmpegPCMAudio(track, options='-vn')
            source = nextcord.PCMVolumeTransformer(source, 0.0)
            
            def bg_finished(error):
                if error:
                    logger.error(f"BG music error: {error}")
                self.is_bg_playing = False
                self._event.set()
            
            self.voice_client.play(source, after=bg_finished)
            logger.info(f"🎵 Playing BG: {os.path.basename(track)}")
            
            steps = 20
            fade_time = 2.0
            step_time = fade_time / steps
            target_volume = Config.BG_MUSIC_VOLUME
            
            for i in range(steps + 1):
                if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
                    fade_volume = target_volume * (i / steps)
                    self.voice_client.source.volume = fade_volume
                await asyncio.sleep(step_time)
                
        except Exception as e:
            logger.error(f"BG music failed: {e}")
            self.is_bg_playing = False
            self._event.set()

    async def stop_bg_music_with_fade(self):
        """Stop background music with fade out"""
        if not self.is_bg_playing or not self.voice_client.is_playing():
            return
        
        try:
            steps = 15
            fade_time = 1.5
            step_time = fade_time / steps
            
            if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
                current_volume = self.voice_client.source.volume
                
                for i in range(steps):
                    if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
                        fade_volume = current_volume * (1 - (i / steps))
                        self.voice_client.source.volume = fade_volume
                    await asyncio.sleep(step_time)
            
            self.voice_client.stop()
            self.is_bg_playing = False
        except Exception as e:
            logger.error(f"BG fade out error: {e}")
            self.voice_client.stop()
            self.is_bg_playing = False

    async def apply_spotify_crossfade(self, next_song):
        """Apply Spotify-style crossfade (fade out current, fade in next simultaneously)"""
        if not self.crossfade_enabled or not self.voice_client.is_playing():
            return
        
        fade_duration = self.crossfade_duration
        steps = 30
        step_time = fade_duration / steps
        
        try:
            await next_song.download()
            next_source = next_song.create_ffmpeg_source()
            next_pcm = nextcord.PCMVolumeTransformer(next_source, 0.0)
            self.next_source_ready = next_pcm
        except Exception as e:
            logger.error(f"Crossfade prep failed: {e}")
            return
        
        original_volume = self.volume
        for i in range(steps):
            if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
                fade_out = original_volume * (1 - (i / steps))
                self.voice_client.source.volume = fade_out
            await asyncio.sleep(step_time)
        
        self.voice_client.stop()
        
        def next_finished(error):
            if error:
                logger.error(f"Playback error: {error}")
            self._event.set()
        
        self.voice_client.play(next_pcm, after=next_finished)
        
        for i in range(steps):
            if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
                fade_in = original_volume * (i / steps)
                self.voice_client.source.volume = fade_in
            await asyncio.sleep(step_time)
        
        if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
            self.voice_client.source.volume = original_volume

    async def player_loop(self):
        await self.bot.wait_until_ready()
        
        while True:
            self._event.clear()
            
            if not self.queue and not self.current and self.bg_music_enabled and not self.is_bg_playing:
                if not self.bg_idle_task or self.bg_idle_task.done():
                    await self.start_bg_music_after_delay()
                await asyncio.sleep(1)
                continue
            
            if self.is_bg_playing and (self.queue or self.current):
                await self.stop_bg_music_with_fade()
                if self.bg_idle_task:
                    self.bg_idle_task.cancel()
                    self.bg_idle_task = None
                await asyncio.sleep(0.1)

            if not self.queue and self.loop_mode != LoopMode.SONG and not self.current:
                self.state = PlaybackState.IDLE
                await asyncio.sleep(1)
                continue

            try:
                if self.loop_mode == LoopMode.SONG and self.current:
                    song = self.current
                elif self.loop_mode == LoopMode.RANDOM and self.queue:
                    idx = random.randint(0, len(self.queue) - 1)
                    song = self.queue[idx]
                    del self.queue[idx]
                elif self.queue:
                    song = self.queue.popleft()
                else:
                    self.current = None
                    self.state = PlaybackState.IDLE
                    await asyncio.sleep(1)
                    continue
                
                self.state = PlaybackState.LOADING
                
                if not song.is_downloaded:
                    try:
                        await asyncio.wait_for(song.download(), timeout=60)
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout: {song.title[:50]}")
                        self.current = None
                        continue
                    except Exception as e:
                        logger.error(f"Download failed: {e}")
                        self.current = None
                        continue
                
                if not song.filepath or not os.path.exists(song.filepath):
                    logger.error(f"File missing: {song.video_id}")
                    self.current = None
                    continue
                
                asyncio.create_task(self.preload_songs())
                
                next_song = self.queue[0] if self.queue else None
                if self.crossfade_enabled and next_song and self.voice_client.is_playing():
                    self.current = song
                    await self.apply_spotify_crossfade(next_song)
                    if self.loop_mode != LoopMode.SONG:
                        self.history.append(song)
                    if self.loop_mode == LoopMode.QUEUE and not self.radio_mode:
                        self.queue.append(song)
                    continue
                
                self.current = song
                
                try:
                    pcm_source = song.create_ffmpeg_source()
                except Exception as e:
                    logger.error(f"FFmpeg error: {e}")
                    self.current = None
                    continue
                
                source = nextcord.PCMVolumeTransformer(pcm_source, self.volume)
                self.state = PlaybackState.PLAYING
                
                def song_finished(error):
                    if error:
                        logger.error(f"Playback error: {error}")
                    self._event.set()
                
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                    await asyncio.sleep(0.3)
                
                self.voice_client.play(source, after=song_finished)
                await asyncio.sleep(0.5)
                
                if not self.voice_client.is_playing():
                    logger.error("Playback failed to start")
                    self.current = None
                    continue
                
                if not Config.ENABLE_CONSOLE_MODE:
                    embed = self.create_now_playing_embed(song)
                    await self.channel.send(embed=embed)
                
                if self.loop_mode == LoopMode.QUEUE and not self.radio_mode:
                    self.queue.append(song)
                
                if self.loop_mode != LoopMode.SONG:
                    self.history.append(song)
                
                await self._event.wait()
                
                if self.loop_mode != LoopMode.SONG:
                    self.current = None
                
            except Exception as e:
                logger.error(f"Player loop error: {e}", exc_info=True)
                self.current = None
                await asyncio.sleep(5)
                
                if not song.filepath or not os.path.exists(song.filepath):
                    logger.error(f"File missing: {song.video_id}")
                    self.current = None
                    continue
                
                # Preload next songs
                asyncio.create_task(self.preload_songs())
                
                # Apply crossfade if enabled and has next song
                next_song = self.queue[0] if self.queue else None
                if self.crossfade_enabled and next_song and self.voice_client.is_playing():
                    self.current = song
                    await self.apply_spotify_crossfade(next_song)
                    # Crossfade handles the transition, skip normal playback
                    if self.loop_mode != LoopMode.SONG:
                        self.history.append(song)
                    if self.loop_mode == LoopMode.QUEUE and not self.radio_mode:
                        self.queue.append(song)
                    continue
                
                # Normal playback (no crossfade)
                self.current = song
                
                try:
                    pcm_source = song.create_ffmpeg_source()
                except Exception as e:
                    logger.error(f"FFmpeg error: {e}")
                    self.current = None
                    continue
                
                source = nextcord.PCMVolumeTransformer(pcm_source, self.volume)
                self.state = PlaybackState.PLAYING
                
                def song_finished(error):
                    if error:
                        logger.error(f"Playback error: {error}")
                    self._event.set()
                
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                    await asyncio.sleep(0.3)
                
                self.voice_client.play(source, after=song_finished)
                await asyncio.sleep(0.5)
                
                if not self.voice_client.is_playing():
                    logger.error("Playback failed to start")
                    self.current = None
                    continue
                
                # Send now playing embed (only if console disabled)
                if not Config.ENABLE_CONSOLE_MODE:
                    embed = self.create_now_playing_embed(song)
                    await self.channel.send(embed=embed)
                
                # Handle loop modes BEFORE waiting
                if self.loop_mode == LoopMode.QUEUE and not self.radio_mode:
                    self.queue.append(song)
                
                if self.loop_mode != LoopMode.SONG:
                    self.history.append(song)
                
                # Wait for song to finish
                await self._event.wait()
                
                # Clear current song after it finishes (if not looping single song)
                if self.loop_mode != LoopMode.SONG:
                    self.current = None
                
            except Exception as e:
                logger.error(f"Player loop error: {e}", exc_info=True)
                self.current = None
                await asyncio.sleep(5)
                
                # Download if needed
                if not song.is_downloaded:
                    try:
                        await asyncio.wait_for(song.download(), timeout=60)
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout: {song.title[:50]}")
                        self.current = None
                        continue
                    except Exception as e:
                        logger.error(f"Download failed: {e}")
                        self.current = None
                        continue
                
                if not song.filepath or not os.path.exists(song.filepath):
                    logger.error(f"File missing: {song.video_id}")
                    self.current = None
                    continue
                
                # Preload next songs
                asyncio.create_task(self.preload_songs())
                
                # Apply crossfade if enabled and has next song
                next_song = self.queue[0] if self.queue else None
                if self.crossfade_enabled and next_song and self.voice_client.is_playing():
                    self.current = song
                    await self.apply_spotify_crossfade(next_song)
                    # Crossfade handles the transition, skip normal playback
                    if self.loop_mode != LoopMode.SONG:
                        self.history.append(song)
                    if self.loop_mode == LoopMode.QUEUE and not self.radio_mode:
                        self.queue.append(song)
                    continue
                
                # Normal playback (no crossfade)
                self.current = song
                
                try:
                    pcm_source = song.create_ffmpeg_source()
                except Exception as e:
                    logger.error(f"FFmpeg error: {e}")
                    self.current = None
                    continue
                
                source = nextcord.PCMVolumeTransformer(pcm_source, self.volume)
                self.state = PlaybackState.PLAYING
                
                def song_finished(error):
                    if error:
                        logger.error(f"Playback error: {error}")
                    self._event.set()
                
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                    await asyncio.sleep(0.3)
                
                self.voice_client.play(source, after=song_finished)
                await asyncio.sleep(0.5)
                
                if not self.voice_client.is_playing():
                    logger.error("Playback failed to start")
                    self.current = None
                    continue
                
                # Send now playing embed (only if console disabled)
                if not Config.ENABLE_CONSOLE_MODE:
                    embed = self.create_now_playing_embed(song)
                    await self.channel.send(embed=embed)
                
                if self.loop_mode != LoopMode.SONG:
                    self.history.append(song)
                
                if self.loop_mode == LoopMode.QUEUE and not self.radio_mode:
                    self.queue.append(song)
                
                await self._event.wait()
                
            except Exception as e:
                logger.error(f"Player loop error: {e}", exc_info=True)
                self.current = None
                await asyncio.sleep(5)
    
    def create_now_playing_embed(self, song):
        embed = Embed(color=Config.THEME_MAIN)
        
        if self.radio_mode:
            embed.title = "📻 Radio Mode • Now Playing"
        else:
            embed.title = "🎵 Now Playing"
        
        embed.description = f"### [{song.title}]({song.url})\n**{song.uploader}**"
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        if song.duration:
            embed.add_field(name="⏱️ Duration", value=f"`{str(timedelta(seconds=song.duration))}`", inline=True)
        
        embed.add_field(name="🔊 Volume", value=f"`{int(self.volume * 100)}%`", inline=True)
        
        queue_info = f"∞ (Radio)" if self.radio_mode else f"`{len(self.queue)}`"
        embed.add_field(name="📜 Queue", value=queue_info, inline=True)
        
        if self.crossfade_enabled:
            embed.add_field(name="🎵 Crossfade", value=f"`{self.crossfade_duration}s`", inline=True)
        
        embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
        return embed
    
    def create_queue_embed(self):
        if self.radio_mode:
            embed = Embed(title="📻 Radio Queue", color=Config.THEME_SUB)
        else:
            embed = Embed(title="📜 Music Queue", color=Config.THEME_MAIN)
        
        if self.current:
            duration = str(timedelta(seconds=self.current.duration)) if self.current.duration else "Live"
            embed.add_field(
                name="▶️ Current",
                value=f"**[{self.current.title[:45]}]({self.current.url})**\n*{self.current.uploader}* • `{duration}`",
                inline=False
            )
        
        if self.queue:
            queue_list = [
                f"`{i}.` {'✅' if s.is_downloaded else '⏳'} **{s.title[:35]}**\n    ↳ *{s.uploader[:25]}*"
                for i, s in enumerate(list(self.queue)[:10], 1)
            ]
            if len(self.queue) > 10:
                queue_list.append(f"\n*...+{len(self.queue) - 10} more*")
            embed.add_field(name="⏭️ Up Next", value="\n".join(queue_list), inline=False)
        
        total = sum(s.duration for s in self.queue if s.duration)
        duration_str = str(timedelta(seconds=total)) if total else "∞" if self.radio_mode else "0:00"
        
        footer = f"📊 {len(self.queue)} songs • ⏱️ {duration_str} • 🔁 {self.loop_mode.value}"
        embed.set_footer(text=footer)
        embed.timestamp = datetime.now(timezone.utc)
        return embed
    
    async def add_songs(self, songs: List[AudioSource]):
        # Cancel BG music if playing
        if self.is_bg_playing:
            self.voice_client.stop()
            self.is_bg_playing = False
            if self.bg_idle_task:
                self.bg_idle_task.cancel()
        
        added = []
        for song in songs:
            if len(self.queue) < Config.MAX_QUEUE_SIZE:
                if not song.duration or song.duration <= Config.MAX_SONG_DURATION:
                    self.queue.append(song)
                    added.append(song)
        
        if added:
            limit = Config.RADIO_PRELOAD if self.radio_mode else Config.PRELOAD_COUNT
            for song in list(self.queue)[:limit]:
                if not song.is_downloaded and not song.download_task:
                    asyncio.create_task(self._safe_download(song))
        
        if self.state == PlaybackState.IDLE and self.queue:
            if not self._task or self._task.done():
                await self.start()
        
        return added
    
    def skip(self, to_position: Optional[int] = None):
        if to_position and to_position > 1 and to_position <= len(self.queue) + 1:
            for _ in range(to_position - 2):
                if self.queue:
                    self.queue.popleft()
        
        if self.voice_client.is_playing():
            self.voice_client.stop()
    
    def pause(self):
        if self.voice_client.is_playing():
            self.voice_client.pause()
            self.state = PlaybackState.PAUSED
    
    def resume(self):
        if self.voice_client.is_paused():
            self.voice_client.resume()
            self.state = PlaybackState.PLAYING
    
    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))
        if self.voice_client.source and hasattr(self.voice_client.source, 'volume'):
            self.voice_client.source.volume = self.volume
    
    def shuffle(self):
        temp = list(self.queue)
        random.shuffle(temp)
        self.queue = deque(temp)
    
    def clear_queue(self):
        self.queue.clear()
        if self.radio_mode:
            self.disable_radio_mode()

# ================== Session Manager ==================
class SessionManager:
    def __init__(self, bot_instance, bg_manager):
        self.sessions: Dict[int, MusicPlayer] = {}
        self.bot = bot_instance
        self.bg_manager = bg_manager
    
    async def create_session(self, ctx, voice_client):
        player = MusicPlayer(ctx, voice_client, self.bg_manager)
        player.bot = self.bot
        self.sessions[ctx.guild.id] = player
        await player.start()
        return player
    
    def get_session(self, guild_id: int) -> Optional[MusicPlayer]:
        return self.sessions.get(guild_id)
    
    async def destroy_session(self, guild_id: int):
        if guild_id in self.sessions:
            await self.sessions[guild_id].stop()
            del self.sessions[guild_id]
    
    async def cleanup_all(self):
        for guild_id in list(self.sessions.keys()):
            await self.destroy_session(guild_id)

# ================== Playlist Manager ==================
class PlaylistManager:
    def __init__(self):
        self.playlists_file = "playlists.json"
        self.playlists = self.load_playlists()
        self._save_lock = asyncio.Lock()
    
    def load_playlists(self):
        if os.path.exists(self.playlists_file):
            try:
                with open(self.playlists_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    async def save_playlists(self):
        async with self._save_lock:
            try:
                with open(f"{self.playlists_file}.tmp", 'w', encoding='utf-8') as f:
                    json.dump(self.playlists, f, indent=2, ensure_ascii=False)
                os.replace(f"{self.playlists_file}.tmp", self.playlists_file)
            except Exception as e:
                logger.error(f"Playlist save error: {e}")
    
    def create_playlist(self, user_id: str, name: str, creator_name: str):
        user_id = str(user_id)
        if user_id not in self.playlists:
            self.playlists[user_id] = {}
        
        if name not in self.playlists[user_id]:
            self.playlists[user_id][name] = {
                "creator": creator_name,
                "created": datetime.now(timezone.utc).isoformat(),
                "songs": []
            }
            asyncio.create_task(self.save_playlists())
            return True
        return False
    
    def add_to_playlist(self, user_id: str, name: str, song_data: dict):
        user_id = str(user_id)
        if user_id in self.playlists and name in self.playlists[user_id]:
            self.playlists[user_id][name]["songs"].append(song_data)
            asyncio.create_task(self.save_playlists())
            return True
        return False
    
    def get_playlist(self, user_id: str, name: str):
        user_id = str(user_id)
        if user_id in self.playlists and name in self.playlists[user_id]:
            return self.playlists[user_id][name]["songs"]
        return None
    
    def get_user_playlists(self, user_id: str):
        user_id = str(user_id)
        return list(self.playlists.get(user_id, {}).keys())
    
    def delete_playlist(self, user_id: str, name: str):
        user_id = str(user_id)
        if user_id in self.playlists and name in self.playlists[user_id]:
            del self.playlists[user_id][name]
            asyncio.create_task(self.save_playlists())
            return True
        return False

# ================== Bot Setup ==================
class MusicBot(commands.Bot):
    def __init__(self):
        intents = nextcord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(command_prefix=Config.DEFAULT_PREFIX, intents=intents, help_command=None)
        
        self.bg_manager = BackgroundMusicManager()
        self.session_manager = SessionManager(self, self.bg_manager)
        self.playlist_manager = PlaylistManager()
        self.start_time = datetime.now(timezone.utc)
        
    async def on_ready(self):
        logger.info(f'✅ {self.user} connected!')
        logger.info(f'📊 Servers: {len(self.guilds)}')
        logger.info(f'🎵 BG Music: {len(self.bg_manager.bg_tracks)} tracks')
        
        self.cleanup_cache.start()
        
        await self.change_presence(
            activity=nextcord.Activity(
                type=nextcord.ActivityType.listening,
                name="✦ エメラルド ✵ ミュージック ✦"
            )
        )
    
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        session = self.session_manager.get_session(member.guild.id)
        if session and session.voice_client:
            if len(session.voice_client.channel.members) == 1:
                await asyncio.sleep(60)
                if session.voice_client.is_connected() and len(session.voice_client.channel.members) == 1:
                    await self.session_manager.destroy_session(member.guild.id)

    @tasks.loop(seconds=Config.CACHE_CLEANUP_INTERVAL)
    async def cleanup_cache(self):
        try:
            if os.path.exists('downloads'):
                total = 0
                files = []
                for f in os.listdir('downloads'):
                    path = os.path.join('downloads', f)
                    if os.path.isfile(path):
                        size = os.path.getsize(path)
                        total += size
                        files.append((path, os.path.getmtime(path), size))
                
                # Remove old files
                cutoff = time.time() - 14400
                for path, mtime, size in files:
                    if mtime < cutoff:
                        with suppress(OSError):
                            os.remove(path)
                            total -= size
                
                # Remove if over limit
                max_size = Config.MAX_RAM_MB * 1024 * 1024
                if total > max_size:
                    files.sort(key=lambda x: x[1])
                    for path, _, size in files:
                        if total <= max_size * 0.8:
                            break
                        with suppress(OSError):
                            os.remove(path)
                            total -= size
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")

bot = MusicBot()

# ================== Commands ==================
@bot.slash_command(name="join", description="Join your voice channel")
async def join(ctx: nextcord.Interaction):
    if not ctx.user.voice:
        return await ctx.send("❌ You need to be in a voice channel!", ephemeral=True)
    
    channel = ctx.user.voice.channel
    
    if ctx.guild.voice_client:
        await ctx.guild.voice_client.move_to(channel)
        embed = Embed(description=f"✅ Moved to **{channel.name}**", color=Config.THEME_MAIN)
        await ctx.send(embed=embed)
    else:
        voice_client = await channel.connect()
        session = await bot.session_manager.create_session(ctx, voice_client)
        
        embed = Embed(description=f"✅ Connected to **{channel.name}**", color=Config.THEME_MAIN)
        
        if Config.ENABLE_CONSOLE_MODE:
            console_embed = session.create_console_embed()
            view = ConsoleControlView(session, bot)
            session.console_message = await ctx.channel.send(embed=console_embed, view=view)
            embed.set_footer(text="🎛️ Console created")
        
        await ctx.send(embed=embed)

@bot.slash_command(name="leave", description="Leave the voice channel")
async def leave(ctx: nextcord.Interaction):
    if not ctx.guild.voice_client:
        return await ctx.send("❌ Not connected!", ephemeral=True)
    
    await bot.session_manager.destroy_session(ctx.guild.id)
    embed = Embed(description="👋 Disconnected", color=Config.THEME_SUB)
    await ctx.send(embed=embed)

@bot.slash_command(name="console", description="Show music control console")
async def console(ctx: nextcord.Interaction, ephemeral: bool = SlashOption(required=False, default=False)):
    session = bot.session_manager.get_session(ctx.guild.id)
    
    if not session:
        return await ctx.send("❌ No active session!", ephemeral=True)
    
    embed = session.create_console_embed()
    view = ConsoleControlView(session, bot)
    
    if ephemeral:
        await ctx.send(embed=embed, view=view, ephemeral=True)
    else:
        if session.console_message:
            try:
                await session.console_message.delete()
            except:
                pass
        await ctx.response.defer()
        session.console_message = await ctx.channel.send(embed=embed, view=view)
        await ctx.followup.send("✅ Console created!", ephemeral=True)

@bot.slash_command(name="play", description="Play a song or playlist")
async def play(ctx: nextcord.Interaction, search: str = SlashOption(description="Song name or URL", required=True)):
    await ctx.response.defer()

    if not ctx.user.voice:
        return await ctx.followup.send("❌ You need to be in a voice channel!", ephemeral=True)
    
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session or not session.voice_client.is_connected():
        voice_client = await ctx.user.voice.channel.connect()
        session = await bot.session_manager.create_session(ctx, voice_client)
        
        if Config.ENABLE_CONSOLE_MODE and not session.console_message:
            console_embed = session.create_console_embed()
            view = ConsoleControlView(session, bot)
            session.console_message = await ctx.channel.send(embed=console_embed, view=view)
    
    if session.radio_mode:
        session.disable_radio_mode()

    try:
        sources = await AudioSource.create_source(ctx, search, loop=bot.loop, download=True)
        
        if not sources:
            return await ctx.followup.send("❌ No results found!")
        
        added = await session.add_songs(sources)
        
        if len(added) == 1:
            song = added[0]
            embed = Embed(color=Config.THEME_MAIN)
            embed.title = "✅ Added to Queue"
            embed.description = f"**[{song.title}]({song.url})**\n*{song.uploader}*"
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            if song.duration:
                embed.add_field(name="⏱️", value=f"`{str(timedelta(seconds=song.duration))}`", inline=True)
            embed.add_field(name="📍", value=f"`#{len(session.queue)}`", inline=True)
        else:
            embed = Embed(color=Config.THEME_MAIN)
            embed.title = "✅ Added Playlist"
            embed.description = f"Added **{len(added)}** songs to the queue"
        
        embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
        await ctx.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Play error: {e}")
        await ctx.followup.send(f"❌ Error: {str(e)[:100]}")

@bot.slash_command(name="radio", description="Start infinite radio mode")
async def radio(ctx: nextcord.Interaction):
    await ctx.response.defer()
    
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session or not session.current:
        return await ctx.followup.send("❌ Play a song first!", ephemeral=True)
    
    await session.enable_radio_mode(session.current.video_id)
    
    embed = Embed(color=Config.THEME_SUB)
    embed.title = "📻 Radio Mode Activated"
    embed.description = f"Starting radio based on:\n**{session.current.title}**\n*by {session.current.uploader}*"
    if session.current.thumbnail:
        embed.set_thumbnail(url=session.current.thumbnail)
    embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
    await ctx.followup.send(embed=embed)

@bot.slash_command(name="crossfade", description="Toggle or set crossfade duration")
async def crossfade(ctx: nextcord.Interaction, duration: float = SlashOption(required=False, min_value=0.0, max_value=10.0)):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ No active session!", ephemeral=True)
    
    if duration is None:
        session.crossfade_enabled = not session.crossfade_enabled
        status = "enabled" if session.crossfade_enabled else "disabled"
        embed = Embed(description=f"🎵 Crossfade: **{status}**", color=Config.THEME_MAIN)
    elif duration == 0:
        session.crossfade_enabled = False
        embed = Embed(description="🎵 Crossfade: **disabled**", color=Config.THEME_SUB)
    else:
        session.crossfade_enabled = True
        session.crossfade_duration = duration
        embed = Embed(description=f"🎵 Crossfade: **{duration}s**", color=Config.THEME_MAIN)
    
    await ctx.send(embed=embed)

@bot.slash_command(name="pause", description="Pause playback")
async def pause(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ Nothing playing!", ephemeral=True)
    session.pause()
    await ctx.send(embed=Embed(description="⏸️ Paused", color=Config.THEME_SUB))

@bot.slash_command(name="resume", description="Resume playback")
async def resume(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ Nothing playing!", ephemeral=True)
    session.resume()
    await ctx.send(embed=Embed(description="▶️ Resumed", color=Config.THEME_MAIN))

@bot.slash_command(name="skip", description="Skip current song")
async def skip(ctx: nextcord.Interaction, to_position: int = SlashOption(required=False, min_value=1)):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session or not session.current:
        return await ctx.send("❌ Nothing playing!", ephemeral=True)
    
    session.skip(to_position)
    desc = f"⏭️ Skipped to #{to_position}" if to_position else "⏭️ Skipped"
    await ctx.send(embed=Embed(description=desc, color=Config.THEME_MAIN))

@bot.slash_command(name="queue", description="Show the music queue")
async def queue(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ No active session!", ephemeral=True)
    await ctx.send(embed=session.create_queue_embed())

@bot.slash_command(name="loop", description="Set loop mode")
async def loop(ctx: nextcord.Interaction, mode: str = SlashOption(choices=["off", "song", "queue", "random"], required=True)):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ No active session!", ephemeral=True)
    
    session.loop_mode = LoopMode(mode)
    await ctx.send(embed=Embed(description=f"🔁 Loop: **{mode}**", color=Config.THEME_MAIN))

@bot.slash_command(name="volume", description="Set playback volume")
async def volume(ctx: nextcord.Interaction, level: int = SlashOption(min_value=0, max_value=100, required=True)):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ No active session!", ephemeral=True)
    
    session.set_volume(level / 100)
    icon = "🔇" if level == 0 else "🔉" if level < 30 else "🔊"
    await ctx.send(embed=Embed(description=f"{icon} Volume: **{level}%**", color=Config.THEME_MAIN))

@bot.slash_command(name="shuffle", description="Shuffle the queue")
async def shuffle(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session or not session.queue:
        return await ctx.send("❌ Queue is empty!", ephemeral=True)
    session.shuffle()
    await ctx.send(embed=Embed(description=f"🔀 Shuffled {len(session.queue)} songs", color=Config.THEME_SUB))

@bot.slash_command(name="clear", description="Clear the queue")
async def clear(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session:
        return await ctx.send("❌ No active session!", ephemeral=True)
    
    size = len(session.queue)
    session.clear_queue()
    await ctx.send(embed=Embed(description=f"🗑️ Cleared {size} songs", color=Config.THEME_SUB))

@bot.slash_command(name="nowplaying", description="Show current song")
async def nowplaying(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session or not session.current:
        return await ctx.send("❌ Nothing playing!", ephemeral=True)
    await ctx.send(embed=session.create_now_playing_embed(session.current))

@bot.slash_command(name="help", description="Show help information")
async def help_command(ctx: nextcord.Interaction):
    embed = Embed(title="🎵 Music Bot Commands", color=Config.THEME_MAIN)
    embed.description = "A powerful music bot with crossfade, radio mode, and background music!"
    
    embed.add_field(
        name="🎵 Music",
        value=(
            "`/play` - Play a song or playlist\n"
            "`/radio` - Start infinite radio mode\n"
            "`/pause` - Pause playback\n"
            "`/resume` - Resume playback\n"
            "`/skip` - Skip current song\n"
            "`/queue` - Show music queue\n"
            "`/nowplaying` - Show current song\n"
            "`/loop` - Set loop mode\n"
            "`/volume` - Set volume (0-100)\n"
            "`/shuffle` - Shuffle queue\n"
            "`/clear` - Clear queue\n"
            "`/crossfade` - Toggle crossfade"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎛️ Control",
        value=(
            "`/join` - Join voice channel\n"
            "`/leave` - Leave voice channel\n"
            "`/console` - Show control panel"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📝 Playlist",
        value=(
            "`/playlist_create` - Create new playlist\n"
            "`/playlist_add` - Add song to playlist\n"
            "`/playlist_play` - Play playlist\n"
            "`/playlist_list` - List playlists\n"
            "`/playlist_delete` - Delete playlist"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔧 Utility",
        value=(
            "`/help` - Show this help\n"
            "`/ping` - Check latency\n"
            "`/stats` - Bot statistics\n"
            "`/tts` - Text-to-speech"
        ),
        inline=False
    )
    
    embed.add_field(
        name="✨ Features",
        value=(
            "• Spotify-style crossfade transitions\n"
            "• Infinite radio mode with YT Music\n"
            "• Background music when idle\n"
            "• Smart preloading & parallel downloads\n"
            "• Interactive console control"
        ),
        inline=False
    )
    
    embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
    embed.timestamp = datetime.now(timezone.utc)
    await ctx.send(embed=embed)

# ================== Playlist Commands ==================
@bot.slash_command(name="playlist_create", description="Create a new playlist")
async def playlist_create(ctx: nextcord.Interaction, name: str = SlashOption(required=True)):
    creator = f"{ctx.user.name}#{ctx.user.discriminator}"
    
    if bot.playlist_manager.create_playlist(ctx.user.id, name, creator):
        embed = Embed(color=Config.THEME_MAIN)
        embed.title = "✅ Playlist Created"
        embed.description = f"**{name}**"
        embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Playlist **{name}** already exists!", ephemeral=True)

@bot.slash_command(name="playlist_add", description="Add song to playlist")
async def playlist_add(ctx: nextcord.Interaction, name: str = SlashOption(required=True), song: str = SlashOption(required=False)):
    await ctx.response.defer()
    
    if not song:
        session = bot.session_manager.get_session(ctx.guild.id)
        if not session or not session.current:
            return await ctx.followup.send("❌ Play a song or specify a URL!", ephemeral=True)
        
        song_data = {
            "title": session.current.title,
            "url": session.current.url,
            "duration": session.current.duration,
            "uploader": session.current.uploader
        }
        
        if bot.playlist_manager.add_to_playlist(ctx.user.id, name, song_data):
            embed = Embed(color=Config.THEME_MAIN)
            embed.description = f"✅ Added to **{name}**"
            embed.add_field(name="Song", value=f"[{session.current.title[:40]}]({session.current.url})")
            await ctx.followup.send(embed=embed)
        else:
            await ctx.followup.send(f"❌ Playlist **{name}** not found!", ephemeral=True)
    else:
        try:
            sources = await AudioSource.create_source(ctx, song, loop=bot.loop, download=False)
            
            if not sources:
                return await ctx.followup.send("❌ No results found!", ephemeral=True)
            
            added = 0
            for source in sources:
                song_data = {
                    "title": source.title,
                    "url": source.url,
                    "duration": source.duration,
                    "uploader": source.uploader
                }
                if bot.playlist_manager.add_to_playlist(ctx.user.id, name, song_data):
                    added += 1
            
            if added:
                embed = Embed(color=Config.THEME_MAIN)
                embed.description = f"✅ Added {added} songs to **{name}**"
                await ctx.followup.send(embed=embed)
            else:
                await ctx.followup.send(f"❌ Playlist not found!", ephemeral=True)
        except Exception as e:
            await ctx.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)

@bot.slash_command(name="playlist_play", description="Play a playlist")
async def playlist_play(ctx: nextcord.Interaction, name: str = SlashOption(required=True)):
    await ctx.response.defer()
    
    songs = bot.playlist_manager.get_playlist(ctx.user.id, name)
    
    if not songs:
        return await ctx.followup.send(f"❌ Playlist **{name}** not found!", ephemeral=True)
    
    if not ctx.guild.voice_client:
        if not ctx.user.voice:
            return await ctx.followup.send("❌ You need to be in a voice channel!")
        
        voice_client = await ctx.user.voice.channel.connect()
        session = await bot.session_manager.create_session(ctx, voice_client)
        
        if Config.ENABLE_CONSOLE_MODE and not session.console_message:
            console_embed = session.create_console_embed()
            view = ConsoleControlView(session, bot)
            session.console_message = await ctx.channel.send(embed=console_embed, view=view)
    
    session = bot.session_manager.get_session(ctx.guild.id)
    
    if session.radio_mode:
        session.disable_radio_mode()
    
    added = 0
    for song_data in songs:
        try:
            sources = await AudioSource.create_source(ctx, song_data['url'], loop=bot.loop, download=(added == 0))
            if sources:
                await session.add_songs(sources)
                added += len(sources)
        except Exception as e:
            logger.error(f"Failed to add: {e}")
    
    embed = Embed(color=Config.THEME_MAIN)
    embed.title = "📝 Playing Playlist"
    embed.description = f"**{name}**"
    embed.add_field(name="Added", value=f"`{added} songs`", inline=True)
    embed.add_field(name="Queue", value=f"`{len(session.queue)} songs`", inline=True)
    embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
    await ctx.followup.send(embed=embed)

@bot.slash_command(name="playlist_list", description="List your playlists")
async def playlist_list(ctx: nextcord.Interaction):
    playlists = bot.playlist_manager.get_user_playlists(ctx.user.id)
    
    if not playlists:
        embed = Embed(
            description="📝 You don't have any playlists yet!\nUse `/playlist_create` to make one.",
            color=Config.THEME_SUB
        )
        return await ctx.send(embed=embed, ephemeral=True)
    
    embed = Embed(title="📝 Your Playlists", color=Config.THEME_MAIN)
    
    info = []
    for pl_name in playlists:
        songs = bot.playlist_manager.get_playlist(ctx.user.id, pl_name)
        if songs:
            count = len(songs)
            total_dur = sum(s.get('duration', 0) for s in songs)
            dur_str = str(timedelta(seconds=total_dur)) if total_dur else "0:00"
            info.append(f"**{pl_name}**\n    `{count} songs` • `{dur_str}`")
    
    embed.description = "\n\n".join(info)
    embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
    await ctx.send(embed=embed)

@bot.slash_command(name="playlist_delete", description="Delete a playlist")
async def playlist_delete(ctx: nextcord.Interaction, name: str = SlashOption(required=True)):
    if bot.playlist_manager.delete_playlist(ctx.user.id, name):
        embed = Embed(description=f"✅ Deleted playlist: **{name}**", color=Config.THEME_SUB)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Playlist **{name}** not found!", ephemeral=True)

# ================== Utility Commands ==================
@bot.slash_command(name="ping", description="Check bot latency")
async def ping(ctx: nextcord.Interaction):
    latency = round(bot.latency * 1000)
    color = Config.THEME_MAIN if latency < 100 else Config.THEME_SUB if latency < 200 else Config.THEME_BG
    status = "Excellent" if latency < 100 else "Good" if latency < 200 else "Poor"
    
    embed = Embed(title="🏓 Pong!", color=color)
    embed.add_field(name="Latency", value=f"`{latency}ms`", inline=True)
    embed.add_field(name="Status", value=f"`{status}`", inline=True)
    embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
    await ctx.send(embed=embed)

@bot.slash_command(name="stats", description="Show bot statistics")
async def stats(ctx: nextcord.Interaction):
    uptime = datetime.now(timezone.utc) - bot.start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    cache_size = 0
    if os.path.exists('downloads'):
        for f in os.listdir('downloads'):
            cache_size += os.path.getsize(os.path.join('downloads', f))
    cache_mb = cache_size / (1024 * 1024)
    
    embed = Embed(title="📊 Bot Statistics", color=Config.THEME_MAIN)
    embed.add_field(name="🌐 Servers", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="🎵 Sessions", value=f"`{len(bot.session_manager.sessions)}`", inline=True)
    embed.add_field(name="⏱️ Uptime", value=f"`{hours}h {minutes}m`", inline=True)
    embed.add_field(name="🏓 Latency", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    embed.add_field(name="💾 Cache", value=f"`{cache_mb:.1f} MB`", inline=True)
    embed.add_field(name="🎵 BG Tracks", value=f"`{len(bot.bg_manager.bg_tracks)}`", inline=True)
    
    features = []
    features.append(f"🎛️ Console: {'✅' if Config.ENABLE_CONSOLE_MODE else '❌'}")
    features.append(f"🎵 Crossfade: {'✅' if Config.ENABLE_CROSSFADE else '❌'} ({Config.CROSSFADE_DURATION}s)")
    features.append(f"📻 BG Music: {'✅' if Config.ENABLE_BG_MUSIC else '❌'}")
    embed.add_field(name="✨ Features", value=" • ".join(features), inline=False)
    
    embed.set_footer(text="✦ エメラルド ✵ ミュージック ✦")
    embed.timestamp = datetime.now(timezone.utc)
    await ctx.send(embed=embed)

@bot.slash_command(name="tts", description="Text-to-speech in voice channel")
async def tts(ctx: nextcord.Interaction, text: str = SlashOption(required=True), language: str = SlashOption(choices=["en", "ja", "th", "ko", "zh"], default="en")):
    if not ctx.guild.voice_client:
        if not ctx.user.voice:
            return await ctx.send("❌ You need to be in a voice channel!", ephemeral=True)
        await ctx.user.voice.channel.connect()
    
    await ctx.response.defer()
    
    try:
        tts_obj = gTTS(text=text, lang=language, slow=False)
        filename = f"tts_{ctx.user.id}_{int(time.time())}.mp3"
        tts_obj.save(filename)
        
        source = await nextcord.FFmpegOpusAudio.from_probe(filename)
        ctx.guild.voice_client.play(source)
        
        embed = Embed(color=Config.THEME_MAIN)
        embed.description = f"🔊 TTS: *{text[:80]}{'...' if len(text) > 80 else ''}*"
        await ctx.followup.send(embed=embed)
        
        # Clean up file after a delay
        async def cleanup_tts():
            await asyncio.sleep(5)
            with suppress(OSError):
                os.remove(filename)
        
        asyncio.create_task(cleanup_tts())
        
    except Exception as e:
        logger.error(f"TTS error: {e}")
        try:
            await ctx.followup.send(f"❌ TTS error: {e}")
        except:
            await ctx.send(f"❌ TTS error: {e}", ephemeral=True)

# ================== Admin Commands ==================
@bot.slash_command(name="forceskip", description="Force skip (Admin only)")
@commands.has_permissions(administrator=True)
async def forceskip(ctx: nextcord.Interaction):
    session = bot.session_manager.get_session(ctx.guild.id)
    if not session or not session.current:
        return await ctx.send("❌ Nothing playing!", ephemeral=True)
    
    session.skip()
    embed = Embed(description="⏭️ Force skipped by admin", color=Config.THEME_SUB)
    await ctx.send(embed=embed)

@bot.slash_command(name="forcedisconnect", description="Force disconnect all (Owner only)")
@commands.is_owner()
async def forcedisconnect(ctx: nextcord.Interaction):
    count = len(bot.session_manager.sessions)
    await bot.session_manager.cleanup_all()
    
    for vc in bot.voice_clients:
        await vc.disconnect()
    
    embed = Embed(description=f"🔌 Disconnected from {count} sessions", color=Config.THEME_SUB)
    await ctx.send(embed=embed, ephemeral=True)

# ================== Error Handling ==================
@bot.event
async def on_application_command_error(ctx: nextcord.Interaction, error: Exception):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏱️ Cooldown: {error.retry_after:.0f}s", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Missing permissions!", ephemeral=True)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Bot missing permissions!", ephemeral=True)
    else:
        logger.error(f"Error: {error}", exc_info=True)
        error_embed = Embed(description=f"❌ Error:\n```{str(error)[:200]}```", color=Config.THEME_BG)
        
        if not ctx.response.is_done():
            await ctx.send(embed=error_embed, ephemeral=True)
        else:
            await ctx.followup.send(embed=error_embed, ephemeral=True)

# ================== Startup and Cleanup ==================
@atexit.register
def cleanup_on_exit():
    logger.info("Cleaning up...")
    
    try:
        asyncio.run(bot.playlist_manager.save_playlists())
    except:
        pass
    
    if os.path.exists('downloads'):
        for f in os.listdir('downloads'):
            with suppress(OSError):
                os.remove(os.path.join('downloads', f))
    
    for f in os.listdir('.'):
        if f.startswith('tts_'):
            with suppress(OSError):
                os.remove(f)

def main():
    os.makedirs('downloads', exist_ok=True)
    os.makedirs(Config.BG_MUSIC_FOLDER, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("🎵 Discord Music Bot Starting...")
    logger.info("✦ エメラルド ✵ ミュージック ✦ Emerald Music")
    logger.info("=" * 60)
    logger.info(f"📊 Preload: {Config.PRELOAD_COUNT} songs")
    logger.info(f"📻 Radio Preload: {Config.RADIO_PRELOAD} songs")
    logger.info(f"💾 RAM Limit: {Config.MAX_RAM_MB}MB")
    logger.info(f"🎛️ Console: {Config.ENABLE_CONSOLE_MODE} (Refresh: {Config.CONSOLE_REFRESH_RATE}s)")
    logger.info(f"🎵 Crossfade: {Config.ENABLE_CROSSFADE} ({Config.CROSSFADE_DURATION}s)")
    logger.info(f"📻 BG Music: {Config.ENABLE_BG_MUSIC} (Delay: {Config.BG_MUSIC_IDLE_DELAY}s)")
    logger.info(f"🎵 BG Music Tracks Found: {len(bot.bg_manager.bg_tracks)}")
    logger.info(f"🎨 Theme: Elegant Blue & Purple")
    logger.info("=" * 60)
    
    try:
        bot.run(Config.TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
