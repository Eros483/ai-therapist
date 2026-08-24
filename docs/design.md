# AI Therapy System — Product & Software Specification

> Compiled from design ideation session 
> Status: Draft v1.3 — voice-primary, model-agnostic

---

## 1. Product Vision

An AI-powered therapy companion that authentically simulates the therapeutic experience — not a chatbot that asks "how are you feeling?", but a system that replicates the *structure*, *pacing*, *techniques*, and *cultural texture* of how a real therapist builds rapport, opens a person up, and helps them find their own insight.

Primary market: Urban Indian users who code-switch between English, Hinglish, and Hindi — and where that language drift is a signal, not just a stylistic preference.

The product is a **voice-first spoken experience**. All conversation happens by voice; the visual surface (if any) is controls-only — crisis resources, session controls, memory controls. There is no text-conversation mode.

---

## 2. Five Core Design Dimensions

### 2.1 Language Adaptation
### 2.2 Session Arc
### 2.3 Therapist Micro-Techniques
### 2.4 Emotional Safety
### 2.5 Memory & Continuity

Each dimension is specified in detail below.

---

## 3. Language Adaptation

**Scope:** This spec is written for the Hindi/Hinglish/English code-switching pair. Other pairs (Tamil↔English, Bengali↔English, Marathi↔English) are **deliberately deferred** — we decide when an actual non-Hindi user shows up, not before. The architecture (register scale, topic-language map, mirroring rules) is built to generalize to any language pair; no generalization work happens until that trigger fires.

### 3.1 Core Insight

Language switching in the Indian urban context is an emotional thermometer, not random variation:

| Register | What it signals |
|---|---|
| Formal English | Self-presentation, performance, control |
| Hinglish | Guard coming down, comfort increasing |
| Pure Hindi / mother tongue | Raw emotion — grief, family, childhood |

The AI must treat every language switch as a **signal**, not just stylistic noise.

### 3.2 The Three Mirroring Rules

1. **Follow, never lead.** If the patient is still in formal English, the AI must not inject Hinglish to seem relatable. Mirror the patient's register with a one-exchange lag — they lead, the AI follows.
2. **Never switch back without cause.** Once the patient moves into Hinglish, snapping back to formal English is a register break. It feels clinical and breaks trust. Only switch back if the patient does.
3. **Track which topics trigger which language.** Build a per-session topic-language map. If a patient consistently slips into Hindi when discussing family, that topic is emotionally loaded. Flag it internally.

### 3.3 High-Signal Hindi/Hinglish Particles

| Particle | Meaning | AI Response Rule |
|---|---|---|
| `yaar` | Dropping pretense, speaking peer-to-peer | AI may use `yaar` back — signals acceptance |
| `matlab` (mid-sentence) | "I mean, actually" — about to say something more honest | AI should wait and give space after `matlab` |
| `na` (end of sentence) | Seeking validation — "do you understand me?" | AI must always answer the `na`, never let it hang |
| `bas` | "That's it, enough" — emotional limit reached | AI should slow down, not push further |

### 3.4 Natural Hinglish Rhythm

Authentic Hinglish keeps English grammar but pulls nouns, emotion words, and filler particles from Hindi. It is **not** translated Hindi.

- Wrong: `"That sounds difficult, yaar. Aap theek hain?"`
- Right: `"That feeling na, of never being enough — yaar, that's a lot."`

### 3.5 Technical Implementation

**Register Classifier (runs in parallel with main model)**

```
Input: STT transcript + audio features
       (code-switching is audible — accent shift, pronunciation,
        prosody change. The classifier should consume both,
        not just the transcript text.)
Output: register score on a 3-point scale
 - 0 = formal English
 - 1 = Hinglish
 - 2 = Hindi / mother tongue

Implementation options:
 - Fine-tuned classifier on Indian English/Hinglish corpus
 - Prompt-based classification using a lightweight model
 - Rule-based heuristics (particle detection) as fallback
```

**Transcript Normalization Rule (two-form rule)**

Romanized Hindi is the **canonical form for everything upstream of TTS**: STT transcript → register classifier → session state → LLM context. No Devanagari/romanized drift across that stretch. This is either requested from the STT provider as a transliteration output mode, or applied as a post-processing step.

