"""BrowserFrameSerializer round-trip tests — the /ws <-> browser protocol."""

import base64
import json

import pytest
from pipecat.frames.frames import AudioRawFrame, InputAudioRawFrame, TextFrame

from app.voice.serialization import BrowserFrameSerializer

PCM = b"\x00\x00\xff\x7f\x01\x80"


@pytest.mark.asyncio
async def test_serialize_audio_frame_to_json():
    frame = AudioRawFrame(audio=PCM, sample_rate=24000, num_channels=1)
    payload = await BrowserFrameSerializer().serialize(frame)
    msg = json.loads(payload)
    assert msg["type"] == "audio"
    assert msg["sample_rate"] == 24000
    assert msg["num_channels"] == 1
    assert base64.b64decode(msg["data"]) == PCM


@pytest.mark.asyncio
async def test_serialize_ignores_non_audio_frames():
    s = BrowserFrameSerializer()
    assert await s.serialize(TextFrame("hi")) is None


@pytest.mark.asyncio
async def test_deserialize_audio_message_to_input_frame():
    msg = json.dumps(
        {"type": "audio", "data": base64.b64encode(PCM).decode(), "sample_rate": 16000}
    )
    frame = await BrowserFrameSerializer().deserialize(msg)
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.audio == PCM
    assert frame.sample_rate == 16000
    assert frame.num_channels == 1


@pytest.mark.asyncio
async def test_deserialize_ignores_junk():
    s = BrowserFrameSerializer()
    assert await s.deserialize("not json") is None
    assert await s.deserialize(json.dumps({"type": "other"})) is None
    assert await s.deserialize(json.dumps({"type": "audio", "data": "!!not-base64!!"})) is None
    assert await s.deserialize(b"garbage") is None


@pytest.mark.asyncio
async def test_deserialize_bytes_input():
    msg = json.dumps({"type": "audio", "data": base64.b64encode(PCM).decode()})
    frame = await BrowserFrameSerializer().deserialize(msg.encode())
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.sample_rate == 16000  # default when absent
