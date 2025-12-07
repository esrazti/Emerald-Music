from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import threading
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
import json
from bot import AudioSource, LoopMode

app = Flask(__name__, static_folder='template', template_folder='template')
# Explicitly apply CORS to the Flask app itself for REST endpoints (like /api/play)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global bot instance
bot_instance = None

def start_web_server(bot, host='0.0.0.0', port=5000, use_ssl=False, cert_path=None, key_path=None):
    """
    Start the web server in a separate thread
    
    Args:
        bot: The bot instance
        host: Host to bind to (default: '0.0.0.0')
        port: Port to bind to (default: 5000)
        use_ssl: Whether to use HTTPS (default: False)
        cert_path: Path to SSL certificate file (required if use_ssl=True)
        key_path: Path to SSL key file (required if use_ssl=True)
    
    Examples:
        # HTTP (default)
        start_web_server(bot)
        
        # HTTPS with self-signed certificate
        start_web_server(bot, use_ssl=True, cert_path='cert.pem', key_path='key.pem')
        
        # HTTPS with Let's Encrypt
        start_web_server(bot, use_ssl=True, 
                        cert_path='/etc/letsencrypt/live/domain.com/fullchain.pem',
                        key_path='/etc/letsencrypt/live/domain.com/privkey.pem')
    """
    global bot_instance
    bot_instance = bot
    
    def run():
        if use_ssl:
            if not cert_path or not key_path:
                print("âŒ SSL enabled but cert_path or key_path not provided!")
                print("   Falling back to HTTP...")
                socketio.run(app, host=host, port=port, debug=False, use_reloader=False)
            elif not os.path.exists(cert_path) or not os.path.exists(key_path):
                print(f"âŒ Certificate files not found!")
                print(f"   cert_path: {cert_path} (exists: {os.path.exists(cert_path)})")
                print(f"   key_path: {key_path} (exists: {os.path.exists(key_path)})")
                print("   Falling back to HTTP...")
                socketio.run(app, host=host, port=port, debug=False, use_reloader=False)
            else:
                display_host = 'localhost' if host == '0.0.0.0' else host
                print(f"âœ¦ Web dashboard started (HTTPS): https://{display_host}:{port}")
                # For flask-socketio, SSL context needs to be passed differently
                import ssl
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(cert_path, key_path)
                socketio.run(
                    app, 
                    host=host, 
                    port=port, 
                    debug=False, 
                    use_reloader=False,
                    ssl_context=ssl_context
                )
        else:
            display_host = 'localhost' if host == '0.0.0.0' else host
            print(f"âœ¦ Web dashboard started (HTTP): https://{display_host}:{port}")
            socketio.run(app, host=host, port=port, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

def run_async(coro):
    """Helper to run async functions from sync context using the bot's event loop"""
    if not bot_instance:
        raise RuntimeError("Bot instance not available")
    
    # Use the bot's event loop
    loop = bot_instance.loop
    
    # Create a future in the bot's event loop
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    
    # Wait for the result with a timeout
    try:
        return future.result(timeout=60)
    except Exception as e:
        print(f"Error in run_async: {e}")
        raise

# ================== Web Routes ==================
@app.route('/')
def index():
    """Serve the dashboard HTML"""
    try:
        return render_template('dashboard.html')
    except Exception as e:
        print(f"Error rendering template: {e}")
        return "Template not found. Make sure 'dashboard.html' is in the 'template' folder.", 404


@app.route('/api/status')
def get_status():
    """Get bot status and statistics"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        # Get all active sessions
        sessions_data = []
        for guild_id, session in bot_instance.session_manager.sessions.items():
            guild = bot_instance.get_guild(guild_id)
            if guild:
                session_info = {
                    'guild_id': str(guild_id),
                    'guild_name': guild.name,
                    'current_song': None,
                    'queue_size': len(session.queue),
                    'is_playing': session.voice_client.is_playing() if session.voice_client else False,
                    'is_paused': session.voice_client.is_paused() if session.voice_client else False,
                    'volume': int(session.volume * 100),
                    'loop_mode': session.loop_mode.value,
                    'radio_mode': session.radio_mode,
                    'state': session.state.value
                }
                
                if session.current and not session.is_bg_playing:
                    session_info['current_song'] = {
                        'title': session.current.title,
                        'url': session.current.url,
                        'uploader': session.current.uploader,
                        'duration': session.current.duration,
                        'thumbnail': session.current.thumbnail
                    }
                
                sessions_data.append(session_info)
        
        uptime = datetime.now(timezone.utc) - bot_instance.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        
        return jsonify({
            'online': True,
            'servers': len(bot_instance.guilds),
            'sessions': len(bot_instance.session_manager.sessions),
            'uptime': f"{hours}h {minutes}m",
            'latency': round(bot_instance.latency * 1000),
            'sessions_data': sessions_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/guilds')
def get_guilds():
    """Get list of guilds bot is in"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        guilds = []
        for guild in bot_instance.guilds:
            session = bot_instance.session_manager.get_session(guild.id)
            guilds.append({
                'id': str(guild.id),
                'name': guild.name,
                'has_session': session is not None,
                'member_count': guild.member_count
            })
        return jsonify({'guilds': guilds})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/<guild_id_str>')
def get_session(guild_id_str):
    """Get detailed session info for a guild"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        guild_id = int(guild_id_str)
    except ValueError:
        return jsonify({'error': 'Invalid guild_id'}), 400
        
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        queue_list = []
        for i, song in enumerate(list(session.queue)[:20]):
            queue_list.append({
                'position': i + 1,
                'title': song.title,
                'url': song.url,
                'uploader': song.uploader,
                'duration': song.duration,
                'is_downloaded': song.is_downloaded
            })
        
        current_song_data = None
        if session.current and not session.is_bg_playing:
             current_song_data = {
                'title': session.current.title,
                'url': session.current.url,
                'uploader': session.current.uploader,
                'duration': session.current.duration,
                'thumbnail': session.current.thumbnail
            }

        return jsonify({
            'current_song': current_song_data,
            'queue': queue_list,
            'queue_size': len(session.queue),
            'volume': int(session.volume * 100),
            'loop_mode': session.loop_mode.value,
            'radio_mode': session.radio_mode,
            'is_playing': session.voice_client.is_playing() if session.voice_client else False,
            'is_paused': session.voice_client.is_paused() if session.voice_client else False,
            'state': session.state.value
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ================== Control API ==================
@app.route('/api/play', methods=['POST'])
def play_music():
    """
    Handles API request to play music. Used by the dashboard and the Chrome Extension.
    
    The Chrome Extension is expected to send 'guild_id' and 'query' (the URL).
    The dashboard sends 'guild_id' and 'search'.
    """
    if not bot_instance:
        return jsonify({'status': 'error', 'error': 'Bot not initialized', 'message': 'Bot not initialized'}), 503
    
    data = request.get_json()
    guild_id_str = data.get('guild_id')
    # Support both 'query' (from extension) and 'search' (from dashboard)
    search = data.get('query') or data.get('search')
    
    if not guild_id_str or not search:
        return jsonify({'status': 'error', 'error': 'Missing guild_id or query/search', 'message': 'Missing guild_id or query'}), 400
    
    try:
        # Convert the string guild_id from the extension to an integer
        guild_id = int(guild_id_str)
        guild = bot_instance.get_guild(guild_id)
        
        if not guild:
            return jsonify({'status': 'error', 'error': f'Guild with ID {guild_id} not found', 'message': f'Guild with ID {guild_id} not found. Is the bot in that server?'}), 404
        
        session = bot_instance.session_manager.get_session(guild_id)
        
        # If no session exists, try to create a mock context to join voice
        if not session:
            # Mock Context object for the music_cog.play function
            class MockContext:
                def __init__(self, guild, channel):
                    self.guild = guild
                    self.channel = channel 

            # Find a suitable channel to respond in (e.g., the guild's default channel or the first text channel)
            channel = guild.text_channels[0] if guild.text_channels else None

            if not channel:
                return jsonify({'status': 'error', 'error': 'Guild has no text channels', 'message': 'Guild has no text channels to send response/join status.'}), 400
                
            ctx = MockContext(guild, channel)

            # Run the async bot play command
            run_async(bot_instance.music_cog.play(ctx, search))
            
            # After command executes, broadcast status update to all dashboard users
            threading.Thread(target=broadcast_status_update, daemon=True).start()

            return jsonify({'status': 'success', 'success': True, 'message': f'Successfully added {search} to queue for {guild.name}'})
        
        # If session exists, add to queue directly
        try:
            async def add_to_queue():
                loop = bot_instance.loop
                ctx = session.ctx if hasattr(session, 'ctx') else None 
                
                sources = await AudioSource.create_source(ctx, search, loop=loop, download=True)
                
                if not sources:
                    return 0
                
                if session.radio_mode:
                    session.disable_radio_mode()
                
                added = await session.add_songs(sources)
                return len(added)

            added_count = run_async(add_to_queue())
            
            if added_count > 0:
                socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'played'})
                return jsonify({'status': 'success', 'success': True, 'message': f'Added {added_count} song(s): {search}'})
            else:
                return jsonify({'status': 'error', 'error': 'No songs found or added', 'message': 'No songs found or added'}), 404
        
        except Exception as e:
            print(f"Error in /api/play: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'status': 'error', 'error': str(e), 'message': str(e)}), 500

    except ValueError:
        return jsonify({'status': 'error', 'error': 'Invalid guild_id format. Must be a number.', 'message': 'Invalid guild_id format. Must be a number.'}), 400
    except Exception as e:
        print(f"Error processing play request: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': str(e)}), 500


@app.route('/api/pause', methods=['POST'])
def pause_music():
    """Pause playback"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.pause()
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'paused'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resume', methods=['POST'])
def resume_music():
    """Resume playback"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.resume()
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'resumed'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/skip', methods=['POST'])
def skip_song():
    """Skip current song or background music"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        # Check if there's anything playing (regular song or BG music)
        if not session.voice_client or not session.voice_client.is_playing():
            return jsonify({'error': 'Nothing is playing'}), 404

        # Skip works for both regular songs and background music
        session.skip()
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'skipped'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_music():
    """Stop playback and clear queue"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.clear_queue()
        if session.voice_client and session.voice_client.is_playing():
            session.voice_client.stop()
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'stopped'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/volume', methods=['POST'])
def set_volume():
    """Set volume"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
        volume = int(data.get('volume'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id/volume'}), 400
    
    if volume is None:
        return jsonify({'error': 'Missing volume'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.set_volume(volume / 100)
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'volume_changed', 'volume': volume})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/loop', methods=['POST'])
def set_loop():
    """Set loop mode"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    mode = data.get('mode')
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400

    if not mode:
        return jsonify({'error': 'Missing loop mode'}), 400
        
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.loop_mode = LoopMode(mode)
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'loop_changed', 'mode': mode})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/shuffle', methods=['POST'])
def shuffle_queue():
    """Shuffle queue"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.shuffle()
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'shuffled'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear', methods=['POST'])
def clear_queue():
    """Clear queue"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.clear_queue()
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': 'cleared'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/radio', methods=['POST'])
def toggle_radio():
    """Toggle radio mode"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        if session.radio_mode:
            session.disable_radio_mode()
            action = 'radio_disabled'
            msg = 'Radio disabled'
        else:
            if session.current and not session.is_bg_playing:
                async def enable_radio():
                    await session.enable_radio_mode(session.current.video_id)
                run_async(enable_radio())
                action = 'radio_enabled'
                msg = 'Radio enabled'
            else:
                return jsonify({'error': 'Play a song first to start radio'}), 400
        
        socketio.emit('status_update', {'guild_id': str(guild_id), 'action': action})
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crossfade', methods=['POST'])
def toggle_crossfade():
    """Toggle crossfade"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    data = request.json
    try:
        guild_id = int(data.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid or missing guild_id'}), 400
    
    session = bot_instance.session_manager.get_session(guild_id)
    if not session:
        return jsonify({'error': 'No active session'}), 404
    
    try:
        session.crossfade_enabled = not session.crossfade_enabled
        socketio.emit('status_update', {
            'guild_id': str(guild_id), 
            'action': 'crossfade_toggled',
            'enabled': session.crossfade_enabled
        })
        return jsonify({'success': True, 'enabled': session.crossfade_enabled})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ================== WebSocket Events ==================
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('âœ¦ Client connected')
    emit('connected', {'message': 'Connected to bot'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('âœ¦ Client disconnected')

@socketio.on('request_status')
def handle_status_request():
    """Handle status request from client"""
    if bot_instance:
        try:
            sessions_data = []
            for guild_id, session in bot_instance.session_manager.sessions.items():
                guild = bot_instance.get_guild(guild_id)
                if guild:
                    session_info = {
                        'guild_id': str(guild_id),
                        'guild_name': guild.name,
                        'queue_size': len(session.queue),
                        'is_playing': session.voice_client.is_playing() if session.voice_client else False,
                        'volume': int(session.volume * 100)
                    }
                    if session.current and not session.is_bg_playing:
                        session_info['current_song'] = session.current.title
                    sessions_data.append(session_info)
            
            emit('status_update', {
                'online': True,
                'servers': len(bot_instance.guilds),
                'sessions': len(bot_instance.session_manager.sessions),
                'sessions_data': sessions_data
            })
        except Exception as e:
            emit('error', {'message': str(e)})

def broadcast_status_update():
    """Broadcast status update to all connected clients"""
    if bot_instance:
        try:
            sessions_data = []
            for guild_id, session in bot_instance.session_manager.sessions.items():
                guild = bot_instance.get_guild(guild_id)
                if guild:
                    sessions_data.append({
                        'guild_id': str(guild_id),
                        'guild_name': guild.name,
                        'queue_size': len(session.queue)
                    })
            
            socketio.emit('status_update', {
                'servers': len(bot_instance.guilds),
                'sessions': len(bot_instance.session_manager.sessions),
                'sessions_data': sessions_data
            })
        except:
            pass

# Start periodic status broadcasts
def start_status_broadcaster():
    """Start background task to broadcast status updates"""
    def broadcast():
        while True:
            time.sleep(5)
            broadcast_status_update()
    
    thread = threading.Thread(target=broadcast, daemon=True)
    thread.start()

# Start broadcaster when server starts
start_status_broadcaster()
