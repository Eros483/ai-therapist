"""Sarvam Bulbul streaming TTS — `TTSProvider` implementation (impl §7.9, §8.3).

Wraps the sarvamai SDK's HTTP streaming `text_to_speech.convert_stream`,
yielding audio bytes as they arrive.

Bulbul accepts code-mixed romanized text natively (SDK docs), so the §2.2
canonical romanized form passes through unchanged — no script normalization
at this boundary. The §7.7 prosody directive map merges into the SDK's
pitch/pace/loudness params, which pins the model to `bulbul:v2` (v3 drops
pitch/loudness). On any SDK error it logs and yields nothing — a failed
synthesis must not crash the voice loop.
"""

from collections.abc import AsyncIterator

from sarvamai import AsyncSarvamAI

from app.config.settings import settings
from app.logger import logger


class SarvamBulbulTTS:
    """Bulbul TTS over the sarvamai SDK's streaming convert_stream."""

    # bulbul:v2 keeps pitch/loudness — required by the §7.7 prosody flow.
    _DEFAULT_MODEL = "bulbul:v2"
    _LANGUAGE_CODE = "hi-IN"
    _PROSODY_KEYS = ("pitch", "pace", "loudness")

    def __init__(self, api_key: str | None = None, client: AsyncSarvamAI | None = None):
        if client is None:
            client = AsyncSarvamAI(api_subscription_key=api_key or settings.sarvam_api_key)
        self._client = client

    @staticmethod
    def _sdk_params(prosody: dict | None) -> dict:
        if not prosody:
            return {}
        return {
            key: value
            for key, value in prosody.items()
            if key in SarvamBulbulTTS._PROSODY_KEYS and value is not None
        }

    async def synthesize(self, text: str, prosody: dict | None = None) -> AsyncIterator[bytes]:
        try:
            stream = self._client.text_to_speech.convert_stream(
                text=text,
                language_code=self._LANGUAGE_CODE,
                model=self._DEFAULT_MODEL,
                **self._sdk_params(prosody),
            )
            async for chunk in stream:
                yield chunk
        except Exception:
            logger.exception("Sarvam Bulbul TTS failed; yielding no audio")
            return
