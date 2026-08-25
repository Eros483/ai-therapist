"""F012 — voice provider services.

Tests mirror the structure of app/voice/services/: script normalization
(§2.2), protocol conformance (§7.9), provider degradation (never crash the
voice loop), and config-driven selection (§7.11).

The Rumik API is paused (no free tier, no key) — every Rumik test runs
against an injected fake httpx transport; the live API is never called.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sarvamai.types import RealtimeTranscriptFinal

from app.config.settings import settings
from app.voice.services.bulbul_tts import SarvamBulbulTTS
from app.voice.services.factory import get_stt_provider, get_tts_provider
from app.voice.services.protocols import STTProvider, TTSProvider
from app.voice.services.rumik_tts import RumikMugaTTS, RumikMulberryTTS
from app.voice.services.sarvam_stt import SarvamSTT
from app.voice.services.script import (
    has_devanagari,
    normalize_to_provider_script,
    romanized_to_devanagari,
)

# ---------------------------------------------------------------------------
# script.py — TTS-boundary normalization (§2.2)
# ---------------------------------------------------------------------------


def test_has_devanagari_detects_devanagari_block():
    assert has_devanagari("कैसे हो")
    assert has_devanagari("मैं ठीक हूँ")
    assert not has_devanagari("kaise ho")
    assert not has_devanagari("How are you")


def test_romanized_tokens_map_to_devanagari():
    assert romanized_to_devanagari("kaise ho") == "कैसे हो"
    assert romanized_to_devanagari("thik hoon") == "ठीक हूँ"
    assert (
        romanized_to_devanagari("mujhe samajh nahin aata") == "मुझे समझ नहीं aata"
    )  # aata unknown → passthrough


def test_english_tokens_pass_through_unchanged():
    text = "I feel okay today"
    assert romanized_to_devanagari(text) == text


def test_already_devanagari_text_untouched():
    text = "मैं ठीक हूँ"
    assert romanized_to_devanagari(text) == text


def test_mixed_text_transliterates_only_known_tokens():
    assert romanized_to_devanagari("I feel thik hoon") == "I feel ठीक हूँ"


def test_punctuation_preserved():
    assert romanized_to_devanagari("kaise, ho?") == "कैसे, हो?"
    assert romanized_to_devanagari("kaise ho.") == "कैसे हो."


def test_normalize_to_provider_script_switches_boundary_script():
    assert normalize_to_provider_script("kaise ho", "devanagari") == "कैसे हो"
    assert normalize_to_provider_script("kaise ho", "latin") == "kaise ho"
    with pytest.raises(ValueError):
        normalize_to_provider_script("kaise ho", "klingon")


# ---------------------------------------------------------------------------
# protocols — §7.9 conformance
# ---------------------------------------------------------------------------


def test_concrete_providers_conform_to_protocols():
    assert isinstance(SarvamSTT(client=object()), STTProvider)
    assert isinstance(SarvamBulbulTTS(client=object()), TTSProvider)
    assert isinstance(RumikMulberryTTS(transport=object(), api_key="k"), TTSProvider)
    assert isinstance(RumikMugaTTS(transport=object(), api_key="k"), TTSProvider)


# ---------------------------------------------------------------------------
# sarvam_stt.py — Saaras realtime streaming STT
# ---------------------------------------------------------------------------


async def _aiter(items):
    for item in items:
        yield item


class _FakeSttSocket:
    """Mimics AsyncSpeechToTextRealtimeStreamingSocketClient: audio in, events out."""

    def __init__(self, finals):
        self._finals = finals
        self.sent_audio = []
        self.ended = False

    async def send_realtime_audio_input(self, message):
        self.sent_audio.append(message.audio)

    async def send_realtime_end(self, message):
        self.ended = True

    def __aiter__(self):
        async def _gen():
            for final in self._finals:
                yield final

        return _gen()


class _FakeRealtimeStreaming:
    def __init__(self, socket):
        self._socket = socket
        self.connect_kwargs = None

    @asynccontextmanager
    async def connect(self, **kwargs):
        self.connect_kwargs = kwargs
        yield self._socket


class _FailingConnect:
    @asynccontextmanager
    async def connect(self, **kwargs):
        raise RuntimeError("stt down")
        yield None  # pragma: no cover — makes this a generator for asynccontextmanager


def _fake_sarvam_client(socket=None, streaming=None):
    streaming = streaming or _FakeRealtimeStreaming(socket)
    return SimpleNamespace(speech_to_text_realtime_streaming=streaming)


@pytest.mark.asyncio
async def test_sarvam_stt_streams_final_transcripts():
    socket = _FakeSttSocket(
        [
            RealtimeTranscriptFinal(utterance_idx=0, text="kaise ho"),
            RealtimeTranscriptFinal(utterance_idx=1, text="thik hoon"),
        ]
    )
    stt = SarvamSTT(client=_fake_sarvam_client(socket))
    audio_chunks = [b"\x00" * 100, b"\x01" * 100]

    results = [t async for t in stt.transcribe_stream(_aiter(audio_chunks))]

    assert results == ["kaise ho", "thik hoon"]
    assert len(socket.sent_audio) == 2  # every chunk forwarded
    assert socket.ended  # RealtimeEnd sent so the server finalizes the utterance


@pytest.mark.asyncio
async def test_sarvam_stt_requests_romanized_output():
    streaming = _FakeRealtimeStreaming(_FakeSttSocket([]))
    stt = SarvamSTT(client=_fake_sarvam_client(streaming=streaming))

    _ = [t async for t in stt.transcribe_stream(_aiter([b"x"]))]

    assert streaming.connect_kwargs["mode"] == "translit"  # §2.2 canonical form
    assert streaming.connect_kwargs["language_code"] == "auto"


@pytest.mark.asyncio
async def test_sarvam_stt_uses_settings_key_when_no_client(monkeypatch):
    captured = {}

    class _FakeSarvamAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import app.voice.services.sarvam_stt as module

    monkeypatch.setattr(module, "AsyncSarvamAI", _FakeSarvamAI)
    monkeypatch.setattr(settings, "sarvam_api_key", "sk-test")

    SarvamSTT()

    assert captured["api_subscription_key"] == "sk-test"


@pytest.mark.asyncio
async def test_sarvam_stt_degrades_to_empty_on_error():
    stt = SarvamSTT(client=_fake_sarvam_client(streaming=_FailingConnect()))

    results = [t async for t in stt.transcribe_stream(_aiter([b"x"]))]

    assert results == []  # logged, never raised — the voice loop survives


# ---------------------------------------------------------------------------
# bulbul_tts.py — Sarvam Bulbul streaming TTS
# ---------------------------------------------------------------------------


class _FakeTextToSpeech:
    def __init__(self, chunks=()):
        self._chunks = chunks
        self.calls = []

    async def convert_stream(self, **kwargs):
        self.calls.append(kwargs)
        for chunk in self._chunks:
            yield chunk


class _FailingTextToSpeech:
    async def convert_stream(self, **kwargs):
        raise RuntimeError("tts down")
        yield b""  # pragma: no cover — makes this an async generator


def _fake_tts_client(tts):
    return SimpleNamespace(text_to_speech=tts)


@pytest.mark.asyncio
async def test_bulbul_synthesize_maps_prosody_and_streams_audio():
    tts = _FakeTextToSpeech(chunks=[b"\xff\xfb", b"\x00\x01"])
    bulbul = SarvamBulbulTTS(client=_fake_tts_client(tts))

    audio = [
        c
        async for c in bulbul.synthesize(
            "kaise ho", prosody={"pace": 0.8, "loudness": 1.2, "pitch": 0.1}
        )
    ]

    assert audio == [b"\xff\xfb", b"\x00\x01"]
    call = tts.calls[0]
    assert call["pace"] == 0.8
    assert call["loudness"] == 1.2
    assert call["pitch"] == 0.1
    assert call["language_code"] == "hi-IN"


@pytest.mark.asyncio
async def test_bulbul_passes_romanized_canonical_text_through():
    # Bulbul accepts code-mixed romanized text natively — no script change at
    # this boundary (§2.2: script normalization only where the provider requires it).
    tts = _FakeTextToSpeech()
    bulbul = SarvamBulbulTTS(client=_fake_tts_client(tts))

    _ = [c async for c in bulbul.synthesize("kaise ho aap", prosody=None)]

    assert tts.calls[0]["text"] == "kaise ho aap"


@pytest.mark.asyncio
async def test_bulbul_degrades_to_empty_stream_on_error():
    bulbul = SarvamBulbulTTS(client=_fake_tts_client(_FailingTextToSpeech()))

    audio = [c async for c in bulbul.synthesize("kaise ho")]

    assert audio == []


# ---------------------------------------------------------------------------
# rumik_tts.py — Mulberry/Muga, description-driven (§7.7), Devanagari (§2.2)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, chunks=(), status=200):
        self._chunks = chunks
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeTransport:
    def __init__(self, response=None):
        self._response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._response is None:
            raise RuntimeError("network down")
        return self._response


def _rumik(transport, prosody_kwargs=None, **kwargs):
    return RumikMulberryTTS(
        api_key="rumik-key",
        base_url="https://fake.rumik.ai",
        transport=transport,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_rumik_mulberry_normalizes_hindi_and_merges_description():
    transport = _FakeTransport(_FakeResponse(chunks=[b"a", b"b"]))
    tts = _rumik(transport)

    audio = [c async for c in tts.synthesize("kaise ho aap", prosody={"description": "slow, warm"})]

    assert audio == [b"a", b"b"]
    url, kwargs = transport.calls[0]
    payload = kwargs["json"]
    assert url == "https://fake.rumik.ai/v1/text-to-speech"
    assert payload["text"] == "कैसे हो आप"  # §2.2: Devanagari at the Mulberry boundary
    assert payload["description"] == "slow, warm"  # §7.7: prosody directive merged in
    assert payload["model"] == "mulberry"
    assert kwargs["headers"]["Authorization"] == "Bearer rumik-key"


@pytest.mark.asyncio
async def test_rumik_keeps_english_latin():
    transport = _FakeTransport(_FakeResponse())
    tts = _rumik(transport)

    _ = [c async for c in tts.synthesize("How are you feeling today")]

    assert transport.calls[0][1]["json"]["text"] == "How are you feeling today"


@pytest.mark.asyncio
async def test_rumik_defaults_description_when_no_prosody():
    transport = _FakeTransport(_FakeResponse())
    tts = _rumik(transport)

    _ = [c async for c in tts.synthesize("kaise ho")]

    assert (
        transport.calls[0][1]["json"]["description"] == "warm, natural, empathetic therapist voice"
    )


@pytest.mark.asyncio
async def test_rumik_degrades_to_empty_stream_on_error():
    tts = _rumik(_FakeTransport(response=None))

    audio = [c async for c in tts.synthesize("kaise ho")]

    assert audio == []


@pytest.mark.asyncio
async def test_rumik_muga_is_a_silent_alias_with_different_model():
    transport = _FakeTransport(_FakeResponse())
    tts = RumikMugaTTS(
        api_key="rumik-key",
        base_url="https://fake.rumik.ai",
        transport=transport,
    )

    _ = [c async for c in tts.synthesize("kaise ho")]

    assert transport.calls[0][1]["json"]["model"] == "muga"


# ---------------------------------------------------------------------------
# factory.py — provider selection by config (§7.11), never a hardcoded default
# ---------------------------------------------------------------------------


def test_factory_stt_returns_sarvam_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "sarvam")
    monkeypatch.setattr(settings, "sarvam_api_key", "sk-test")

    assert isinstance(get_stt_provider(), SarvamSTT)


@pytest.mark.asyncio
async def test_factory_tts_returns_bulbul_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "sarvam")
    monkeypatch.setattr(settings, "sarvam_api_key", "sk-test")

    assert isinstance(get_tts_provider(), SarvamBulbulTTS)


@pytest.mark.asyncio
async def test_factory_tts_returns_mulberry_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "rumik")
    monkeypatch.setattr(settings, "rumik_api_key", "rumik-test")

    provider = get_tts_provider()
    try:
        assert isinstance(provider, RumikMulberryTTS)
    finally:
        await provider.aclose()


def test_factory_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "nope")
    with pytest.raises(ValueError, match="nope"):
        get_stt_provider()

    monkeypatch.setattr(settings, "tts_provider", "also-nope")
    with pytest.raises(ValueError, match="also-nope"):
        get_tts_provider()
