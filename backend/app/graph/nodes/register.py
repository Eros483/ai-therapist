"""Register classifier node (F004) — pure function of text.

Assigns each patient utterance a register score on a 3-point scale plus a
continuous Code-Mixing Index (CMI), per implementation.md §2.1 and
methodology.md §3.3. This is a v0 rule-based heuristic; upgrades to
audio-feature + transcript classification are later work.

Deterministic mapping (pure function of text):
  * 2 (hindi-led):    Devanagari characters present, OR hi_ratio >= 0.5
  * 0 (formal-en):    no Devanagari, no Hindi words/particles (pure English)
  * 1 (hinglish):     everything else — CMI >= 0.5, or any high-signal
                      particle (yaar/matlab/na/bas), or a mixture

CMI = 1 - max(n_hi, n_en) / n over word tokens, where n_hi counts
Devanagari + romanized-Hindi lexicon tokens and n_en counts everything else.
Pure Hindi or pure English -> CMI 0.0 (no mixing); balanced Hinglish -> ~0.5+.
"""

from app.graph.state import SessionState

# CMI >= this is treated as code-mixed (Sengupta et al., HSSC 2024).
CMI_THRESHOLD = 0.5

# High-signal particles that mark a Hinglish register regardless of CMI
# (methodology.md §3.3). Exposed for use by phase agents.
PARTICLES: frozenset[str] = frozenset({"yaar", "matlab", "na", "bas"})

# v0 romanized-Hindi lexicon — common function/emotion/filler words. Matched
# case-insensitively on word tokens. ponytail: small hand-built set; swap for a
# trained detector when the register regression set (methodology.md §8) exists.
_ROMANIZED_HINDI: frozenset[str] = frozenset(
    {
        "main",
        "hoon",
        "hai",
        "nahi",
        "na",
        "mujhe",
        "tumhe",
        "kya",
        "kaun",
        "kyun",
        "aap",
        "tum",
        "bahut",
        "matlab",
        "yaar",
        "bas",
        "theek",
        "chahiye",
        "jaana",
        "aana",
        "karna",
        "kiya",
        "kar",
        "raha",
        "rahi",
        "tha",
        "thi",
        "bhi",
        "ke",
        "ki",
        "ka",
        "ko",
        "se",
        "mein",
        "aur",
    }
)

_DEVANAGARI_START, _DEVANAGARI_END = 0x0900, 0x097F


def _is_devanagari(word: str) -> bool:
    return any(_DEVANAGARI_START <= ord(ch) <= _DEVANAGARI_END for ch in word)


def _is_hindi_word(word: str) -> bool:
    return _is_devanagari(word) or word.lower() in _ROMANIZED_HINDI


def cmi(text: str) -> float:
    """Code-Mixing Index: 1 - max(n_hi, n_en)/n over word tokens."""
    tokens = [t for t in text.split() if t]
    n = len(tokens)
    if n == 0:
        return 0.0
    n_hi = sum(1 for t in tokens if _is_hindi_word(t))
    n_en = n - n_hi
    return 1.0 - max(n_hi, n_en) / n


def classify_register(text: str) -> dict:
    """Return {"register": int, "cmi": float} for a single utterance."""
    tokens = [t for t in text.split() if t]
    n = len(tokens)
    n_hi = sum(1 for t in tokens if _is_hindi_word(t))
    hi_ratio = n_hi / n if n else 0.0
    has_devanagari = any(_is_devanagari(t) for t in tokens)
    lower = text.lower()

    if has_devanagari or hi_ratio >= 0.5:
        register = 2
    elif n == 0 or (n_hi == 0 and not any(p in lower for p in PARTICLES)):
        register = 0
    else:
        register = 1

    return {"register": register, "cmi": cmi(text)}


def register_node(state: SessionState) -> dict:
    """LangGraph node: reads state["patient_utterance"], returns a partial
    state update {"register": {"register": int, "cmi": float}}."""
    return {"register": classify_register(state["patient_utterance"])}
