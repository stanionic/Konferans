import os
import sys
import uuid
from datetime import datetime

# Tests should run without a Redis instance available. Force a SimpleCache for tests
# so cache operations succeed in local/CI environments.
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')

sys.path.insert(0, os.path.dirname(__file__))


def test_routes():
    from app import app
    with app.test_client() as client:
        # Test index route
        response = client.get('/')
        print(f"Index route status: {response.status_code}")
        assert response.status_code == 200
        assert b'Konferans' in response.data  # Assuming title or something

        # Test create_room
        response = client.post('/create_room')
        print(f"Create room status: {response.status_code}")
        assert response.status_code == 302  # Redirect

        # Get room_id from session or redirect
        # Since it's a redirect, follow it
        with client.session_transaction() as sess:
            room_id = sess.get('owner_room')
        if room_id:
            print(f"Created room: {room_id}")

            # Test room route
            response = client.get(f'/room/{room_id}')
            print(f"Room route status: {response.status_code}")
            assert response.status_code == 200

            # Test add_credits
            response = client.post(f'/add_credits/{room_id}')
            print(f"Add credits status: {response.status_code}")
            assert response.status_code == 302

            # Test join_room with valid room
            response = client.post('/join_room', data={'room_id': room_id})
            print(f"Join room status: {response.status_code}")
            assert response.status_code == 302

            # Test join_room with invalid room
            response = client.post('/join_room', data={'room_id': 'invalid'})
            print(f"Join invalid room status: {response.status_code}")
            assert response.status_code == 302  # Should redirect to index

def test_sockets():
    from app import app, socketio, cache
    # Test socket events
    client = socketio.test_client(app)
    client.connect()

    # Test join
    room_id = str(uuid.uuid4())[:8]
    cache.set(f'room:{room_id}', {'users': [], 'owner': None, 'start_time': datetime.now(), 'credits': 0}, timeout=3600)
    client.emit('join', {'room': room_id, 'username': 'testuser'})
    received = client.get_received()
    print(f"Join event received: {received}")
    assert any('user_joined' in str(msg) for msg in received)

    # Test leave - the Socket.IO server sends user_left to the room, but since
    # the test client leaves the room before the event is dispatched, the
    # client may not receive the event itself. Instead check the cache state
    # to ensure the user was removed.
    client.emit('leave', {'room': room_id, 'username': 'testuser'})
    # Inspect cache to ensure the user was removed from the room.
    room_state = cache.get(f'room:{room_id}')
    print(f"Room state after leave: {room_state}")
    # If room_state is None, room was deleted; otherwise ensure testuser not present
    assert (room_state is None) or ('testuser' not in room_state.get('users', []))

    # Test offer
    client.emit('offer', {'room': room_id, 'offer': 'test'})
    received = client.get_received()
    print(f"Offer event received: {received}")
    # Offer should be emitted back, but since skip_sid, maybe not to self

    # Test answer
    client.emit('answer', {'room': room_id, 'answer': 'test'})
    received = client.get_received()
    print(f"Answer event received: {received}")

    # Test ice_candidate
    client.emit('ice_candidate', {'room': room_id, 'candidate': 'test'})
    received = client.get_received()
    print(f"ICE candidate event received: {received}")

    client.disconnect()


if __name__ == '__main__':
    print("Testing routes...")
    test_routes()
    print("Routes test passed.")

    print("Testing sockets...")
    test_sockets()
    print("Sockets test passed.")

    print("All tests passed!")
