"""Pipecat voice-loop assembly (F011) — impl §7.7.

The graph is turn-scoped; the voice layer holds the conversation loop:
mic → streaming STT · VAD/endpointing · TTS playback · barge-in cancel.

Pieces wired here (all per §7.7 / §8.2):

* ``FastAPIWebsocketTransport`` — the `/ws` voice endpoint transport.
* ``SileroVADAnalyzer`` — endpointing. The phase-dependent turn-end threshold
  is applied via ``VADParamsUpdateFrame`` when the session phase changes.
* ``SarvamSTTService`` — streaming STT, `mode="translit"` (romanized output,
  the §2.2 canonical form).
* ``SarvamTTSService`` — streaming TTS (Bulbul).
* ``TurnGraphProcessor`` — the bridge: STT transcript in → turn-graph
  invocation (F010) → response text → TTS. Owns barge-in capture (F013) and
  the 90-second silence check-in.

Live-audio verification (endpointing behaviour, barge-in, TTS prosody) is a
`make dev` + browser-mic exercise — this module only assembles.
"""

from collections.abc import Awaitable, Callable

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    EndFrame,
    StartFrame,
    TextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADParamsUpdateFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.utils.asyncio.task_manager import TaskManager

from app.config.settings import settings
from app.graph.state import SessionState, new_session_state
from app.logger import logger
from app.voice.interruptions import append_interruption, capture_interruption, truncated_ai_text
from app.voice.serialization import BrowserFrameSerializer
from app.voice.timers import vad_threshold_for_phase

# Graph invoker: (thread_id, state) -> updated state. The server (F015) injects
# a real one owning the checkpointer context; the default echoes for standalone.
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


def build_transport(websocket) -> FastAPIWebsocketTransport:
    """The `/ws` Pipecat websocket transport (input+output).

    ``serializer=BrowserFrameSerializer()`` — the transport ignores every
    message without a serializer, and Pipecat ships only telephony ones. This
    is what lets the control-surface browser talk to the pipeline.
    """
    params = FastAPIWebsocketParams(
        audio_in_sample_rate=16000,
        audio_out_sample_rate=24000,
        vad_enabled=True,
        vad_analyzer=SileroVADAnalyzer(
            sample_rate=16000,
            params=VADParams(stop_secs=vad_threshold_for_phase("landing")),
        ),
        serializer=BrowserFrameSerializer(),
    )
    return FastAPIWebsocketTransport(websocket, params=params)


def build_stt() -> SarvamSTTService:
    """Streaming STT (Saaras) — translit mode = romanized canonical output."""
    return SarvamSTTService(api_key=settings.sarvam_api_key, mode="translit")


def build_tts() -> SarvamTTSService:
    """Streaming TTS (Bulbul). Prosody is a fixed warm directive in v0; live
    phase→prosody application (§7.7) is a voice-eval tuning exercise."""
    return SarvamTTSService(api_key=settings.sarvam_api_key)


class TurnGraphProcessor(FrameProcessor):
    """Bridge STT transcript → turn graph (F010) → response text → TTS.

    Also owns the voice-side timers (§7.7): phase-dependent VAD threshold
    updates and the 90-second silence check-in, plus barge-in capture into the
    next turn's `interruption_events` (F013).
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
        self._phase = "landing"

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        # super() handles StartFrame (and pushes it downstream) and system
        # frames — nothing more to do for those.
        if isinstance(frame, StartFrame):
            return

        # Session close → fire the post-session course graph (§7.4) async.
        if isinstance(frame, EndFrame):
            await self.push_frame(frame)
            if self._on_close is not None:
                await self._on_close(self._state, list(self._transcript))
            return

        # Barge-in: patient spoke during TTS playback — capture it (F013).
        if isinstance(frame, UserStartedSpeakingFrame):
            truncated = truncated_ai_text(self._state.get("response", ""), "")
            event = capture_interruption(
                interrupted_what=truncated or "previous response",
                phase=self._phase,
                when_min=self._state.get("elapsed_minutes", 0.0),
            )
            self._state = {**self._state, **append_interruption(self._state, event)}
            await self.push_frame(frame)
            return

        if isinstance(frame, UserStoppedSpeakingFrame):
            await self.push_frame(frame)
            return

        # Final STT transcript → one turn-graph invocation → response → TTS.
        if isinstance(frame, TextFrame) and getattr(frame, "text", ""):
            self._transcript.append(frame.text)
            self._state, response, phase = await run_turn(
                {**self._state, "patient_utterance": frame.text}, self._invoker, self._thread_id
            )
            # Phase change → update the turn-end VAD threshold (§7.7).
            if phase != self._phase:
                self._phase = phase
                await self.push_frame(
                    VADParamsUpdateFrame(params=VADParams(stop_secs=vad_threshold_for_phase(phase)))
                )
            if response:
                await self.push_frame(TextFrame(response))

        await self.push_frame(frame)


def build_pipeline(
    websocket,
    invoker: GraphInvoker,
    thread_id: str,
    on_close: Callable[[SessionState, list[str]], Awaitable[None]] | None = None,
) -> Callable[[], Awaitable[None]]:
    """Assemble the §7.7 voice pipeline for one websocket connection.

    Returns an async ``run()`` callable. Pipecat ≥1.7 removed `Pipeline.run`;
    the worker is built lazily inside ``run()`` so its `TaskManager` binds to
    the running event loop. The transport's `on_client_disconnected` handler
    cancels the worker so ``run()`` returns when the browser disconnects.
    """
    transport = build_transport(websocket)
    pipeline = Pipeline(
        [
            transport.input(),
            build_stt(),
            TurnGraphProcessor(invoker, thread_id, on_close=on_close),
            build_tts(),
            transport.output(),
        ]
    )

    async def run() -> None:
        worker = PipelineWorker(pipeline, task_manager=TaskManager())

        @transport.event_handler("on_client_disconnected")
        async def _on_disconnected(transport, client) -> None:
            logger.info("voice client disconnected; cancelling pipeline")
            await worker.cancel()

        await worker.run(params=PipelineParams())

    return run
