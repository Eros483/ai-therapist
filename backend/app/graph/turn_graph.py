"""Turn graph assembly (F010) — one LangGraph invocation per patient exchange (§7.3).

Topology::

    START
      → safety_l1_lexicon            [pure code, <1ms — L1 lexicon gate]
          ├─ hit ────────────────→ crisis_node → notify_emergency_contact → END
          └─ miss
             → parallel branch:     safety_l2_small_model ‖ register_classifier
                                    ‖ affect_from_audio ‖ state_extractor
             → join                 [trivial passthrough]
             → conditional edge:    L2 hit → crisis_node → notify_emergency_contact → END
                                    else → phase_agent[phase] (landing/opening/deepening/
                                    meaning/closing) → END

The load-bearing property (§7.3, §7.8): the phase agent NEVER runs on a crisis
utterance. L1 hit routes immediately (no LLM in the loop); L2 hit gates the
join — crisis_verdict is written by the parallel branch, and `route_from_join`
sends any crisis verdict down the crisis path.

The L1-hit branch never runs L2, so the L1 gate writes the verdict L2 would
have produced directly (category rides straight through from the lexicon hit,
confidence 1.0 — L1 is high precision, zero latency). `crisis_node` and
`notify_emergency_contact` already tolerate a missing/partial crisis_verdict.

Note on state channels: SessionState has no `l1_hit`/`l1_category` keys, and
langgraph drops node outputs that aren't in the TypedDict schema — so the L1
gate carries its verdict in the schema-valid `crisis_verdict` channel instead
of a dedicated (dropped) channel. On a miss it writes a benign placeholder so
a stale verdict from a resumed thread can never leak into this turn; L2
overwrites it in the parallel branch.

Node contracts (§7.5): every node is a pure function of SessionState returning
a partial state update; the only I/O in the whole graph is the declared LiteLLM
calls inside the L2 / extraction / phase / crisis nodes.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.affect import affect_node
from app.graph.nodes.crisis import crisis_node, notify_emergency_contact
from app.graph.nodes.extraction import extraction_node
from app.graph.nodes.phases import (
    closing_node,
    deepening_node,
    landing_node,
    meaning_node,
    opening_node,
)
from app.graph.nodes.register import register_node
from app.graph.nodes.safety import l1_lexicon_check, l2_safety_node
from app.graph.state import PHASES, SessionState

# --- node names (mirror §7.3) ---

PARALLEL_NODES = (
    "safety_l2_small_model",
    "register_classifier",
    "affect_from_audio",
    "state_extractor",
)

# Conditional-edge path map from the join: L2 hit → crisis path, else the phase
# agent named by state.phase. Exported so the routing is unit-testable.
phase_paths: dict[str, str] = {phase: phase for phase in PHASES} | {"crisis_node": "crisis_node"}


def _safety_l1_wrapper(state: SessionState) -> dict:
    """L1 lexicon gate — pure code, zero latency (§7.8 L1).

    On a hit writes the verdict L2 would have produced (L2 never runs on this
    branch): category rides through from the lexicon, confidence 1.0. On a miss
    writes a benign placeholder — L2 overwrites it in the parallel branch, and
    a stale verdict from a resumed thread can never leak into this turn.
    """
    result = l1_lexicon_check(state.get("patient_utterance", ""))
    if result["hit"]:
        return {
            "crisis_verdict": {
                "crisis": True,
                "category": result["category"] or "suicide",
                "confidence": 1.0,
            }
        }
    return {"crisis_verdict": {"crisis": False, "category": "none", "confidence": 0.0}}


def _join(state: SessionState) -> dict:
    """Trivial passthrough — the join point of the parallel branch."""
    return {}


def route_from_l1(state: SessionState) -> list[str]:
    """Conditional edge from the L1 gate: hit → crisis path; miss → parallel four."""
    if (state.get("crisis_verdict") or {}).get("crisis"):
        return ["crisis_node"]
    return list(PARALLEL_NODES)


def route_from_join(state: SessionState) -> str:
    """L2 gate: a crisis verdict sends the turn down the crisis path; otherwise
    the phase agent named by state.phase (landing default) runs."""
    if (state.get("crisis_verdict") or {}).get("crisis"):
        return "crisis_node"
    return state.get("phase", "landing")


def build_turn_graph(checkpointer=None) -> CompiledStateGraph:
    """Assemble the §7.3 turn graph over SessionState.

    ``checkpointer`` (optional) is a LangGraph BaseCheckpointSaver — the
    PostgresSaver from ``app.storage.db.make_checkpointer`` — passed to
    ``compile`` so per-turn state persists per thread (participant:session).
    """
    graph = StateGraph(SessionState)

    # --- nodes ---
    graph.add_node("safety_l1_lexicon", _safety_l1_wrapper)
    graph.add_node("safety_l2_small_model", l2_safety_node)
    graph.add_node("register_classifier", register_node)
    graph.add_node("affect_from_audio", affect_node)
    graph.add_node("state_extractor", extraction_node)
    graph.add_node("join", _join)
    for phase, node in zip(
        PHASES,
        (landing_node, opening_node, deepening_node, meaning_node, closing_node),
        strict=True,
    ):
        graph.add_node(phase, node)
    graph.add_node("crisis_node", crisis_node)
    graph.add_node("notify_emergency_contact", notify_emergency_contact)

    # --- edges ---
    graph.add_edge(START, "safety_l1_lexicon")

    # L1 gate: hit → crisis path; miss → parallel four.
    graph.add_conditional_edges("safety_l1_lexicon", route_from_l1)

    # parallel branch → join
    for node in PARALLEL_NODES:
        graph.add_edge(node, "join")

    # L2 gate at the join: crisis → crisis_node; else the phase agent by phase.
    graph.add_conditional_edges("join", route_from_join, phase_paths)
    for phase in PHASES:
        graph.add_edge(phase, END)

    # shared crisis tail
    graph.add_edge("crisis_node", "notify_emergency_contact")
    graph.add_edge("notify_emergency_contact", END)

    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)
