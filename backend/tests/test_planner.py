"""Pure milestone-predicate tests for the course planner (F009).

These predicates are pure functions of CourseState per §4.3 — no I/O, no
model. They drive the Foundation → Exploration → Working → Termination
transitions, calendar-bounded at session 8.
"""

from app.graph.nodes.course.planner import (
    confirmed_insight_exists,
    evaluate_course_phase,
    pattern_recurs_across_sessions,
)
from app.graph.state import new_course_state


def _course(**overrides):
    return new_course_state(**overrides)


# --- confirmed_insight_exists ---


def test_confirmed_insight_exists_false_when_empty():
    course = _course(
        formulation={"presenting_threads": [], "working_pattern": None, "confirmed_insights": []}
    )
    assert confirmed_insight_exists(course) is False


def test_confirmed_insight_exists_true_when_present():
    course = _course(
        formulation={
            "presenting_threads": [],
            "working_pattern": None,
            "confirmed_insights": ["I disappear so no one can reject me"],
        }
    )
    assert confirmed_insight_exists(course) is True


# --- pattern_recurs_across_sessions ---


def test_pattern_recurs_across_sessions_false_when_unset():
    course = _course(
        formulation={"presenting_threads": [], "working_pattern": None, "confirmed_insights": []}
    )
    assert pattern_recurs_across_sessions(course, min_sessions=2) is False


def test_pattern_recurs_across_sessions_true_when_set():
    course = _course(
        formulation={
            "presenting_threads": [],
            "working_pattern": "feeling unseen by authority figures",
            "confirmed_insights": [],
        }
    )
    assert pattern_recurs_across_sessions(course, min_sessions=2) is True


# --- evaluate_course_phase (§4.3) ---


def test_foundation_when_session_two_or_less():
    course = _course(session_number=1)
    assert evaluate_course_phase(course) == "foundation"
    assert evaluate_course_phase(_course(session_number=2)) == "foundation"


def test_exploration_when_no_insight_or_pattern():
    course = _course(session_number=3)
    assert evaluate_course_phase(course) == "exploration"


def test_working_when_pattern_set():
    course = _course(
        session_number=4,
        formulation={
            "presenting_threads": [],
            "working_pattern": "feeling unseen by authority figures",
            "confirmed_insights": [],
        },
    )
    assert evaluate_course_phase(course) == "working"


def test_termination_by_confirmed_insight():
    course = _course(
        session_number=5,
        formulation={
            "presenting_threads": [],
            "working_pattern": "feeling unseen",
            "confirmed_insights": ["I disappear so no one can reject me"],
        },
    )
    assert evaluate_course_phase(course) == "termination"


def test_termination_by_calendar_at_session_8_without_milestones():
    course = _course(session_number=8)
    assert evaluate_course_phase(course) == "termination"
    assert evaluate_course_phase(_course(session_number=9)) == "termination"


def test_evaluate_handles_missing_formulation_without_crash():
    # CourseState where the formulation block is entirely absent.
    course = new_course_state(session_number=3)
    course.pop("formulation", None)
    assert evaluate_course_phase(course) == "exploration"
    assert confirmed_insight_exists(course) is False
    assert pattern_recurs_across_sessions(course, min_sessions=2) is False
