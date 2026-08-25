"""TTS-boundary script normalization (impl §2.2).

Romanized Hindi is the canonical form upstream of TTS. Rumik Mulberry expects
Hindi in Devanagari and English in Latin, so the romanized → Devanagari step
lives here, at the TTS boundary. Providers whose input script is the canonical
Latin form (e.g. Sarvam Bulbul, which accepts code-mixed romanized text
natively) pass text through unchanged via `normalize_to_provider_script`.

v0 is a modest best-effort lookup table for common romanized Hindi tokens.
Tokens in the table are transliterated; everything else (English words,
unknown romanized words, already-Devanagari text) passes through unchanged.
This is deliberately small and honest — a full transliterator is a later
model-based step. Known collision: English "main" maps to "मैं"; the table
cannot disambiguate without context.
"""

import re

# Devanagari block: U+0900–U+097F.
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Common romanized Hindi tokens → Devanagari (lowercase keys).
_ROMANIZED_MAP = {
    "aap": "आप",
    "achha": "अच्छा",
    "aisa": "ऐसा",
    "aisi": "ऐसी",
    "apne": "अपने",
    "aur": "और",
    "bahut": "बहुत",
    "bas": "बस",
    "batao": "बताओ",
    "bataiye": "बताइए",
    "bhi": "भी",
    "chalo": "चलो",
    "dard": "दर्द",
    "dekho": "देखो",
    "dil": "दिल",
    "din": "दिन",
    "dukh": "दुख",
    "gaya": "गया",
    "gayi": "गई",
    "ghar": "घर",
    "hai": "है",
    "hain": "हैं",
    "ho": "हो",
    "hoon": "हूँ",
    "kaam": "काम",
    "kab": "कब",
    "kahan": "कहाँ",
    "kaise": "कैसे",
    "kaun": "कौन",
    "khushi": "खुशी",
    "kitna": "कितना",
    "koi": "कोई",
    "kuch": "कुछ",
    "kya": "क्या",
    "kyun": "क्यों",
    "lekin": "लेकिन",
    "maan": "मान",
    "main": "मैं",
    "matlab": "मतलब",
    "mehsoos": "महसूस",
    "mere": "मेरे",
    "mujhe": "मुझे",
    "na": "ना",
    "nahin": "नहीं",
    "par": "पर",
    "pyaar": "प्यार",
    "raat": "रात",
    "ruko": "रुको",
    "sab": "सब",
    "samajh": "समझ",
    "soch": "सोच",
    "socho": "सोचो",
    "suno": "सुनो",
    "sunaiye": "सुनाइए",
    "tere": "तेरे",
    "thak": "थक",
    "thik": "ठीक",
    "tujhe": "तुझे",
    "tum": "तुम",
    "waqt": "वक़्त",
    "yaad": "याद",
    "yaar": "यार",
    "zindagi": "ज़िंदगी",
}

_WORD_RE = re.compile(r"[A-Za-z]+")


def has_devanagari(text: str) -> bool:
    """True if the text contains any Devanagari character."""
    return bool(_DEVANAGARI_RE.search(text))


def romanized_to_devanagari(text: str) -> str:
    """Best-effort transliteration of known romanized Hindi tokens to Devanagari.

    English words, unknown romanized tokens, and already-Devanagari text pass
    through unchanged.
    """

    def _translate(match: re.Match[str]) -> str:
        return _ROMANIZED_MAP.get(match.group(0).lower(), match.group(0))

    return _WORD_RE.sub(_translate, text)


def normalize_to_provider_script(text: str, provider_script: str) -> str:
    """Normalize canonical text to a TTS provider's required script (§2.2).

    `provider_script` is ``"devanagari"`` (Rumik Mulberry) or ``"latin"``
    (canonical form — unchanged, e.g. Sarvam Bulbul).
    """
    if provider_script == "devanagari":
        return romanized_to_devanagari(text)
    if provider_script == "latin":
        return text
    raise ValueError(f"Unknown provider script {provider_script!r}; allowed: devanagari, latin")
