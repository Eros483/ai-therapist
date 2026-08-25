"""Post-session course graph (F009) — synthesis → planner → persist (impl §4.2,
§7.4). Runs once, async, after session close — zero turn latency.

Topology: START → synthesis_node → course_planner_node → persist → END.
The persist node writes the updated CourseState via app.storage.course_store
(encrypted at rest, keyed by participant).

``build_course_graph(database_url=None)`` — when a URL is given, persist
writes to that DB (tests pass the test DB); otherwise put_course defaults to
settings.database_url.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.course import course_planner_node, synthesis_node
from app.graph.state import CourseState, SessionState, SessionSummary
from app.logger import logger
from app.storage.course_store import put_course


class CourseGraphState(TypedDict, total=False):
    """Transient input/output channels for the post-session course graph."""

    participant_id: str
    session_number: int
    transcript: list[str]
    final_session_state: SessionState
    course: CourseState
    summary: SessionSummary


def build_course_graph(database_url: str | None = None):
    """Assemble and compile the post-session course graph.

    ``database_url`` is captured by the persist node's closure so tests can
    point at the test DB; when None, put_course defaults to settings.
    """

    async def _persist_node(state: CourseGraphState) -> dict:
        """Declared I/O node: write the updated CourseState to the course store."""
        participant_id = state["participant_id"]
        course = state["course"]
        try:
            await put_course(participant_id, course, database_url=database_url)
            logger.info(
                "course persisted for participant %s session %s",
                participant_id,
                course.get("session_number"),
            )
        except Exception as exc:  # post-session path must not crash the pipeline
            logger.warning("course persist failed for participant %s: %s", participant_id, exc)
        return {}

    builder = StateGraph(CourseGraphState)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("planner", course_planner_node)
    builder.add_node("persist", _persist_node)

    builder.add_edge(START, "synthesis")
    builder.add_edge("synthesis", "planner")
    builder.add_edge("planner", "persist")
    builder.add_edge("persist", END)

    return builder.compile()
