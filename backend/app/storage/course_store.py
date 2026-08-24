"""CourseState persistence (impl §4.2, §5.4-5.5).

Course rows are encrypted at rest (Fernet) and keyed by participant. The
deletion cascade (participant's right to delete session history, §5.5) removes
the course row AND every checkpointer thread for that participant. Functions
accept an optional ``database_url`` so tests target a separate database.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.graph.state import CourseState, participant_thread_prefix
from app.storage.crypto import decrypt_str, encrypt_str
from app.storage.db import Base, make_checkpointer, session_factory


class CourseRecord(Base):
    __tablename__ = "course_records"

    participant_id: Mapped[str] = mapped_column(String, primary_key=True)
    state_blob: Mapped[str] = mapped_column(String)  # encrypted CourseState JSON
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


async def get_course(participant_id: str, database_url: str | None = None) -> CourseState | None:
    async with session_factory(database_url)() as session:
        row = await session.get(CourseRecord, participant_id)
        if row is None:
            return None
        return json.loads(decrypt_str(row.state_blob))


async def put_course(
    participant_id: str, state: CourseState, database_url: str | None = None
) -> None:
    blob = encrypt_str(json.dumps(state, ensure_ascii=False))
    async with session_factory(database_url)() as session:
        row = await session.get(CourseRecord, participant_id)
        if row is None:
            session.add(
                CourseRecord(
                    participant_id=participant_id,
                    state_blob=blob,
                    updated_at=datetime.now(UTC),
                )
            )
        else:
            row.state_blob = blob
            row.updated_at = datetime.now(UTC)
        await session.commit()


async def delete_course(participant_id: str, database_url: str | None = None) -> None:
    async with session_factory(database_url)() as session:
        row = await session.get(CourseRecord, participant_id)
        if row is not None:
            await session.delete(row)
            await session.commit()


async def delete_participant(participant_id: str, database_url: str | None = None) -> None:
    """Deletion cascade (§5.5): course rows + checkpointer threads."""
    await delete_course(participant_id, database_url)
    async with make_checkpointer(database_url) as saver:
        await saver.setup()
        prefix = participant_thread_prefix(participant_id)
        # collect ids while the cursor is open, then delete (adelete_thread
        # on the same connection would deadlock mid-iteration)
        thread_ids = [
            ckpt.config["configurable"]["thread_id"]
            async for ckpt in saver.alist(None)
            if ckpt.config["configurable"]["thread_id"].startswith(prefix)
        ]
        for thread_id in thread_ids:
            await saver.adelete_thread(thread_id)
