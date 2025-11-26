from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.database import get_db
from src.db.models import Note, Tag, note_tags
from src.db.schemas import NoteCreate, NoteRead, NoteUpdate
from src.api.realtime import broadcast_event  # realtime broadcasting

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _apply_note_filters(
    stmt,
    search: Optional[str],
    tag: Optional[str],
    pinned: Optional[bool],
    archived: Optional[bool],
    trashed: Optional[bool],
):
    """
    Internal utility to apply filters to a SQLAlchemy select statement.

    We implement soft-state flags using pseudo rules:
      - archived/trashed/pinned are inferred from title prefixes:
        * "[ARCHIVED]" prefix => archived=True
        * "[TRASH]" prefix => trashed=True
        * "[PIN]" prefix => pinned=True
    This keeps schema unchanged as models don't include these columns.
    """
    # These are string-based conventions to simulate flags without schema fields.
    if pinned is not None:
        if pinned:
            stmt = stmt.where(Note.title.like("[PIN] %"))
        else:
            stmt = stmt.where(~Note.title.like("[PIN] %"))
    if archived is not None:
        if archived:
            stmt = stmt.where(Note.title.like("[ARCHIVED] %"))
        else:
            stmt = stmt.where(~Note.title.like("[ARCHIVED] %"))
    if trashed is not None:
        if trashed:
            stmt = stmt.where(Note.title.like("[TRASH] %"))
        else:
            stmt = stmt.where(~Note.title.like("[TRASH] %"))

    if search:
        like = f"%{search}%"
        stmt = stmt.where((Note.title.ilike(like)) | (Note.content.ilike(like)))

    if tag:
        # Join with tags to filter by tag name
        stmt = (
            stmt.join(note_tags, note_tags.c.note_id == Note.id)
            .join(Tag, Tag.id == note_tags.c.tag_id)
            .where(Tag.name == tag)
        )
    return stmt


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[NoteRead],
    summary="List notes",
    description="List notes with optional filters for search, tag, pinned, archived, trashed.",
)
def list_notes(
    search: Optional[str] = Query(None, description="Free text search in title/content"),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    pinned: Optional[bool] = Query(None, description="Filter by pinned state"),
    archived: Optional[bool] = Query(None, description="Filter by archived state"),
    trashed: Optional[bool] = Query(None, description="Filter by trashed state"),
    db: Session = Depends(get_db),
) -> List[NoteRead]:
    """
    Retrieve all notes applying the optional filters.
    """
    stmt = select(Note).options(selectinload(Note.tags)).order_by(Note.updated_at.desc())
    stmt = _apply_note_filters(stmt, search, tag, pinned, archived, trashed)
    notes = db.execute(stmt).scalars().unique().all()
    return notes


# PUBLIC_INTERFACE
@router.get(
    "/{note_id}",
    response_model=NoteRead,
    summary="Get note by ID",
    description="Retrieve a single note by its ID.",
)
def get_note(note_id: int, db: Session = Depends(get_db)) -> NoteRead:
    """
    Get a single note by id or raise 404.
    """
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    # Force load tags for response completeness
    _ = note.tags  # access relationship
    return note


def _resolve_tags_by_ids(db: Session, tag_ids: Optional[List[int]]) -> List[Tag]:
    if tag_ids is None:
        return []
    if not tag_ids:
        return []
    tags = db.execute(select(Tag).where(Tag.id.in_(tag_ids))).scalars().all()
    if len(tags) != len(set(tag_ids)):
        raise HTTPException(status_code=400, detail="One or more tag IDs are invalid")
    return tags


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create note",
    description="Create a new note with optional associated tag IDs.",
)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> NoteRead:
    """
    Create a new note and optionally attach tags by their IDs.
    """
    tags: List[Tag] = _resolve_tags_by_ids(db, payload.tag_ids)
    note = Note(title=payload.title, content=payload.content)
    if tags:
        note.tags = tags
    db.add(note)
    db.commit()
    db.refresh(note)
    # Ensure relationships loaded
    _ = note.tags
    # Broadcast event
    try:
        # Create a response-like dict following NoteRead schema
        payload_dict = NoteRead.model_validate(note).model_dump()
        # Fire and forget
        import asyncio
        asyncio.create_task(broadcast_event("note", "created", payload_dict))
    except Exception:
        # Do not fail the request due to broadcast issues
        pass
    return note


