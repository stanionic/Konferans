# TODO for Flask App Improvements

- [x] Update cache config to RedisCache in app.py
- [x] Replace SECRET_KEY with environment variable
- [x] Remove global rooms = {} dict
- [x] Modify create_room route to use cache fully
- [x] Modify join_room_route to use cache
- [x] Modify room route to use cache
- [x] Update on_join socket event: get from cache, prevent duplicates, sanitize username, set back
- [x] Update on_leave socket event: similar logic
- [x] Add error handling in socket events
- [x] Test the app by running it
