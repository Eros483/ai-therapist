"""Sarvam Saaras streaming STT — `STTProvider` implementation (impl §7.9, §8.3).

Wraps the sarvamai SDK's realtime streaming STT (a stateful WebSocket): audio
chunks in, `transcript.final` events out. Requests `mode="translit"` so Hindi
arrives romanized — the §2.2 canonical form upstream of the graph — and
`language_code="auto"` for Hinglish code-mixed speech.

The voice loop owns turn detection; this client only converts an audio stream
into a transcript stream, then sends `end` so the server finalizes the
pending utterance. On any SDK error it logs and yields nothing — a failed
transcription must not crash the voice loop.
"""

import base64
from collections.abc import AsyncIterator

from sarvamai import AsyncSarvamAI
from sarvamai.types import RealtimeAudioInput, RealtimeEnd, RealtimeTranscriptFinal

from app.config.settings import settings
from app.logger import logger


class SarvamSTT:
    """Streaming STT over the sarvamai realtime WebSocket (Saaras)."""

    def __init__(self, api_key: str | None = None, client: AsyncSarvamAI | None = None):
        if client is None:
            client = AsyncSarvamAI(api_subscription_key=api_key or settings.sarvam_api_key)
        self._client = client

    async def transcribe_stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]:
        try:
            async with self._client.speech_to_text_realtime_streaming.connect(
                language_code="auto",
                mode="translit",
            ) as socket:
                async for chunk in audio:
                    encoded = base64.b64encode(chunk).decode("ascii")
                    await socket.send_realtime_audio_input(RealtimeAudioInput(audio=encoded))
                await socket.send_realtime_end(RealtimeEnd())
                async for message in socket:
                    if isinstance(message, RealtimeTranscriptFinal):
                        yield message.text
        except Exception:
            logger.exception("Sarvam STT stream failed; yielding no transcript")
            return
