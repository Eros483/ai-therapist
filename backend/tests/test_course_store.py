"""Course-store integration tests against the local Postgres test database.

Requires `make setup` (Postgres container). Tests target a separate
`aitherapy_test` database and use unique participant ids, so they are
idempotent and leave the dev `aitherapy` DB untouched.
"""

import uuid

import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from app.graph.state import SessionState, make_thread_id, new_course_state
from app.storage.course_store import (
    CourseRecord,
    delete_course,
    delete_participant,
    get_course,
    put_course,
)
from app.storage.db import init_db, session_factory

TEST_URL = "postgresql+asyncpg://aitherapy:aitherapy@localhost:5432/aitherapy_test"
CHECKPOINTER_URL = "postgresql://aitherapy:aitherapy@localhost:5432/aitherapy_test"


def _pid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture(scope="module")
async def _db():
    await init_db(TEST_URL)
    yield


async def _wipe_course_rows():
    async with session_factory(TEST_URL)() as session:
        await session.execute(CourseRecord.__table__.delete())
        await session.commit()


async def _create_thread(participant_id: str, session_number: int) -> str:
    """Write a real checkpoint thread via AsyncPostgresSaver."""
    builder = StateGraph(SessionState)
    builder.add_node("noop", lambda s: {"exchange_count": (s.get("exchange_count", 0) + 1)})
    builder.add_edge(START, "noop")
    builder.add_edge("noop", END)

    async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URL) as saver:
        await saver.setup()
        graph = builder.compile(checkpointer=saver)
        thread_id = make_thread_id(participant_id, session_number)
        await graph.ainvoke(
            {"patient_utterance": "hello"},
            config={"configurable": {"thread_id": thread_id}},
        )
    return thread_id


async def _thread_exists(thread_id: str) -> bool:
    async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URL) as saver:
        await saver.setup()
        async for checkpoint in saver.alist(None):
            if checkpoint.config["configurable"]["thread_id"] == thread_id:
                return True
    return False


async def test_put_and_get_round_trip(_db):
    await _wipe_course_rows()
    pid = _pid("rt")
    state = new_course_state(
        session_number=3,
        course_phase="exploration",
        next_session_intention="open with the small noticing",
    )
    await put_course(pid, state, TEST_URL)

    loaded = await get_course(pid, TEST_URL)
    assert loaded == state
    assert loaded["session_number"] == 3
    assert loaded["next_session_intention"] == "open with the small noticing"


async def test_get_missing_returns_none(_db):
    pid = _pid("missing")
    assert await get_course(pid, TEST_URL) is None


async def test_put_overwrites(_db):
    await _wipe_course_rows()
    pid = _pid("ow")
    await put_course(pid, new_course_state(session_number=1), TEST_URL)
    await put_course(pid, new_course_state(session_number=2), TEST_URL)
    assert (await get_course(pid, TEST_URL))["session_number"] == 2


async def test_storage_is_encrypted_at_rest(_db):
    await _wipe_course_rows()
    pid = _pid("enc")
    marker = "unencrypted-marker-should-not-appear"
    await put_course(pid, new_course_state(next_session_intention=marker), TEST_URL)
    async with session_factory(TEST_URL)() as session:
        row = await session.get(CourseRecord, pid)
        assert marker not in row.state_blob


async def test_delete_course(_db):
    pid = _pid("del")
    await put_course(pid, new_course_state(), TEST_URL)
    await delete_course(pid, TEST_URL)
    assert await get_course(pid, TEST_URL) is None


async def test_delete_participant_cascades_threads(_db):
    await _wipe_course_rows()
    pid = _pid("cascade")
    await put_course(pid, new_course_state(session_number=1), TEST_URL)
    thread_1 = await _create_thread(pid, 1)
    thread_2 = await _create_thread(pid, 2)
    other_thread = await _create_thread(_pid("other"), 1)

    assert await _thread_exists(thread_1)
    assert await _thread_exists(thread_2)

    await delete_participant(pid, TEST_URL)

    assert await get_course(pid, TEST_URL) is None
    assert not await _thread_exists(thread_1)
    assert not await _thread_exists(thread_2)
    assert await _thread_exists(other_thread)
