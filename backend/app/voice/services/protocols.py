"""Provider protocols for the voice layer (impl §7.9).

Concrete implementations live in `app/voice/services/` and are selected by
config (§7.11) — never hardcoded. Both protocols are async and streaming to
match the SDKs they wrap and the Pipecat voice loop that consumes them.

`STTProvider.transcribe_stream` is the streaming form deliberately: the SDK's
realtime STT (Sarvam Saaras) is a stateful WebSocket that takes chunked
audio and emits utterance-final transcripts — there is no single-shot
`transcribe(bytes)` to wrap. The voice loop owns turn detection; this
protocol only converts an audio stream into a transcript stream.

`TTSProvider.synthesize` takes the §7.7 prosody directive map and returns
streaming audio bytes. Providers degrade to an empty stream on error — the
voice loop never crashes on a failed synthesis or transcription.
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    """Streaming speech-to-text: audio chunks in, utterance transcripts out."""

    async def transcribe_stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]: ...


@runtime_checkable
class TTSProvider(Protocol):
    """Streaming text-to-speech: text + prosody out as an audio byte stream."""

    async def synthesize(self, text: str, prosody: dict | None = None) -> AsyncIterator[bytes]: ...
