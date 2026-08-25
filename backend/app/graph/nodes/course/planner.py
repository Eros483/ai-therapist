"""Course planner node (F009) — summary + prior CourseState → updated
formulation, milestone evaluation (§4.3), next_session_intention.

Runs as the second node of the post-session graph (impl §4.2, §7.4). Per §7.5
this node runs the SMALL model (`settings.extraction_model`) and emits strict
JSON:

    {presenting_threads: [str], working_pattern: str|null,
     confirmed_insight: str|null, next_session_intention: str}

The milestone predicates are pure functions of CourseState; the course_phase
is computed in CODE (deterministic), never by the model. The session summary
is appended to prior session_summaries (append, don't wipe).
"""

import json
import re

import litellm

from app.config.settings import settings
from app.graph.state import CourseState, Formulation
from app.logger import logger

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

# Template uses .replace() placeholders (not str.format) so the JSON braces in
# the schema description can't collide with format fields.
_PROMPT_TEMPLATE = (
    "You are the course-planner for an 8-session therapy course. From the "
    "session summary and the prior course state, propose how the formulation "
    "and next-session intention should update. Emit STRICTLY this JSON shape "
    "and nothing else:\n"
    '{"presenting_threads": [str], "working_pattern": str|null, '
    '"confirmed_insight": str|null, "next_session_intention": str}\n'
    "- presenting_threads: the course's presenting threads, updated by this "
    "session.\n"
    "- working_pattern: the cross-session pattern (set once it recurs across "
    ">= 2 sessions), or null if none yet.\n"
    "- confirmed_insight: the patient's own words naming an insight this "
    "session, or null if none. Verbatim, never the AI's phrasing.\n"
    "- next_session_intention: the Landing seed for the next session.\n"
    "Session summary:\n{summary}\n"
    "Prior course state:\n{course}\n"
    "Return only the JSON."
)


def parse_planner(content: str) -> dict:
    """Strict-JSON parse of the planner output (style of extraction.py)."""
    match = _JSON_BLOCK_RE.search(content or "")
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# --- §4.3 milestone predicates (pure functions of CourseState) ---


def confirmed_insight_exists(course: CourseState) -> bool:
    """True when the patient has confirmed at least one insight, verbatim.

    The Working → Termination milestone (methodology.md §5.3): the patient's
    own words, their agreement — not the AI's assertion.
    """
    formulation = course.get("formulation") or {}
    return bool(formulation.get("confirmed_insights"))


def pattern_recurs_across_sessions(course: CourseState, min_sessions: int = 2) -> bool:
    """True when a working pattern has been set (Exploration → Working).

    A pattern recurs across ≥2 sessions (cross-session recurrence, not
    within-session repetition). The predicate is over the formulation's
    working_pattern, which the planner sets once recurrence is observed.
    """
    formulation = course.get("formulation") or {}
    return bool(formulation.get("working_pattern"))


def evaluate_course_phase(course: CourseState) -> str:
    """Compute the course phase per §4.3 — deterministic, not a model call.

    Ordering (delayed-never-rushed, calendar-bounded):
      * session <= 2                     -> foundation
      * session >= 8                     -> termination (calendar-bounded)
      * a confirmed insight exists       -> termination (Working → Termination edge)
      * a working pattern is set         -> working
      * otherwise                        -> exploration

    NOTE: the literal snippet in impl §4.3 returns "working→termination" for
    the confirmed-insight edge as a *transition marker*. Here we return the
    concrete phase value "termination", since `course_phase` must be one of
    foundation/exploration/working/termination (COURSE_PHASES). Session 8 is
    Termination regardless of milestone state.
    """
    if course.get("session_number", 1) <= 2:
        return "foundation"
    if course.get("session_number", 1) >= 8:
        return "termination"
    if confirmed_insight_exists(course):
        return "termination"
    if pattern_recurs_across_sessions(course, min_sessions=2):
        return "working"
    return "exploration"


# --- node ---


def _build_prompt(summary: dict, course: CourseState) -> str:
    return _PROMPT_TEMPLATE.replace("{summary}", json.dumps(summary, ensure_ascii=False)).replace(
        "{course}", json.dumps(course, ensure_ascii=False)
    )


async def course_planner_node(state: dict) -> dict:
    """LangGraph node: summary + prior CourseState → formulation update,
    milestone evaluation, next_session_intention.

    The SMALL model proposes formulation + intention (this is the §7.5
    "small" hop). The course_phase is computed in code from the updated
    CourseState via evaluate_course_phase — the milestone verdict is
    deterministic, never the model's word. Prior session_summaries are
    preserved (append, don't wipe).

    Returns the partial update {"course": <updated CourseState>}.
    """
    course: CourseState = dict(state.get("course") or {})
    summary = state.get("summary") or {}
    session_number = state.get("session_number", course.get("session_number", 1))

    formulation: Formulation = dict(course.get("formulation") or {})
    formulation.setdefault("presenting_threads", [])
    formulation.setdefault("working_pattern", None)
    formulation.setdefault("confirmed_insights", [])

    # Append the new summary (append, don't wipe).
    summaries = list(course.get("session_summaries") or [])
    summaries.append(summary)

    try:
        completion = await litellm.acompletion(
            model=settings.extraction_model,
            messages=[{"role": "user", "content": _build_prompt(summary, course)}],
            temperature=0.0,
        )
        parsed = parse_planner(completion.choices[0].message.content)
    except Exception as exc:  # model failure -> carry prior formulation unchanged
        logger.warning("course_planner_node: model call failed: %s", exc)
        parsed = {}

    if parsed:
        if isinstance(parsed.get("presenting_threads"), list):
            formulation["presenting_threads"] = [str(t) for t in parsed["presenting_threads"]]
        if parsed.get("working_pattern"):
            formulation["working_pattern"] = str(parsed["working_pattern"])
        insight = parsed.get("confirmed_insight")
        if insight and insight not in formulation["confirmed_insights"]:
            formulation["confirmed_insights"].append(str(insight))
        next_intention = str(parsed.get("next_session_intention", ""))
    else:
        logger.warning("course_planner_node: parse failure; carrying prior formulation")
        next_intention = course.get("next_session_intention", "")

    updated: CourseState = dict(course)
    updated["session_number"] = session_number
    updated["session_summaries"] = summaries
    updated["formulation"] = formulation
    updated["next_session_intention"] = next_intention
    updated["course_phase"] = evaluate_course_phase(updated)

    return {"course": updated}
