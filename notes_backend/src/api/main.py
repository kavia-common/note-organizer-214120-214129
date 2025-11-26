from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db.database import engine
from src.db.database import Base  # Declarative base
from src.api.routes.notes import router as notes_router
from src.api.routes.tags import router as tags_router
from src.api.realtime import router as realtime_router

openapi_tags = [
    {
        "name": "health",
        "description": "Service health and status endpoints.",
    },
    {
        "name": "notes",
        "description": "Operations related to notes.",
    },
    {
        "name": "tags",
        "description": "Operations related to tags.",
    },
    {
        "name": "realtime",
        "description": "WebSocket real-time connection endpoints and documentation.",
    },
]

app = FastAPI(
    title="Notes Backend",
    description="API for managing notes and tags with real-time-ready architecture.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# Explicitly allow local frontend origin and include common WebSocket upgrade headers
# Note: Starlette's CORS does not govern WebSocket connections (the browser does not
# enforce CORS on WS the same way), but allowing upgrade headers helps with proxies.
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Keep wildcard permissive during dev if proxies or other tools are used
    "*",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Upgrade", "Connection", "Sec-WebSocket-Protocol"],
)


@app.on_event("startup")
def on_startup() -> None:
    """
    Initialize database tables on application startup.

    Uses SQLAlchemy metadata to create tables if they do not already exist.
    """
    # Create all tables based on models imported under Base.metadata
    Base.metadata.create_all(bind=engine)


@app.get("/", tags=["health"], summary="Health Check")
def health_check():
    """Health endpoint that returns a simple status message and a smoke test checklist."""
    return {
        "message": "Healthy",
        "smoke_test": {
            "api_base": "http://localhost:3001",
            "frontend_base": "http://localhost:3000",
            "steps": [
                "1) POST http://localhost:3001/api/notes with {\"title\":\"Test Note\",\"content\":\"Hello\"}",
                "2) GET http://localhost:3001/api/notes and verify the created note appears",
                "3) Open WebSocket ws://localhost:3001/ws and create another note to see a note.created event",
                "4) From frontend, set REACT_APP_API_URL=http://localhost:3001 and ensure notes list renders"
            ]
        }
    }


# PUBLIC_INTERFACE
@app.get(
    "/realtime",
    tags=["realtime"],
    summary="Realtime WebSocket usage",
    description="Describes how to connect to the WebSocket and sample events.",
)
def realtime_usage() -> dict:
    """
    Returns guidance on connecting to the WebSocket endpoint.

    Returns:
        Dict with fields:
          - endpoint: ws path to connect
          - sample_event: example payload pushed by the server
          - notes: general notes on usage
    """
    return {
        "endpoint": "/ws",
        "sample_event": {
            "type": "note.created",
            "entity": "note",
            "action": "created",
            "payload": {"id": 1, "title": "Example", "content": "Body", "created_at": "...", "updated_at": "...", "tags": []},
        },
        "notes": "Connect using a WebSocket client to /ws; the server broadcasts note/tag events on create/update/delete.",
    }


# Include API routers under /api namespace and register websocket router at root
app.include_router(notes_router)
app.include_router(tags_router)
app.include_router(realtime_router)
