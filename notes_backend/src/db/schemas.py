from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# Base Tag schema
class TagBase(BaseModel):
    name: str = Field(..., description="Unique name for the tag", min_length=1, max_length=64)


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, description="New name for the tag", min_length=1, max_length=64)


class TagRead(TagBase):
    id: int = Field(..., description="Unique identifier for the tag")

    class Config:
        from_attributes = True


# Base Note schema
class NoteBase(BaseModel):
    title: str = Field(..., description="Title of the note", min_length=1, max_length=255)
    content: Optional[str] = Field(None, description="Content/body of the note")


class NoteCreate(NoteBase):
    tag_ids: Optional[List[int]] = Field(default=None, description="List of tag IDs to associate with the note")


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Updated title of the note", min_length=1, max_length=255)
    content: Optional[str] = Field(None, description="Updated content of the note")
    tag_ids: Optional[List[int]] = Field(default=None, description="Updated list of associated tag IDs")


class NoteRead(NoteBase):
    id: int = Field(..., description="Unique identifier for the note")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    tags: List[TagRead] = Field(default_factory=list, description="Tags associated with the note")

    class Config:
        from_attributes = True
