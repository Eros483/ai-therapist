"""Provider selection by config (impl §7.11) — eval-time swappable, never a
hardcoded default. Unknown providers raise `ValueError` naming the allowed
values, so a typo'd env var fails fast at startup rather than at the first
voice turn.
"""

from app.config.settings import settings
from app.voice.services.bulbul_tts import SarvamBulbulTTS
from app.voice.services.protocols import STTProvider, TTSProvider
from app.voice.services.rumik_tts import RumikMulberryTTS
from app.voice.services.sarvam_stt import SarvamSTT

_STT_PROVIDERS = {"sarvam": SarvamSTT}
_TTS_PROVIDERS = {"sarvam": SarvamBulbulTTS, "rumik": RumikMulberryTTS}


def get_stt_provider() -> STTProvider:
    provider = settings.stt_provider
    try:
        cls = _STT_PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown STT provider {provider!r}; allowed: {', '.join(sorted(_STT_PROVIDERS))}"
        ) from None
    return cls(api_key=settings.sarvam_api_key)


def get_tts_provider() -> TTSProvider:
    provider = settings.tts_provider
    try:
        cls = _TTS_PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown TTS provider {provider!r}; allowed: {', '.join(sorted(_TTS_PROVIDERS))}"
        ) from None
    if cls is RumikMulberryTTS:
        return cls(api_key=settings.rumik_api_key)
    return cls(api_key=settings.sarvam_api_key)
