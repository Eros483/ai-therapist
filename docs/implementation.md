# AI Therapy System — Implementation Specification

> Status: v2.1 — adds Course Arc mechanics (§4) and the LangGraph runtime build spec (§7)
> Companion document: **methodology.md** — every mechanism in this spec exists because the methodology demands it. Section rationales below cite it.
> Research grounding: §9; full paper notes in `docs/research.md`.
>
> **Research context:** This is a **research prototype**, not a shipped product. Providers, schemas, and thresholds below are defaults chosen for study, not production hardening. Anything marked *eval-time* is decided by measurement, never by default.

---

## 1. System Overview

The system is **model-agnostic**: no component may hard-depend on a specific LLM, STT, or TTS provider. Every model-facing choice is expressed as capability requirements and every provider is swappable (via LiteLLM — §7.1).

Voice-only conversation; there is no text mode. Minimal visual surface: crisis resources + session controls + memory controls. Voice is the only conversational input.

*(Because: methodology.md §1 — voice-first, native-language; and §7 — the visual surface exists for crisis resources, not conversation.)*

### 1.1 Runtime Topology

Two LangGraph graphs and one voice loop:

```
┌────────────────────────── per patient turn ──────────────────────────┐
│  TURN GRAPH (LangGraph, one invocation per exchange — §7.3)          │
│  safety gate → parallel small-model calls → phase agent → stream out │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ token stream
┌──────────────────────────────▼───────────────────────────────────────┐
│  VOICE LOOP (Pipecat, stream-scoped — §7.7)                          │
│  mic → STT stream · VAD/endpointing · TTS playback · barge-in cancel │
└───────────────────────────────────────────────────────────────────────┘

┌────────────────────── after session close (async) ───────────────────┐
│  COURSE GRAPH (LangGraph — §7.4)                                     │
│  synthesis node → course planner node → course store                 │
└───────────────────────────────────────────────────────────────────────┘
```

- **No serial critic/self-refinement loop before response.** coTherapist (Adhikary et al., WWW 2026) runs Reasoner → Critic → Refine before every answer — sound for a text interface, unusable for live voice: each refinement iteration is seconds of dead air on a call, which is itself a container violation (methodology.md §6.4). Safety screening stays (the safety gate is a parallel classifier, not a serial loop — §7.8); quality self-critique moves to offline evaluation and the parked eval set (methodology.md §8).
- Latency budget: deferred — measured per candidate at model-selection time (§8.1). The one accepted serial cost (state extraction → phase agent, §7.5) is noted there.

---

## 2. Language Pipeline

*(Because: methodology.md §3 — the mirroring rules, register-as-signal, and natural Hinglish rhythm.)*

### 2.1 Register Classifier (runs in parallel with main model)

```
Input: STT transcript + audio features
       (code-switching is audible — accent shift, pronunciation,
        prosody change. The classifier should consume both,
        not just the transcript text.)
Output: register score on a 3-point scale
 - 0 = formal English
 - 1 = Hinglish
 - 2 = Hindi / mother tongue
 Plus: a continuous code-mixing score per utterance. The
 Code-Mixing Index (CMI = 1 − max(n_hi, n_en) / n) from Sengupta
 et al. (HSSC 2024) is a ready-made graded signal — a hard 3-point
 label loses the difference between "mostly English with one Hindi
 word" and "balanced Hinglish." Their code-mixed threshold is
 CMI ≥ 0.5.

Implementation options:
 - Fine-tuned classifier on Indian English/Hinglish corpus
 - Prompt-based classification using a lightweight model   ← v0
 - Rule-based heuristics (particle detection) as fallback
```

### 2.2 Transcript Normalization (two-form rule)

Romanized Hindi is the **canonical form for everything upstream of TTS**: STT transcript → register classifier → session state → LLM context. No Devanagari/romanized drift across that stretch. This is either requested from the STT provider as a transliteration output mode, or applied as a post-processing step.

