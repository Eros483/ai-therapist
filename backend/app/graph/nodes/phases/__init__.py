"""Five phase-specialized therapist agents (F007).

All nodes share the identical signature `async (state: SessionState) -> dict`
returning {"response": str} so F010's conditional edge can call any of them
uniformly. Shared scaffold lives in _common.py; each module adds its phase's
[PHASE INSTRUCTION] + technique subset."""

from app.graph.nodes.phases.closing import closing_node
from app.graph.nodes.phases.deepening import deepening_node
from app.graph.nodes.phases.landing import landing_node
from app.graph.nodes.phases.meaning import meaning_node
from app.graph.nodes.phases.opening import opening_node

__all__ = [
    "landing_node",
    "opening_node",
    "deepening_node",
    "meaning_node",
    "closing_node",
]
