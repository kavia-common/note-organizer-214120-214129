from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db.database import engine
from src.db.database import Base  # Declarative base
from src.api.routes.notes import router as notes_router
from src.api.routes.tags import router as tags_router

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
]

app = FastAPI(
    title="Notes Backend",
    description="API for managing notes and tags with real-time-ready architecture.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Health endpoint that returns a simple status message."""
    return {"message": "Healthy"}


# Include API routers under /api namespace
app.include_router(notes_router)
app.include_router(tags_router)
