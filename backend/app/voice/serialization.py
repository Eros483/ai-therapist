"""Browser voice-loop serialization (F011).

Pipecat ships only telephony serializers (Twilio, Plivo, ...); the control
surface is a plain browser client, so we define a tiny JSON + base64-PCM
protocol::

    in   {"type":"audio","data":"<base64 pcm16>", "sample_rate":16000}  -> InputAudioRawFrame
    out  AudioRawFrame -> {"type":"audio","sample_rate":24000,"num_channels":1,
                           "data":"<base64 pcm16>"}

Anything else is ignored (``None``) — the browser doesn't see VAD/system frames.
"""

import base64
import json

from pipecat.frames.frames import AudioRawFrame, Frame, InputAudioRawFrame
from pipecat.serializers.base_serializer import FrameSerializer


class BrowserFrameSerializer(FrameSerializer):
    """JSON/base64 PCM16 frames between the browser and the Pipecat pipeline."""

    async def serialize(self, frame: Frame) -> str | None:
        if not isinstance(frame, AudioRawFrame):
            return None
        return json.dumps(
            {
                "type": "audio",
                "sample_rate": frame.sample_rate,
                "num_channels": frame.num_channels,
                "data": base64.b64encode(frame.audio).decode("ascii"),
            }
        )

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        try:
            message = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(message, dict) or message.get("type") != "audio":
            return None
        try:
            audio = base64.b64decode(message["data"])
        except (ValueError, KeyError):
            return None
        return InputAudioRawFrame(
            audio=audio,
            sample_rate=int(message.get("sample_rate", 16000)),
            num_channels=int(message.get("num_channels", 1)),
        )
