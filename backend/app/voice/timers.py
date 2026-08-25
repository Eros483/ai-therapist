"""Two distinct voice-loop timers (impl §7.7) — never conflated:

1. **Turn-end VAD threshold** — seconds of silence before the system decides
   *patient finished speaking* vs *patient thinking*. Phase-dependent
   (Deepening > Landing): the therapeutically load-bearing knob (methodology
   §6.4 — aggressive endpointing destroys the container by cutting silences
   short).
2. **90-second silence check-in** — one soft utterance ("I'm here whenever
   you're ready"), fired ONCE, never repeated (methodology §4.5).

Both are pure functions — the voice loop owns applying them (Pipecat VAD
params / check-in scheduling).
"""

from app.config.settings import settings

DEFAULT_SILENCE_CHECKIN_SECONDS = 90


def vad_threshold_for_phase(
    phase: str,
    thresholds: dict[str, float] | None = None,
    fallback: float = 1.5,
) -> float:
    """Turn-end VAD threshold (seconds) for a phase.

    `thresholds` defaults to ``settings.turn_end_vad_thresholds``. Unknown
    phases fall back to ``fallback`` (never raises — the phase set may grow).
    """
    thresholds = thresholds if thresholds is not None else settings.turn_end_vad_thresholds
    return thresholds.get(phase, fallback)


def silence_checkin_should_fire(
    seconds_elapsed: float,
    checkin_seconds: int = DEFAULT_SILENCE_CHECKIN_SECONDS,
    fired: bool = False,
) -> bool:
    """The 90s soft check-in fires once, at the first crossing, never again."""
    if fired:
        return False
    return seconds_elapsed >= checkin_seconds


def phase_prosody_directive(phase: str) -> str:
    """§7.7 prosody directive map — merged into the TTS call per phase."""
    return {
        "landing": "warm, relaxed pace",
        "opening": "warm, steady pace",
        "deepening": "slower, lower energy, longer inter-sentence pauses",
        "meaning": "measured, gentle, reflective",
        "closing": "settled, grounded pace",
    }.get(phase, "warm, natural, empathetic")