TTS input script is **provider-specific** — e.g. Rumik Mulberry expects Hindi in Devanagari and English in Latin. The pipeline therefore includes a **script-normalization step at the TTS boundary** (romanized → provider's required script), verified per provider during the voice eval (§8.3).

**Empirical validation of the two-form rule:** Sengupta et al. (HSSC 2024) found that switched words are majorly written in romanized script — users code-mix far more than they script-switch. Romanized as the upstream canonical form matches observed user behavior, not just pipeline convenience. PARADOX (Sengupta, Akhtar & Chakraborty, TMLR 2024) further shows code-mixing preference is conditioned on socioeconomic status, demographics, and local context — its CM metrics (CM BLEU, CM Rouge, CM KS) are the seed for the Hinglish register regression set in the parked eval (methodology.md §8).

### 2.3 Response Mode System

The system prompt carries three response mode variants:
- `mode: formal-en` — standard English, no code-switching
- `mode: hinglish` — English grammar, Hindi particles allowed, `yaar`/`na`/`matlab` natural
- `mode: hindi-led` — higher proportion of Hindi, emotionally close register

Mode transitions are triggered by register classifier output, with a one-exchange lag *(because: methodology.md §3.2 rule 1 — follow, never lead)*.

### 2.4 Session Topic-Language Map (per session memory)

```json
{
 "topic_language_map": {
   "work": "hinglish",
   "family": "hindi",
   "self_worth": "hindi",
   "logistics": "formal-en"
 }
}
```

This map is updated continuously and surfaced to the model as context *(because: methodology.md §3.2 rule 3 — track which topics trigger which language)*.

---

## 3. Session Arc Mechanics

*(Because: methodology.md §4 — the five-phase arc inside a fixed time container, delayed-never-rushed.)*

### 3.1 Phase Transition Logic

```python
def get_current_phase(elapsed_minutes, total_minutes=45):
   frac = elapsed_minutes / total_minutes
   if frac <= 0.10:  return "landing"
   if frac <= 0.30:  return "opening"
   if frac <= 0.65:  return "deepening"
   if frac <= 0.85:  return "meaning"
   return "closing"
```

### 3.2 Phase Delay

Phase can be delayed (e.g. stay in Opening if `session.primary_thread` is still null — see §5.1) but never rushed forward. Delay is a rule checked before each transition, not a model decision.

### 3.3 Boundary Event Mechanics

Each row of methodology.md §4.5 maps to a voice-loop event handler (§7.7): early-end (compressed close), ~90s silence (single soft check-in timer), acute disclosure (safety override of the time container), hang-up (session close + unresolved-thread marking in the course store, no outbound contact).

---

## 4. Course Arc Mechanics

*(Because: methodology.md §5 — the 8-session course, milestone transitions, next-session intention, termination.)*

### 4.1 Course State

```json
{
 "course": {
   "session_number": 5,
   "course_phase": "exploration",
   "session_summaries": [
     {
       "n": 1,
       "distillation": "surface: work stress; underneath: feeling unseen by father",
       "carry_forward": "notice when 'small' shows up at work",
       "outcome": "partially-addressed"
     }
   ],
   "formulation": {
     "presenting_threads": ["work stress", "relationship with father"],
     "working_pattern": null,
     "confirmed_insights": []
   },
   "next_session_intention": "open with carry-forward from session 5 (the 'small' noticing)",
   "unresolved_threads": ["sister's wedding"]
 }
}
```

Field notes:

- `formulation.working_pattern` is set when a pattern recurs across ≥2 sessions (the Exploration→Working milestone).
- `formulation.confirmed_insights` holds **the patient's own words** at the moment of confirmation — the Termination session quotes them verbatim (methodology.md §5.4).
- `next_session_intention` becomes the Landing content of session N+1; it seeds the Landing, it does not replace it.

### 4.2 Post-Session Graph

Runs once, async, after session close (see §7.4) — zero turn latency:

1. **Synthesis node** — transcript + final session state → per-session summary (distillation + carry-forward + outcome), extracted against the ConSum/MentalCLOUDS counseling-components schema (methodology.md §6.7)
2. **Course planner node** — session summary + prior course state → updated `formulation`, milestone evaluation (§4.3), `next_session_intention`, course store write

### 4.3 Milestone Predicates (code-checkable)

```python
def evaluate_course_phase(course: CourseState) -> str:
    if course.session_number <= 2:
        return "foundation"
    if course.session_number >= 8:
        return "termination"
    if confirmed_insight_exists(course):          # patient-confirmed, verbatim
        return "working→termination"              # edge fires; session 8 regardless
    if pattern_recurs_across_sessions(course, min_sessions=2):
        return "working"
    return "exploration"
```

Delayed-never-rushed, but calendar-bounded: session 8 is Termination regardless of milestone state; unmet milestones are named honestly in the course review (methodology.md §5.3).

### 4.4 Course Boundary Events

Dropped course → no outbound contact (privacy rule); re-entry protocol on return (acknowledge gap, mini-Landing, resume from course store). Crisis mid-course → course state records the interruption; next session opens from where the crisis left the patient. (methodology.md §5.6)

---

## 5. State & Memory

*(Because: methodology.md §4.2 state-tracking requirements, §6.7 distillation schema, §6.8 interruption context, §8 research questions on continuity.)*

### 5.1 Within-Session State

Track the following state throughout each session:

```json
{
 "session": {
   "phase": "deepening",
   "elapsed_minutes": 22,
   "exchange_count": 14,
   "baseline_affect": "tense",
   "primary_thread": "relationship with father",
   "dropped_threads": ["sister's wedding", "job offer"],
   "key_words_used": ["small", "invisible", "not enough"],
   "language_map": {
     "family": "hindi",
     "work": "hinglish"
   },
   "body_locations_mentioned": ["chest", "throat"],
   "tentative_pattern": "feeling unseen by authority figures",
   "interruption_events": [
     {"interrupted_what": "body question", "phase": "deepening", "when_min": 21}
   ],
   "audio_affect": {
     "arousal_trajectory": "rising-then-flattening",
     "flat_prosody_streak": false
   }
 }
}
```

**Field notes:**

- `baseline_affect` is **measured from audio** (pace, volume, pitch, flatness at session open) — not guessed by the LLM from the transcript.
- `interruption_events` (methodology.md §6.8) is surfaced to the model in the session-state block every turn — the model always knows whether its last utterance was cut off, and what it was saying.
- `audio_affect` tracks arousal across the session; a sustained flat-prosody streak is a dissociation signal and can contribute to crisis detection (methodology.md §7.3).

### 5.2 State Ownership

The session state JSON is updated by a **separate lightweight extraction call after each exchange** — not self-reported by the main therapist model. This keeps the therapist model in character, and makes session state deterministic and auditable (a bug in state-tracking is a pipeline bug, not a hallucination). PIECE (Srivastava et al., EMNLP 2024) provides the precedent: experts plan knowledge application before writing, and a planning engine improved counseling summarization across three different base LLMs.

### 5.3 Next-Technique Recommendation

The same extraction call emits a recommended next technique (response-act) — e.g. `next_technique: "body question"` — which rides in the prompt's technique-library slot (§6.1). Grounded in READER (Srivastava et al., WWW 2023): jointly predicting the next response-act before generating the response improved counseling dialogue quality on the HOPE benchmark. It is also the direct counter to the "rarely initiate strategies themselves" failure mode measured by Baldo et al. (arXiv:2608.21325) — see methodology.md §6.10.

### 5.4 Cross-Session Memory

The course store (§4.1) holds the cross-session memory: recurring themes and patterns, key relationships, language/register patterns, unresolved threads (including hang-up-marked), interruption history, observed changes over time.

**Schema seed (research-grounded):** structured around the counseling components validated in ConSum (Srivastava et al., KDD 2022) and MentalCLOUDS (Adhikary et al., JMIR Mental Health 2024) — recurring symptoms, history of mental-health issues, discovered behavior patterns — plus this design's additions: register patterns (topic-language map), interruption history, unresolved threads.

### 5.5 Persistence & Privacy

- **PostgreSQL from day one**: LangGraph `PostgresSaver` checkpointer per session; course store tables via SQLAlchemy 2.0 (async)
- Session content encrypted at rest (Fernet, app-layer) — key management is a deployment concern, documented at build time
- Participant can delete session history at any time (cascades: checkpointer thread + course store rows)
- No session content used for model training without explicit opt-in
- **If this ever becomes a deployed product:** compliance target is India's Digital Personal Data Protection (DPDP) Act, 2023 — see Sethi et al. (*The Digital Personal Data Protection Act 2023: Implications for Mental Healthcare Practice in India*, Indian Journal of Psychological Medicine, 2025). For the research phase, participant data handling runs under research-ethics consent; the consent capture (methodology.md §7.5), minimal-payload crisis notification (§7.3), and deletion rights above carry over unchanged.

---

## 6. System Prompt Architecture

*(Because: methodology.md §6 — the techniques must be callable structure, not prose; §7 — safety rules ride with every turn.)*

### 6.1 Structure — Per-Phase Prompts

Instead of one monolithic system prompt, each phase agent (§7.3) carries **its own scoped prompt**: persona core + that phase's instruction block + that phase's technique subset. Instruction-following improves when the Deepening agent is not carrying Closing's rules; and each agent's technique subset is small enough to be a genuine callable set rather than a wall of prose.

Common blocks (all five agents):

```
[PERSONA]
Who the AI is, its tone, its relationship to the patient.

[LANGUAGE MODE]
Current register (formal-en / hinglish / hindi-led), mirroring rules.

[SESSION STATE]
JSON blob: phase, elapsed time, primary thread, dropped threads,
key words, topic-language map, interruption events, and — from
session 2 — the course context (next_session_intention for Landing,
formulation for later phases).

[SAFETY RULES]
Crisis protocol is pipeline-level (§7.8); the prompt carries only
what the model must know: acknowledge-with-warmth, stop exploring,
stay present.
```

Per-phase blocks (each agent adds its own):

```
[PHASE INSTRUCTION]       — this phase's behaviours, caps, prohibitions
[TECHNIQUE LIBRARY]       — this phase's technique subset as a discrete,
                            named, selectable set + the recommended next
                            technique from the state-extraction call (§5.3)
[CLOSING RULES]           — closing agent only; injected when Closing begins
```

Structured as a callable set, not prose: Baldo et al. (arXiv:2608.21325) showed exposing a validated move ontology as tools roughly halves deviation from human therapist behavior.

### 6.2 Key Directives (carried by all phase agents)

```
- Hold silence rather than filling it. When the patient trails off or says
  "I don't know," wait. A 3-word spoken response after a held pause is
  sometimes the right response.
- If you were interrupted, yield. Do not restart or finish the interrupted
  sentence. Check the interruption history in session state: repeated
  interruptions of your reflections mean slow down and shorten.
- Never parrot back the patient's exact words. Reframe slightly.
- If the patient mentions something and pivots away, address the
  thing they moved past first.
- Do not give advice before the Meaning phase.
- Use the patient's own words as bridges to deeper questions.
- Do not open new emotional threads once Closing begins.
```

---

## 7. Runtime Architecture — LangGraph Build Spec

*(Because: methodology.md §6.10 — five-phase decomposition with phase-scoped technique tools; §6.4 silence; §6.8 barge-in; §7.3 safety gating.)*

### 7.1 Stack

| Concern | Choice | Why |
|---|---|---|
| Orchestration | `langgraph`, `langgraph-checkpoint-postgres` | Conditional edges = the phase state machine; per-node prompts (§6.1); checkpointer = session persistence |
| Voice loop | `pipecat` (websocket transport) + silero VAD | Endpointing control (methodology.md §6.4), cancelable TTS playback, Sarvam/Rumik integrations exist |
| LLM access | `litellm` | One interface over any provider; model swap = config string — model-agnosticism at the code level, not aspirationally |
| STT / TTS | `sarvamai` SDK, Rumik HTTP/WS client — behind protocols (§7.9) | Eval candidates (§8.3) |
| Storage | PostgreSQL + `sqlalchemy` 2.0 (async) + `psycopg` | Decided: Postgres from day one |
| Encryption | `cryptography` (Fernet) | App-layer encryption of session content at rest |
| Config | `pydantic-settings` | Every model, provider, threshold in env-swappable settings (§7.11) |
| Server | `fastapi` + `uvicorn` | Control-surface page + `/ws` voice endpoint |
| Tests | `pytest` | Graph nodes are pure functions of state — cheap to test |

LangGraph is orchestration, not a model — any LLM plugs into it via LiteLLM; model-agnosticism (§1) is preserved.

### 7.2 Process Model

One FastAPI process hosts everything: the static control-surface page, the Pipecat websocket endpoint (`/ws`), and turn-graph invocations. PostgreSQL runs alongside. No additional servers, no message broker. *(Research-prototype sizing; the topology splits cleanly later if ever needed.)*

### 7.3 Turn Graph (one invocation per patient exchange)

```
START
  → safety_L1_lexicon            [pure code, <1ms]
      ├─ hit ────────────────────→ crisis_node ──→ END
      └─ miss
         → parallel branch:
             safety_L2_small_model   (gate: phase agent waits on its verdict)
             register_classifier
             affect_from_audio
             state_extractor        (updates SessionState + next_technique)
         → [join: L2-safe ∧ extraction done]
         → phase_agent[session.phase]        [conditional edge — 5 nodes]
              landing / opening / deepening / meaning / closing
         → END (token stream → voice layer → TTS)
```

- **Five phase-agent nodes**, selected by conditional edge on `session.phase`. Each carries its scoped prompt (§6.1) and its phase's technique subset as callable tools — the realization of methodology.md §6.10.
- **Supporting nodes** (safety L1/L2, register, affect, extraction) are the "separate calls" the spec has always demanded — now explicit graph nodes with contracts (§7.5).
- **Crisis edge**: L1 hit routes immediately; L2 hit gates the join — phase agent never runs on a crisis utterance.
- Interruption events are *not* handled here — the voice layer owns cancellation; the captured event feeds the *next* invocation's state (§7.7).

### 7.4 Post-Session Graph (async, after close)

```
START → synthesis_node → course_planner_node → course_store → END
```

- **synthesis_node**: transcript + final SessionState → per-session summary (distillation, carry-forward, outcome) against the counseling-components schema (methodology.md §6.7)
- **course_planner_node**: summary + prior CourseState → formulation update, milestone evaluation (§4.3), `next_session_intention`
- Runs off the live path; latency irrelevant. Fired by the voice loop's session-close event (including hang-up close).

### 7.5 Node Contracts

| Node | Model class (via LiteLLM) | Input | Output |
|---|---|---|---|
| `safety_L1_lexicon` | none — code | utterance text | `{hit: bool, category}` |
| `safety_L2_small_model` | small | utterance (+ prior context) | strict JSON `{crisis: bool, category, confidence}` |
| `register_classifier` | small | transcript + audio features | `{register: 0–2, cmi: float}` |
| `affect_from_audio` | small / signal heuristics | audio stream stats | `{arousal_delta, flat_prosody_streak}` |
| `state_extractor` | small | transcript + prev SessionState | updated SessionState JSON + `next_technique` |
| `phase_agent` ×5 | **main model** | SessionState + course context + technique subset | spoken response (token stream) |
| `crisis_node` | main model, protocol-constrained | context | crisis protocol response (§7.8) |
| `synthesis_node` | main model | transcript + final SessionState | session summary (components schema) |
| `course_planner_node` | small | summaries + CourseState | formulation updates, milestone verdict, `next_session_intention` |

**Accepted serial cost:** extraction → phase agent is two sequential LLM calls per turn. The spec already demanded the separate extraction call (§5.2); mitigation is a small fast model for extraction, and a held pause before speaking is therapeutically correct anyway (methodology.md §6.4 gives cover). Measured at eval time like everything else.

### 7.6 State Schemas

`SessionState` (§5.1) and `CourseState` (§4.1) as LangGraph `TypedDict`s in `graph/state.py`; checkpointer keys: `thread_id = participant:{id}:session:{n}`, course store keyed by participant.

### 7.7 Voice Loop Integration (Pipecat)

Pipecat owns what LangGraph cannot: mic capture, streaming STT (Sarvam), VAD/endpointing, streaming TTS (Rumik/Sarvam) playback, interruption. The graph is turn-scoped; the voice layer holds the conversation loop.

**Two distinct timers — do not conflate:**

| Timer | Value | Job |
|---|---|---|
| Turn-end VAD threshold | seconds; **phase-dependent** (Deepening > Landing) | Decides *patient finished* vs *patient thinking* — methodology.md §6.4. The therapeutically load-bearing knob |
| 90-second silence check-in | 90s, fixed | One soft check-in utterance, never repeated (methodology.md §4.5) |

**Barge-in flow:** patient speech during TTS playback → cancel TTS stream instantly → capture truncated AI text → append `interruption_event` {what, phase, minute} → next turn-graph invocation's SessionState carries it (methodology.md §6.8).

**Prosody flow:** phase → directive map (Landing: warm/relaxed · Deepening: slower/lower/longer pauses · Closing: settled) merged into the TTS call — e.g. into Mulberry's `description` param, or Bulbul's parameters (§8.3).

**Script flow:** romanized canonical (§2.2) until the TTS boundary; normalization to provider script at the TTS call.

### 7.8 Safety Stack (3 layers)

*(Because: methodology.md §7.3 — detection outside the main model; recall-tuned.)*

| Layer | What | When |
|---|---|---|
| **L1 — lexicon** | High-precision regex/keyword triggers, English + romanized Hindi ("suicide", "khudkhushi", "jeena nahin", "khatam kar du", …). Zero latency, zero training. Catches blunt cases. | v0, day one |
| **L2 — zero-shot small model** | Strict-JSON classifier over every utterance via LiteLLM. Multilingual/Hinglish-capable, red-teamable on day one. Runs parallel with register/affect/extraction; gates the phase agent. | v0, day one |
| **L3 — fine-tuned classifier** | Trained on labeled Hinglish crisis utterances — built from our red-team probes + consented session data. | Deferred — a research deliverable, not a prerequisite |

**Tuning stance:** false positive = an interrupted session (annoying, erodes trust); false negative = a missed crisis (catastrophic). Tune L2 for **recall**; accept precision hits; the emergency-contact notification (methodology.md §7.3) is the backstop.

**Known limitation, logged honestly:** indirect euphemism ("mujhe thak gaya hoon" — fatigue or something darker) is ambiguous even for humans; L2 will miss some. The layer stack + backstop exist precisely because of this. **The dataset gap is the research opportunity:** there is no Hinglish crisis-utterance dataset; L3 plus the dataset itself is a publishable contribution. SAHAY (Singh, Sethi, Math & Chakraborty, IJCAI 2025 — *Multimodal, Privacy-Preserving AI for Suicide Risk Detection and Intervention in India*) is the direction-marker; currently title-depth in `docs/research.md`.

### 7.9 Provider Interfaces

`STTProvider` and `TTSProvider` protocols (async, streaming); concrete implementations: `sarvam_stt.py`, `rumik_tts.py`, `bulbul_tts.py`. Script normalization lives in the TTS implementations (§2.2). Provider selection is config (§7.11) — eval-time swappable.

### 7.10 Repository Layout

```
backend/
  app/
    config/              # pydantic-settings: models, providers, thresholds
    graph/
      state.py           # SessionState, CourseState TypedDicts
      nodes/
        safety.py        # L1 lexicon + L2 small-model gate
        register.py      # register + CMI
        affect.py        # audio affect
        extraction.py    # state extractor + next_technique
        phases/          # landing.py opening.py deepening.py meaning.py closing.py
        crisis.py        # crisis protocol node
        course/          # synthesis.py planner.py
      turn_graph.py      # per-turn graph assembly
      course_graph.py    # post-session graph assembly
    voice/
      pipeline.py        # Pipecat pipeline assembly
      services/          # sarvam_stt.py rumik_tts.py bulbul_tts.py
      interruptions.py   # barge-in capture → interruption_events
      timers.py          # turn-end VAD (phase-dependent) vs 90s check-in
    storage/
      db.py              # async engine, checkpointer setup
      crypto.py          # Fernet
      course_store.py    # CourseState persistence
    server/
      main.py            # FastAPI: static page, /ws endpoint
  tests/                 # nodes are pure functions of state — test them directly
```

### 7.11 Configuration

Every model name, provider, and threshold lives in `pydantic-settings` — never hardcoded: main model, extraction/safety/classifier small models, STT/TTS providers + keys, turn-end VAD thresholds per phase, 90s check-in, session length (45m), course length (8), crisis resource numbers. Eval-time swappable by env var.

---

## 8. Voice Interface & Stack Requirements

*(Because: methodology.md §6.4 silence, §6.8 barge-in, §7.1 persona rendering, §7.3 crisis surfacing — none of these are negotiable pipeline features.)*

### 8.1 LLM — Capability Requirements

- Strong instruction-following (the per-phase prompts carry phase rules, technique constraints, and safety overrides)
- High-quality Hinglish/Hindi code-switching — comprehension and generation
- Streaming-friendly (required for natural voice turn-taking)
- Latency is a selection-time criterion: measure end-to-end voice turn latency per candidate model before committing — including the §7.5 serial extraction hop; no fixed budget set at this stage
- Register classifier: lightweight model or rule-based (separate inference call — §7.3)

### 8.2 Voice Interface Requirements

- Voice-only conversation. There is no text mode.
- Real silence is a first-class technique — methodology.md §6.4
- **Cancelable TTS stream** — required for always-allowed barge-in (methodology.md §6.8): patient speech must instantly cancel TTS playback
- **Prosody directive map** — prosody decided by phase + technique state, applied at the TTS layer (deterministic, auditable, model-agnostic). Not per-token LLM markup:
  - Landing: warm, relaxed pace
  - Deepening: slower, lower energy, longer inter-sentence pauses
  - Closing: settled, grounded pace
- STT must handle Hinglish/code-mixed speech accurately — evaluate per candidate
- TTS must render Hinglish/Hindi code-switching naturally within a single utterance
- TTS must offer Indian English voices in both gender codings, with prosody control (persona requirement, methodology.md §7.1)
- Endpointing tolerance: the pipeline must not cut patient silences short (methodology.md §6.4)
- Minimal visual surface: crisis resources + session controls + memory controls. Voice is the only conversational input.

### 8.3 Voice Provider — Evaluation Candidates

Capability requirements (§8.2) are normative. These are named candidates for **measured evaluation at build time**, not commitments:

| Candidate | Layer | Relevant strengths |
|---|---|---|
| Sarvam (Saaras) | STT | 22 Indic languages; mid-sentence code-mixing; transliteration (romanized) output mode — matches §2.2 normalization; telephony-grade audio handling; streaming, <250ms median |
| Sarvam (Bulbul) | TTS | 11 Indic languages; multiple Indian voices in both gender codings |
| Rumik Silk — Mulberry | TTS | Description-driven (`description` param required per call — the phase prosody directive map merges directly into it, §7.7); 12 named speakers (8 female, 4 male — maps onto the onboarding voice pick); WebSocket streaming for low-latency agents; ~$0.0046/min, MOS competitive with ElevenLabs/Google. Expects Hindi in Devanagari, English in Latin — drives the TTS-boundary script normalization (§2.2) |
| Rumik Silk — Muga | TTS | More expressive sibling; tone tags + inline events (`<laugh>` etc.) — evaluate if Mulberry's expressiveness falls short in Deepening |
| One global provider | STT/TTS | Control baseline for the eval |

Selection is by measured eval against the capability requirements (code-mixing accuracy, romanization, latency, prosody control, cancelable streaming) — never by default.

---

## 9. Research Grounding — Implementation

Full notes with depth labels: `docs/research.md`. Methodology-side grounding lives in methodology.md §9.

| Implementation decision | Grounding |
|---|---|
| Romanized canonical form (§2.2 two-form rule) | Sengupta et al., *HSSC* 2024 — switched words are majorly romanized; users code-mix more than they script-switch |
| CMI continuous register signal (§2.1) | Sengupta et al., *HSSC* 2024 — Code-Mixing Index |
| Next-technique prediction (§5.3) | Srivastava et al., WWW 2023 (READER — response-act prediction before generation); Malhotra et al., WSDM 2022 (HOPE — 12 counseling dialogue acts) |
| Separate state-extraction node (§5.2, §7.3) | Srivastava et al., EMNLP 2024 (PIECE — plan-before-summarize generalized across three base LLMs) |
| Course synthesis + memory schema (§4.2, §5.4) | Srivastava et al., KDD 2022 (ConSum); Adhikary et al., JMIR Mental Health 2024 (MentalCLOUDS) |
| Five phase agents, scoped prompts, technique subsets as tools (§6.1, §7.3) | Baldo et al., arXiv:2608.21325 — ontology-as-tools "roughly halves the mean deviation from the human move distribution"; per-phase scoping counters the context-anchored/never-initiates failure mode |
| No serial critic loop in the voice pipeline (§1.1) | Rejection of coTherapist's Reasoner → Critic → Refine loop (Adhikary et al., WWW 2026) on voice-latency grounds |
| System prompt as policy artifact (§6) | Kadous et al., arXiv:2608.20390 (Ansari — deployed values-sensitive companion, 140K conversations): "grounding is necessary but not sufficient"; their system prompt is "a theological as much as a technical artifact" — in our domain, read: a clinical-ethics artifact |
| Safety stack L1/L2/L3, recall-tuned (§7.8) | coTherapist keeps crisis decisions outside the main model (Adhikary et al., WWW 2026); L3 direction marked by SAHAY (Singh et al., IJCAI 2025) |
| DPDP Act compliance, if deployed (§5.5) | Sethi et al., *Indian J. Psychological Medicine* 2025 |
| Synthetic-session fixtures for eval | Mandal et al., EMNLP 2026 (MAGneT — public data; +4.3% CBT skills, 9-dim expert eval); Mandal et al., EMNLP 2026 (Graph2Counsel — Client Psychological Graphs, public data) |

---

*End of implementation spec — v2.1. Companion: methodology.md.*
