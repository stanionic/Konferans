from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_session import Session
from flask_caching import Cache
import uuid
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here')
app.config['SESSION_TYPE'] = os.environ.get('SESSION_TYPE', 'filesystem')
# Allow overriding cache type in env; default to RedisCache for production deployments
app.config['CACHE_TYPE'] = os.environ.get('CACHE_TYPE', 'RedisCache')
app.config['CACHE_REDIS_URL'] = os.environ.get('REDIS_URL', 'redis://localhost:6379')

Session(app)

# Initialize cache but fall back safely to an in-memory SimpleCache when Redis is unavailable.
def _create_cache(app):
    """Create and return a Cache instance. If RedisCache is configured but unavailable,
    fall back to SimpleCache so the app remains usable in dev/test environments.
    """
    try:
        cache = Cache(app)
        # If RedisCache is in use, performs a small write/read to ensure connection succeeds.
        if app.config.get('CACHE_TYPE') == 'RedisCache':
            try:
                cache.set('_cache_ping', '1', timeout=1)
                cache.delete('_cache_ping')
            except Exception:
                raise
        return cache
    except Exception as e:
        app.logger.warning('Cache init failed (%s). Falling back to SimpleCache.', e)
        app.config['CACHE_TYPE'] = 'SimpleCache'
        return Cache(app)

cache = _create_cache(app)

socketio = SocketIO(app, cors_allowed_origins="*")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_credits/<room_id>', methods=['POST'])
def add_credits(room_id):
    room_data = cache.get(f'room:{room_id}')
    if room_data:
        room_data['credits'] += 1  # Add 1 credit, adjust as needed
        cache.set(f'room:{room_id}', room_data, timeout=3600)
    return redirect(url_for('room', room_id=room_id))

@app.route('/create_room', methods=['POST'])
def create_room():
    room_id = str(uuid.uuid4())[:8]
    room_data = {'users': [], 'owner': None, 'start_time': datetime.now(), 'credits': 0}
    cache.set(f'room:{room_id}', room_data, timeout=3600)  # Cache for 1 hour
    session['owner_room'] = room_id
    return redirect(url_for('room', room_id=room_id))

@app.route('/join_room', methods=['POST'])
def join_room_route():
    room_id = request.form.get('room_id')
    room_data = cache.get(f'room:{room_id}')
    if room_data:
        elapsed = (datetime.now() - room_data['start_time']).total_seconds() / 60
        if elapsed > 40 and room_data['credits'] <= 0:
            return redirect(url_for('index'))  # Don't allow joining expired rooms
        return redirect(url_for('room', room_id=room_id))
    return redirect(url_for('index'))

@app.route('/room/<room_id>')
def room(room_id):
    room_data = cache.get(f'room:{room_id}')
    if not room_data:
        return redirect(url_for('index'))
    is_owner = session.get('owner_room') == room_id
    elapsed = (datetime.now() - room_data['start_time']).total_seconds() / 60
    if elapsed > 40 and room_data['credits'] <= 0:
        return redirect(url_for('index'))  # Redirect if expired
    return render_template(
        'room.html',
        room_id=room_id,
        is_owner=is_owner,
        elapsed=elapsed,
        credits=room_data['credits'],
    )

@socketio.on('join')
def on_join(data):
    try:
        room_id = data['room']
        username = data['username'].strip()[:20]  # Sanitize: strip whitespace, limit to 20 chars
        if not username:
            emit('error', {'message': 'Invalid username'})
            return
        join_room(room_id)
        room_data = cache.get(f'room:{room_id}')
        if not room_data:
            room_data = {'users': [], 'owner': None, 'start_time': datetime.now(), 'credits': 0}
        if username not in room_data['users']:
            room_data['users'].append(username)
            cache.set(f'room:{room_id}', room_data, timeout=3600)
            emit('user_joined', {'username': username}, room=room_id)
    except Exception as e:
        emit('error', {'message': 'Failed to join room'})
        print(f"Error in on_join: {e}")

@socketio.on('leave')
def on_leave(data):
    try:
        room_id = data['room']
        username = data['username'].strip()[:20]  # Sanitize: strip whitespace, limit to 20 chars
        leave_room(room_id)
        room_data = cache.get(f'room:{room_id}')
        if room_data and username in room_data['users']:
            room_data['users'].remove(username)
            if not room_data['users']:
                cache.delete(f'room:{room_id}')
            else:
                cache.set(f'room:{room_id}', room_data, timeout=3600)
            emit('user_left', {'username': username}, room=room_id)
    except Exception as e:
        emit('error', {'message': 'Failed to leave room'})
        print(f"Error in on_leave: {e}")

@socketio.on('offer')
def on_offer(data):
    try:
        emit('offer', data, room=data['room'], skip_sid=request.sid)
    except Exception as e:
        print(f"Error in on_offer: {e}")

@socketio.on('answer')
def on_answer(data):
    try:
        room_id = data['room']
        room_data = cache.get(f'room:{room_id}')
        if room_data:
            elapsed = (datetime.now() - room_data['start_time']).total_seconds() / 60  # minutes
            if elapsed > 40 and room_data['credits'] <= 0:
                emit('error', {'message': 'Session expired. Please add credits to continue.'})
                leave_room(room_id)
                return
            elif elapsed > 30 and room_data['credits'] <= 0:
                remaining = 40 - elapsed
                message = (
                    f'Free session ends in {remaining:.1f} minutes. '
                    'Add credits to continue.'
                )
                emit('warning', {'message': message}, room=room_id)
        emit('answer', data, room=data['room'], skip_sid=request.sid)
    except Exception as e:
        print(f"Error in on_answer: {e}")

@socketio.on('ice_candidate')
def on_ice_candidate(data):
    try:
        room_id = data['room']
        room_data = cache.get(f'room:{room_id}')
        if room_data:
            elapsed = (datetime.now() - room_data['start_time']).total_seconds() / 60  # minutes
            if elapsed > 40 and room_data['credits'] <= 0:
                emit('error', {'message': 'Session expired. Please add credits to continue.'})
                leave_room(room_id)
                return
            elif elapsed > 30 and room_data['credits'] <= 0:
                remaining = 40 - elapsed
                message = (
                    f'Free session ends in {remaining:.1f} minutes. '
                    'Add credits to continue.'
                )
                emit('warning', {'message': message}, room=room_id)
        emit('ice_candidate', data, room=data['room'], skip_sid=request.sid)
    except Exception as e:
        print(f"Error in on_ice_candidate: {e}")

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