# PUBLIC_INTERFACE
@router.patch(
    "/{note_id}",
    response_model=NoteRead,
    summary="Update note",
    description="Patch update a note's title/content and tag associations.",
)
def update_note(note_id: int, payload: NoteUpdate, db: Session = Depends(get_db)) -> NoteRead:
    """
    Update mutable fields and optionally overwrite tag associations.
    """
    note: Optional[Note] = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if payload.title is not None:
        note.title = payload.title
    if payload.content is not None:
        note.content = payload.content
    if payload.tag_ids is not None:
        tags = _resolve_tags_by_ids(db, payload.tag_ids)
        note.tags = tags

    db.add(note)
    db.commit()
    db.refresh(note)
    _ = note.tags
    try:
        payload_dict = NoteRead.model_validate(note).model_dump()
        import asyncio
        asyncio.create_task(broadcast_event("note", "updated", payload_dict))
    except Exception:
        pass
    return note


# PUBLIC_INTERFACE
@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete note",
    description="Soft delete a note by marking it as trashed using a title prefix.",
)
def soft_delete_note(note_id: int, db: Session = Depends(get_db)) -> None:
    """
    Soft-delete using a title prefix convention to avoid schema changes.
    """
    note: Optional[Note] = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if not note.title.startswith("[TRASH] "):
        note.title = f"[TRASH] {note.title}"
    db.add(note)
    db.commit()
    try:
        import asyncio
        # return minimal payload to indicate which id changed
        asyncio.create_task(broadcast_event("note", "deleted", {"id": note_id}))
    except Exception:
        pass
    return None


def _ensure_no_duplicate_prefix(title: str, prefix: str) -> str:
    # remove existing prefix if present, then add once
    if title.startswith(prefix):
        # already has correct prefix
        return title
    # remove other mutually exclusive prefixes before setting this one
    for other in ("[PIN] ", "[ARCHIVED] ", "[TRASH] "):
        if other != prefix and title.startswith(other):
            title = title[len(other) :]
            break
    return f"{prefix}{title}"


# PUBLIC_INTERFACE
@router.post(
    "/{note_id}/archive",
    response_model=NoteRead,
    summary="Archive note",
    description="Mark a note as archived via a title prefix convention.",
)
def archive_note(note_id: int, db: Session = Depends(get_db)) -> NoteRead:
    note: Optional[Note] = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    note.title = _ensure_no_duplicate_prefix(note.title, "[ARCHIVED] ")
    db.add(note)
    db.commit()
    db.refresh(note)
    _ = note.tags
    try:
        payload_dict = NoteRead.model_validate(note).model_dump()
        import asyncio
        asyncio.create_task(broadcast_event("note", "updated", payload_dict))
    except Exception:
        pass
    return note


# PUBLIC_INTERFACE
@router.post(
    "/{note_id}/restore",
    response_model=NoteRead,
    summary="Restore note",
    description="Remove special prefixes to restore a note from archived/trashed states.",
)
def restore_note(note_id: int, db: Session = Depends(get_db)) -> NoteRead:
    note: Optional[Note] = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    # Remove any known prefixes
    for prefix in ("[ARCHIVED] ", "[TRASH] "):
        if note.title.startswith(prefix):
            note.title = note.title[len(prefix) :]
            break
    db.add(note)
    db.commit()
    db.refresh(note)
    _ = note.tags
    try:
        payload_dict = NoteRead.model_validate(note).model_dump()
        import asyncio
        asyncio.create_task(broadcast_event("note", "updated", payload_dict))
    except Exception:
        pass
    return note


# PUBLIC_INTERFACE
@router.post(
    "/{note_id}/pin",
    response_model=NoteRead,
    summary="Pin/Unpin note",
    description="Toggle pin state via title prefix '[PIN] '. If currently pinned, unpin; otherwise pin.",
)
def pin_toggle_note(note_id: int, db: Session = Depends(get_db)) -> NoteRead:
    note: Optional[Note] = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.title.startswith("[PIN] "):
        note.title = note.title[len("[PIN] ") :]
    else:
        # Remove other prefixes that conflict with pin? Keep them as-is, pin can combine.
        if not note.title.startswith("[PIN] "):
            note.title = f"[PIN] {note.title}"
    db.add(note)
    db.commit()
    db.refresh(note)
    _ = note.tags
    try:
        payload_dict = NoteRead.model_validate(note).model_dump()
        import asyncio
        asyncio.create_task(broadcast_event("note", "updated", payload_dict))
    except Exception:
        pass
    return note
