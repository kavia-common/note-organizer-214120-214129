from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import Tag
from src.db.schemas import TagCreate, TagRead

router = APIRouter(prefix="/api/tags", tags=["tags"])


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[TagRead],
    summary="List tags",
    description="Retrieve all tags.",
)
def list_tags(db: Session = Depends(get_db)) -> List[TagRead]:
    """
    List all tags ordered by name.
    """
    tags = db.execute(select(Tag).order_by(Tag.name.asc())).scalars().all()
    return tags


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create tag",
    description="Create a new tag by name. Name must be unique.",
)
def create_tag(payload: TagCreate, db: Session = Depends(get_db)) -> TagRead:
    """
    Create a tag with a unique name. 409 if name exists.
    """
    existing = db.execute(select(Tag).where(Tag.name == payload.name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag name already exists")
    tag = Tag(name=payload.name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


# PUBLIC_INTERFACE
@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tag",
    description="Delete a tag by ID.",
)
def delete_tag(tag_id: int, db: Session = Depends(get_db)) -> None:
    """
    Delete the tag. Associated note relationships are removed by cascade.
    """
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return None
