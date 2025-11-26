# note-organizer-214120-214129

## Smoke Test Checklist

Backend (FastAPI) port: 3001
Frontend (React) port: 3000

1) Ensure backend running and DB initialized
   - GET http://localhost:3001/ should return { "message": "Healthy", ... }
2) Create a note
   - POST http://localhost:3001/api/notes
     Body: { "title": "Test Note", "content": "Hello" }
   - Expect 201 and returned note object.
3) List notes
   - GET http://localhost:3001/api/notes
   - Verify "Test Note" appears.
4) Realtime
   - Connect to ws://localhost:3001/ws
   - In another tab, POST another note; expect a "note.created" event payload.
5) Frontend
   - In notes_frontend/.env set REACT_APP_API_URL=http://localhost:3001
   - Start frontend and ensure notes list loads.

CORS is configured to allow http://localhost:3000 and common WebSocket headers during development.
SQLite is used by default if DATABASE_URL is not set (sqlite:///./notes.db).