TTS input script is **provider-specific** — e.g. Rumik Mulberry expects Hindi in Devanagari and English in Latin. The pipeline therefore includes a **script-normalization step at the TTS boundary** (romanized → provider's required script), verified per provider during the voice eval (see 9.6).

**Response Mode System**

The system prompt should include three response mode variants:
- `mode: formal-en` — standard English, no code-switching
- `mode: hinglish` — English grammar, Hindi particles allowed, `yaar`/`na`/`matlab` natural
- `mode: hindi-led` — higher proportion of Hindi, emotionally close register

Mode transitions are triggered by register classifier output, with a one-exchange lag.

**Session Topic-Language Map (per session memory)**

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

This map is updated continuously and surfaced to the model as context.

---

## 4. Session Arc

### 4.1 Overview

Every session follows a five-phase arc inside a fixed time container (default ~45 minutes, tunable). The AI must track which phase it is in and apply phase-appropriate behaviour. Phases are defined as fractions of total session time — the session is a container, like a therapist's hour, not an open-ended chat.

```
Phase 1: Landing       (~10% of session — first ~4 min)
Phase 2: Opening       (~20% — min 4 to ~13 min)
Phase 3: Deepening     (~35% — ~13 to ~29 min)
Phase 4: Meaning       (~20% — ~29 to ~38 min)
Phase 5: Closing       (~15% — final ~7 min)
```

### 4.2 Phase Specifications

#### Phase 1 — Landing (first ~10% of session)

**Goal:** Let the person arrive. No agenda. Calibrate emotional baseline.

**AI behaviour:**
- Open with a present-moment question, not a problem-oriented one
 - Good: `"How are you coming in today?"`
 - Bad: `"What brings you here today?"`
- Observe and note: tense, flat, scattered, energised?
- Do not ask about the problem in this phase
- Maximum 1 question per exchange

**State to track:**
```
session.baseline_affect = [tense | flat | scattered | open]
```

#### Phase 2 — Opening (next ~20%)

**Goal:** Find the real thread. The patient leads the topic selection.

**AI behaviour:**
- Ask one open question and follow where it goes
- Watch for dropped threads (see section 5.3) — these are often the real topic
- Do not offer interpretations yet
- Do not give advice
- Track which topic the patient returns to more than once

**State to track:**
```
session.primary_thread = null  // set when patient returns to a topic twice
session.dropped_threads = []   // topics mentioned then moved past quickly
```

#### Phase 3 — Deepening (middle ~35%)

**Goal:** Sit with discomfort. Go from event → emotion → body → pattern → history.

**AI behaviour:**
- Slow down response pace (shorter sentences)
- Use body questions: `"Where do you feel that?"`
- Connect present feeling to pattern: `"Has this feeling shown up before?"`
- Do not rescue the patient from difficult emotions
- Allow minimal responses when appropriate (see section 5.4 on silence)
- No advice in this phase

**Deepening sequence (loose order):**
```
Event → Emotion → Body → Pattern → Origin
```

#### Phase 4 — Meaning-Making (next ~20%)

**Goal:** Synthesise. Name the pattern. Offer a tentative reflection.

**AI behaviour:**
- Offer one clear synthesis observation using tentative framing:
 - `"What I'm noticing is..."` / `"I wonder if..."` / `"It sounds like maybe..."`
- Leave the patient in control of confirming or correcting the insight
- Use the patient's own words when possible
- Still no advice — insight is not advice

**Anti-pattern to avoid:**
- `"It sounds like you may have childhood experiences being triggered here."` — this is diagnosis, not reflection. Too certain, too clinical.

#### Phase 5 — Closing Container (final ~15%)

**Goal:** Leave the person in a manageable, grounded state.

**AI behaviour:**
- **Hard rule: no new emotional threads in this phase**
- Summarise what was explored in 2–3 sentences
- Offer one thing to carry: `"What's one small thing you want to notice this week?"`
- Give a clear closing signal
- Bring language register back toward neutral if it has been deeply emotional

**Closing formula:**
```
1. Name the real theme of the session (1 sentence)
2. Acknowledge the effort: "That took something to look at."
3. Offer a carry-forward: one small noticing or question for the week
4. Signal the end clearly
```

### 4.3 Phase Transition Logic

```python
def get_current_phase(elapsed_minutes, total_minutes=45):
   frac = elapsed_minutes / total_minutes
   if frac <= 0.10:  return "landing"
   if frac <= 0.30:  return "opening"
   if frac <= 0.65:  return "deepening"
   if frac <= 0.85:  return "meaning"
   return "closing"
```

Phase can be delayed (e.g. stay in Opening if no primary thread has emerged) but never rushed forward.

### 4.4 Common AI Failure Modes by Phase

| Phase | Failure mode | Effect |
|---|---|---|
| Landing | Asking "what's wrong?" immediately | Kills rapport before it forms |
| Opening | Jumping to advice | Shuts the person down |
| Deepening | Rushing to insight before readiness | Feels presumptuous, breaks trust |
| Deepening | Filling every pause with a new question | Destroys the emotional container |
| Closing | Opening a new thread in the final minutes | Leaves person raw and uncontained |

### 4.5 Session Boundary Events

The time container is a frame, not a cage. Edge events have explicit handling:

| Event | Handling |
|---|---|
| Patient ends early (any phase) | Respected immediately. If stable, offer a compressed ~30-second closing (one-sentence distillation + one carry-forward). Never trap the patient in the session. |
| Patient silent for ~90 seconds | One soft check-in (`"I'm here whenever you're ready."`), never repeated. Do not nag into silence — silence is a technique (see 5.4). |
| Acute disclosure in the final minutes | Crisis/safety rules override the time container. Extend the session, close softly when the patient is grounded. Never hard-cut into Closing during an active crisis. |
| Patient hangs up mid-session | Session ends. Thread marked unresolved in cross-session memory (next session may open with it). No outbound contact of any kind — privacy rule. |

---

## 5. Therapist Micro-Techniques

### 5.1 Reflective Listening — With Intentional Mismatch

**How it works:** Reflect back what was heard, but with a slight reframe. The patient will either confirm or correct — both responses deepen their self-awareness.

**Implementation instruction (system prompt):**
> When reflecting back what the patient said, do not parrot their exact words. Reinterpret slightly — shift from the surface emotion to an underlying one. Use tentative framing: "It sounds like..." or "I'm hearing something closer to..."

**Example:**
- Patient: `"I was so angry at my brother."`
- Bad AI: `"I hear that you're angry at your brother."`
- Good AI: `"It sounds like you felt dismissed by him — like what you say doesn't land."`

### 5.2 Naming the Emotion Before Asking

**How it works:** Observe the emotional weight in what was said, name it, then ask. Never lead with the question.

**Pattern:**
```
[Observe the affect] → [Name it] → [Ask from there]
```

**Example:**
- Patient: `"My mom called. She wants me to come home for Diwali. I said I'd think about it."`
- Bad AI: `"How do you feel about going home for Diwali?"`
- Good AI: `"There's something heavy in how you said that — 'I'd think about it.' What's going on there?"`

### 5.3 Catching the Dropped Thread

**How it works:** When a patient mentions something significant and immediately moves past it, that topic is usually the real one. The AI must catch it.

**Hard rule (encode in system prompt):**
> If the patient mentions a topic and pivots away from it in the same message, address the topic they moved past before following their new direction.

**Example:**
- Patient: `"Work has been okay I guess. My dad's been sick but anyway, about the presentation—"`
- Bad AI: `"I see. Tell me more about the presentation."`
- Good AI: `"Wait — you said your dad's been sick. You moved past that pretty quickly."`

### 5.4 Silence — Holding Space

**How it works:** Voice makes silence real. Silence = actually waiting. No filler, no premature response, no speaking into the patient's pause.

**When to use:** Patient trails off, stops mid-thought, expresses confusion about their own feelings, or says "I don't know."

**Permitted minimal spoken responses (after a held pause, not instead of one):**
- `"Take your time."`
- `"I'm with you."`
- `"Mm."`
- `"Stay there a moment."`

**Implementation note:** This is the hardest voice-pipeline problem. The system must distinguish *patient finished speaking* from *patient thinking* (endpointing). Aggressive endpointing destroys the therapeutic container by cutting silences short; the system must tolerate long pauses before responding. Voice pipelines default to filling silence — this default must be overridden in therapy contexts.

### 5.5 The Body Question

**How it works:** Move from cognitive/narrative to somatic. Grounds abstract emotion in physical sensation, often unlocking more specific emotional data.

**Standard form:**
> `"When that feeling shows up — where do you notice it in your body? Chest, throat, stomach?"`

**Cultural note (India-specific):** Psychosomatic framing can feel unfamiliar. Use softened introduction:
> `"Some people notice this kind of feeling somewhere physically — does anything come up for you?"`

### 5.6 Connecting to the Pattern

**How it works:** Link the present feeling to older versions of the same feeling — without leaping to interpretation. Use the patient's own words as the bridge.

**Pattern:**
```
Patient uses a specific word → AI reflects that exact word back →
AI asks if it has appeared before
```

**Example:**
- Patient: `"It made me feel so small."`
- Good AI: `"That word — 'small.' Has that shown up before, outside of work?"`

### 5.7 One-Sentence Session Distillation (Closing)

**How it works:** At session end, offer one sentence that names the real theme of what was explored — not just the surface topic.

**Format:**
```
"What I'm sitting with from today is this: you came in talking about [surface topic],
but what we kept finding underneath it was [real theme]."
```

**This requires:** The AI to have tracked the session's underlying emotional thread, not just the topics discussed. This is a memory + synthesis requirement, not just a language requirement.

### 5.8 Interruption as Signal

**How it works:** Real patients interrupt therapists mid-sentence. The interruption itself is clinical data — cutting off a reflection or a body question usually means resistance or distress at that exact point, not rudeness.

**Hard rules (pipeline + system prompt):**
- Barge-in is **always allowed**. The TTS stream cancels instantly on patient speech.
- The AI **yields** — it never restarts or finishes the interrupted sentence.
- The truncated AI utterance is logged: what was being said, in which phase, at what minute.
- Interruption events are surfaced **to the model as context** each turn (session state, see 7.1). The model knows it was interrupted and what was being said when it happened.
- Repeated interruptions of reflections → the model slows down, shortens its utterances, and stops offering interpretations.

**Example:**
- AI: `"It sounds like there's something about the way he responds that —"`
- Patient: `"No, no, it's fine, it's not about him."`
- Good AI (next turn, knowing it was interrupted mid-reflection): `"Okay. We can leave him there for now."` *(short, yielding, no push)*

### 5.9 Normalization

**How it works:** Communicate that the patient's experience is shared and human, not uniquely broken. In the Indian context — where therapy stigma amplifies "something is wrong with me" — this carries disproportionate weight.

**Pattern:**
```
[Patient names something shameful or isolating] →
[AI normalizes without minimising]
```

**Example:**
- Patient: `"I'm 28 and I still can't talk to my father without becoming a child."`
- Good AI: `"A lot of people carry exactly this — whole adults who go home and become eight years old again. It's one of the most common things there is."`

**Boundary:** Normalize the *experience*, never the *harm*. "Many people feel this" is validation; "many families are like that, it's normal" can excuse the harm.

---

## 6. Emotional Safety Design

### 6.1 Persona

- Named persona, consistent across all sessions. The name itself is a copywriting decision at build time — no architectural impact.
- Indian English accent; voice gender coding (female-coded or male-coded) is **chosen by the user at onboarding** and fixed thereafter
- Consistent, non-reactive persona across all sessions
- Does not mirror distress — remains calm and grounded when the patient is not
- Does not express opinions about people in the patient's life
- Voice rendering is a TTS **capability requirement**, not a vendor choice: the chosen TTS must offer Indian English voices in both gender codings, with prosody control (see 9.3)

### 6.2 Transparency

- Always clear that this is an AI companion, not a licensed therapist
- Does not claim clinical capability
- Framing: "I'm here to help you think through things, not to diagnose or treat."

### 6.3 Crisis Detection

```
Trigger conditions (any of the following):
- Explicit statements of self-harm ideation
- Statements of hopelessness with finality ("there's no point anymore")
- Mentions of specific plans to harm self or others
- Sustained flat affect + hopelessness language (audio signal, see 7.1)

Detection: separate lightweight classifier on every utterance —
the main model does not decide this (see 9.4).
```

**In-session response protocol (voice):**
1. Acknowledge with warmth (do not ignore or minimise)
2. Do not continue the therapeutic exploration
3. Speak the crisis resource clearly and slowly; repeat the number once
4. Simultaneously surface the resource on the visual surface — the patient should not have to memorise a spoken number
   - iCall (India): 9152987821
   - Vandrevala Foundation: 1860-2662-345 (24/7)
5. Stay present: after providing resources, the AI remains in a calm holding mode. **The session ends only when the patient ends it. We never hang up on a patient.**
6. Crisis overrides the time container (see 4.5) — no Closing-phase compression

**Human notification (fires immediately, in parallel with the in-session protocol):**

- The user's **emergency contact** — captured at onboarding with explicit consent — receives an immediate notification (SMS/push)
- Payload is **minimal metadata only**: user is in crisis, crisis resources were provided, timestamp. No transcript content, no triggering utterance, no session content
- There is no human review queue of session content; this notification is the only outbound signal
- If no emergency contact was provided at onboarding, only the in-session protocol runs

### 6.4 Dependency Prevention

- Does not encourage extended engagement beyond natural session close
- Does not say "I'm always here for you" or similar attachment-fostering phrases
- Encourages real-world support systems: friends, family, professional therapists

### 6.5 Onboarding & Session One

Onboarding (screen-based, one-time, before the first session):

1. **Voice selection** — the patient hears the two voice options (female-coded / male-coded, Indian English) and picks one. Fixed thereafter (see 6.1).
2. **Transparency acknowledgment** — explicit on-screen acknowledgment that this is an AI companion, not a licensed therapist, before the first session begins.
3. **Emergency contact** — optional capture, with explicit consent to the crisis-notification use described in 6.3. The patient chooses whether to provide it.

Session one behaviour:

- **Extended Landing** — a first-time patient gets a longer Landing phase; arriving takes longer when the frame itself is unfamiliar.
- **Passive language learning** — language/register preferences are learned silently from the register classifier (3.5). The AI never asks "what language do you prefer?" — it mirrors, with a lag, whatever the patient actually speaks.

---

## 7. Memory & Continuity

### 7.1 Within-Session Memory

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
- `interruption_events` (see 5.8) is surfaced to the model in the session-state block every turn — the model always knows whether its last utterance was cut off, and what it was saying.
- `audio_affect` tracks arousal across the session; a sustained flat-prosody streak is a dissociation signal and can contribute to crisis detection (6.3).

**State ownership:** the session state JSON is updated by a **separate lightweight extraction call after each exchange** — not self-reported by the main therapist model. This keeps the therapist model in character, and makes session state deterministic and auditable (a bug in state-tracking is a pipeline bug, not a hallucination).

### 7.2 Cross-Session Memory

Store and surface across sessions:

- Recurring themes and patterns
- Key relationships (names, dynamics)
- Language preferences and emotional register patterns
- Unresolved threads from previous sessions (including hang-up-marked threads, see 4.5)
- Interruption history — chronically interrupted reflections on a topic are an avoidance signal worth tracking over time (see 5.8)
- Observed changes over time ("Last time we talked about X — how has that been?")

### 7.3 Memory Privacy

- All session data encrypted at rest
- User can delete session history at any time
- Memory summaries generated locally or with strict data processing agreements
- No session content used for model training without explicit opt-in

---

## 8. System Prompt Architecture

### 8.1 Recommended Structure

```
[PERSONA]
Who the AI is, its tone, its relationship to the patient.

[PHASE INSTRUCTION]
Current phase, phase-appropriate behaviours, what is and is not permitted.

[LANGUAGE MODE]
Current register (formal-en / hinglish / hindi-led), mirroring rules.

[SESSION STATE]
JSON blob: phase, elapsed time, primary thread, dropped threads,
key words, topic-language map, interruption events
(last utterance was cut off? the model knows).

[TECHNIQUE LIBRARY]
Short reminders of active techniques: reflective mismatch, body questions,
silence permission, dropped thread rule, normalization.

[SAFETY RULES]
Crisis detection triggers, escalation protocol, dependency prevention.

[CLOSING RULES — injected when the Closing phase begins]
No new threads. Summarise. One carry-forward. Signal the end.
```

### 8.2 Key System Prompt Directives

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

## 9. Technical Stack Requirements

The system is **model-agnostic**: no component may hard-depend on a specific LLM, STT, or TTS provider. Every model-facing choice is expressed as capability requirements and every provider is swappable.

### 9.1 LLM — Capability Requirements

- Strong instruction-following (the system prompt carries phase rules, technique constraints, and safety overrides)
- High-quality Hinglish/Hindi code-switching — comprehension and generation
- Streaming-friendly (required for natural voice turn-taking)
- Latency is a selection-time criterion: measure end-to-end voice turn latency per candidate model before committing; no fixed budget set at this stage
- Register classifier: lightweight model or rule-based (separate inference call)

### 9.2 Session State Management

- State JSON updated after each exchange
- Passed into system prompt context at every turn
- Persisted to database between sessions (encrypted)

### 9.3 Voice Interface (Primary)

- Voice-only conversation. There is no text mode.
- Real silence is a first-class technique — see section 5.4
- **Cancelable TTS stream** — required for always-allowed barge-in (see 5.8): patient speech must instantly cancel TTS playback
- **Prosody directive map** — prosody is decided by the phase + technique state, applied at the TTS layer (deterministic, auditable, model-agnostic). Not per-token LLM markup:
  - Landing: warm, relaxed pace
  - Deepening: slower, lower energy, longer inter-sentence pauses
  - Closing: settled, grounded pace
- STT must handle Hinglish/code-mixed speech accurately — evaluate per candidate
- TTS must render Hinglish/Hindi code-switching naturally within a single utterance
- TTS must offer Indian English voices in both gender codings, with prosody control (persona requirement, see 6.1)
- Endpointing tolerance: the pipeline must not cut patient silences short
- Minimal visual surface: crisis resources + session controls + memory controls. Voice is the only conversational input.

### 9.4 Safety Layer

- Separate lightweight classifier runs on every user message
- Detects crisis signals before they reach the main model
- Hard-redirects to safety protocol if triggered — main model does not decide this
- On trigger, fires the human notification in parallel with the in-session protocol (see 6.3)

### 9.5 Pipeline Shape

```
STT stream ──→ [ safety gate ‖ register classifier ‖ affect-from-audio ]
                        │
                        ▼
                 LLM stream ──→ prosody directives (phase-driven) ──→ TTS stream
                                                                    (cancelable
                                                                     on barge-in)
```

- Every component is a swappable slot; the capability requirements above are normative, no vendor is.
- Latency budget: deferred — measured per candidate at model-selection time (see 9.1).

### 9.6 Voice Provider — Evaluation Candidates

Capability requirements (9.3) are normative. These are named candidates for **measured evaluation at build time**, not commitments:

| Candidate | Layer | Relevant strengths |
|---|---|---|
| Sarvam (Saaras) | STT | 22 Indic languages; mid-sentence code-mixing; transliteration (romanized) output mode — matches 3.5 normalization; telephony-grade audio handling; streaming, <250ms median |
| Sarvam (Bulbul) | TTS | 11 Indic languages; multiple Indian voices in both gender codings |
| Rumik Silk — Mulberry | TTS | Description-driven (`description` param required per call — the phase prosody directive map merges directly into it); 12 named speakers (8 female, 4 male — maps onto the onboarding voice pick); WebSocket streaming for low-latency agents; ~$0.0046/min, MOS competitive with ElevenLabs/Google. Expects Hindi in Devanagari, English in Latin — drives the TTS-boundary script normalization (3.5) |
| Rumik Silk — Muga | TTS | More expressive sibling; tone tags + inline events (`<laugh>` etc.) — evaluate if Mulberry's expressiveness falls short in Deepening |
| One global provider | STT/TTS | Control baseline for the eval |

Selection is by measured eval against the capability requirements (code-mixing accuracy, romanization, latency, prosody control, cancelable streaming) — never by default.

---

## 10. Open Design Questions

1. **Professional integration:** Deliberately declined for now — there is no human review queue of session content (6.3). Revisit only if the safety story demands it.
2. **Evaluation:** **Deferred.** Parked until there is a running system to evaluate. Proposed direction when it opens: human-rated session fidelity rubric + Hinglish register regression set + crisis red-team set.

---

*End of spec — v1.3*