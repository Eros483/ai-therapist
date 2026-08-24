"""Graph state schemas — SessionState (§5.1) and CourseState (§4.1) as
LangGraph TypedDicts. Graph nodes are pure functions of state; the transient
per-turn channels (patient_utterance, register, crisis_verdict, next_technique,
response) are inputs/outputs of a single turn-graph invocation."""

from typing import TypedDict


class InterruptionEvent(TypedDict):
    interrupted_what: str
    phase: str
    when_min: float


class AudioAffect(TypedDict):
    arousal_trajectory: str
    flat_prosody_streak: bool


class SessionState(TypedDict, total=False):
    # --- tracked session state (§5.1) ---
    phase: str
    elapsed_minutes: float
    exchange_count: int
    baseline_affect: str
    primary_thread: str
    dropped_threads: list[str]
    key_words_used: list[str]
    language_map: dict[str, str]
    body_locations_mentioned: list[str]
    tentative_pattern: str
    interruption_events: list[InterruptionEvent]
    audio_affect: AudioAffect
    # --- per-turn transient channels ---
    patient_utterance: str
    register: dict[str, float]
    crisis_verdict: dict[str, object]
    next_technique: str
    response: str


class SessionSummary(TypedDict):
    n: int
    distillation: str
    carry_forward: str
    outcome: str


class Formulation(TypedDict):
    presenting_threads: list[str]
    working_pattern: str | None
    confirmed_insights: list[str]


class CourseState(TypedDict, total=False):
    session_number: int
    course_phase: str
    session_summaries: list[SessionSummary]
    formulation: Formulation
    next_session_intention: str
    unresolved_threads: list[str]


PHASES = ("landing", "opening", "deepening", "meaning", "closing")
COURSE_PHASES = ("foundation", "exploration", "working", "termination")


def make_thread_id(participant_id: str, session_number: int) -> str:
    """Checkpointer thread_id per §7.6: participant:{id}:session:{n}."""
    return f"participant:{participant_id}:session:{session_number}"


def participant_thread_prefix(participant_id: str) -> str:
    """Prefix matching every thread belonging to a participant (deletion cascade)."""
    return f"participant:{participant_id}:session:"


def new_session_state(**overrides) -> SessionState:
    state: SessionState = {
        "phase": "landing",
        "elapsed_minutes": 0.0,
        "exchange_count": 0,
        "baseline_affect": "",
        "primary_thread": "",
        "dropped_threads": [],
        "key_words_used": [],
        "language_map": {},
        "body_locations_mentioned": [],
        "tentative_pattern": "",
        "interruption_events": [],
        "audio_affect": {"arousal_trajectory": "steady", "flat_prosody_streak": False},
    }
    state.update(overrides)
    return state


def new_course_state(**overrides) -> CourseState:
    state: CourseState = {
        "session_number": 1,
        "course_phase": "foundation",
        "session_summaries": [],
        "formulation": {
            "presenting_threads": [],
            "working_pattern": None,
            "confirmed_insights": [],
        },
        "next_session_intention": "",
        "unresolved_threads": [],
    }
    state.update(overrides)
    return state
