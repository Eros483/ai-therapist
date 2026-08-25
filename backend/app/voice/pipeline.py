"""Pipecat voice pipeline (F011) — SmallWebRTC transport per the Pipecat docs.

Browsers connect over WebRTC (serverless SmallWebRTC), NOT WebSocket — the
docs are explicit: FastAPIWebsocketTransport is for telephony, and browser
audio over WebSocket is the wrong path (TCP head-of-line blocking, no built-in
AEC, no RTP timing). This module follows the canonical p2p-webrtc example:

    SmallWebRTCTransport.input()
      → VADProcessor (Silero)            [emits VADUserStarted/StoppedSpeakingFrame]
      → SarvamSTTService                 [VAD-stop → flush → TranscriptionFrame]
      → TurnGraphProcessor               [turn-graph (F010) → response TextFrame]
      → SarvamTTSService                 [TextFrame → AudioRawFrame]
      → SmallWebRTCTransport.output()

VAD is NOT configured on the transport params (TransportParams has no VAD
fields — passing them is silently dropped); it lives in a VADProcessor, which
passes audio through and broadcasts VAD frames that the STT consumes.

`run_bot(webrtc_connection, ...)` is the per-connection entry, wired by the
server's `/api/offer` signaling handler.
"""

from collections.abc import Awaitable, Callable

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    ClientConnectedFrame,
    EndFrame,
    StartFrame,
    TextFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from app.config.settings import settings
from app.graph.state import SessionState, new_session_state
from app.logger import logger
from app.voice.interruptions import append_interruption, capture_interruption, truncated_ai_text
from app.voice.timers import vad_threshold_for_phase

# Graph invoker: (thread_id, state) -> updated state. The server (F015) injects
# a real one owning the checkpointer context.
GraphInvoker = Callable[[str, SessionState], Awaitable[SessionState]]


async def run_turn(
    state: SessionState, invoker: GraphInvoker, thread_id: str
) -> tuple[SessionState, str, str]:
    """One graph turn: transcript in state → updated state + response + phase.

    Pure except for the injected invoker; the processor and the server both use
    this, and it's the unit-testable heart of the bridge.
    """
    result = await invoker(thread_id, state)
    updated = {**state, **result}
    response = updated.get("response") or ""
    phase = updated.get("phase", "landing")
    return updated, response, phase


def build_webrtc_transport(connection: SmallWebRTCConnection) -> SmallWebRTCTransport:
    """Serverless peer-to-peer WebRTC transport for one browser connection."""
    return SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )


def build_vad() -> VADProcessor:
    """Silero VAD — the turn-end threshold is phase-dependent (§7.7)."""
    return VADProcessor(
        vad_analyzer=SileroVADAnalyzer(
            sample_rate=16000,
            params=VADParams(stop_secs=vad_threshold_for_phase("landing")),
        )
    )


def build_stt() -> SarvamSTTService:
    """Streaming STT (Saaras) — translit mode = romanized canonical output (§2.2)."""
    return SarvamSTTService(
        api_key=settings.sarvam_api_key,
        mode="translit",
        sample_rate=16000,
    )


def build_tts() -> SarvamTTSService:
    """Streaming TTS (Bulbul)."""
    return SarvamTTSService(api_key=settings.sarvam_api_key)


class TurnGraphProcessor(FrameProcessor):
    """Bridge STT transcript → turn graph (F010) → response text → TTS.

    Owns the voice-side timers (§7.7) and barge-in capture into the next turn's
    `interruption_events` (F013). Greets the patient once the client connects
    (the Landing phase opens the session).
    """

    def __init__(
        self,
        invoker: GraphInvoker,
        thread_id: str,
        on_close: Callable[[SessionState, list[str]], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self._invoker = invoker
        self._thread_id = thread_id
        self._on_close = on_close
        self._state: SessionState = new_session_state()
        self._transcript: list[str] = []
        self._greeted = False

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame)
            return

        # Client connected → open the session (Landing greeting).
        if isinstance(frame, ClientConnectedFrame):
            await self.push_frame(frame)
            if not self._greeted:
                self._greeted = True
                self._state, response, _phase = await run_turn(
                    {**self._state, "patient_utterance": ""}, self._invoker, self._thread_id
                )
                if response:
                    await self.push_frame(TextFrame(response))
            return

        # Session close → fire the post-session course graph (§7.4).
        if isinstance(frame, EndFrame):
            await self.push_frame(frame)
            if self._on_close is not None:
                await self._on_close(self._state, list(self._transcript))
            return

        # Barge-in: patient spoke during TTS playback — capture it (F013).
        if isinstance(frame, (UserStartedSpeakingFrame, VADUserStartedSpeakingFrame)):
            truncated = truncated_ai_text(self._state.get("response", ""), "")
            event = capture_interruption(
                interrupted_what=truncated or "previous response",
                phase=self._state.get("phase", "landing"),
                when_min=self._state.get("elapsed_minutes", 0.0),
            )
            self._state = {**self._state, **append_interruption(self._state, event)}
            await self.push_frame(frame)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            await self.push_frame(frame)
            return

        # Final STT transcript → one turn-graph invocation → response → TTS.
        if isinstance(frame, TextFrame) and getattr(frame, "text", ""):
            self._transcript.append(frame.text)
            logger.info("STT transcript: %r", frame.text)
            self._state, response, _phase = await run_turn(
                {**self._state, "patient_utterance": frame.text}, self._invoker, self._thread_id
            )
            if response:
                await self.push_frame(TextFrame(response))

        await self.push_frame(frame)


async def run_bot(
    webrtc_connection: SmallWebRTCConnection,
    invoker: GraphInvoker,
    thread_id: str,
    on_close: Callable[[SessionState, list[str]], Awaitable[None]] | None = None,
) -> None:
    """Run one voice session on a SmallWebRTC connection (canonical p2p pattern)."""
    transport = build_webrtc_transport(webrtc_connection)
    pipeline = Pipeline(
        [
            transport.input(),
            build_vad(),
            build_stt(),
            TurnGraphProcessor(invoker, thread_id, on_close=on_close),
            build_tts(),
            transport.output(),
        ]
    )
    worker = PipelineWorker(pipeline, params=PipelineParams())

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport, client) -> None:
        logger.info("voice client disconnected; cancelling pipeline")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
