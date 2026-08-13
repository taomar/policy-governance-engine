"""Human-authored collaboration notes attached to a governed entity.

See `domain/models.py::Note` for the polymorphic entity_type/entity_id
design rationale. This is a cross-cutting feature used by all three actor
personas (system admin, policy composer/reviewer, policy manager) to leave
context, rationale, and sign-off remarks on policy sets, published versions,
candidate rules under review, and individual rules.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import CreateNoteRequest, NoteResponse
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.persistence.repositories import NoteRepository

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _to_response(note) -> NoteResponse:
    return NoteResponse(
        id=str(note.id),
        entity_type=note.entity_type,
        entity_id=note.entity_id,
        author=note.author,
        author_role=note.author_role,
        body=note.body,
        created_at=note.created_at,
    )


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    entity_type: str, entity_id: str, session: AsyncSession = Depends(get_session)
) -> list[NoteResponse]:
    repo = NoteRepository(session)
    notes = await repo.list_for_entity(entity_type=entity_type, entity_id=entity_id)
    return [_to_response(n) for n in notes]


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(
    payload: CreateNoteRequest, session: AsyncSession = Depends(get_session)
) -> NoteResponse:
    repo = NoteRepository(session)
    note = await repo.create(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        author=payload.author,
        author_role=payload.author_role,
        body=payload.body,
    )
    await session.commit()
    return _to_response(note)


@router.delete("/{note_id}", status_code=204, response_model=None)
async def delete_note(note_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    repo = NoteRepository(session)
    note = await repo.get_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    await repo.delete(note)
    await session.commit()
