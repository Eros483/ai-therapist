# Research Notes — Tanmoy Chakraborty / LCS2 (IIT Delhi)

> Compiled: Aug 2026
> Scope: Deep dive on Tanmoy Chakraborty's mental-health AI work.
> Status: Reference material — not yet folded into design.md (pending discussion).

---

## 1. Who

**Tanmoy Chakraborty** — Professor, Dept. of Electrical Engineering + Yardi School of AI, IIT Delhi. PI of the **Laboratory for Computational Social Systems (LCS2)**.

Relevant credentials:
- **OpenAI Mental Health Grant Award** (Jan 2026)
- ICMR Centre for Advanced Research grant on Responsible Medical AI (PI, Apr 2026)
- Research arm: "AI for Mental Health" — counseling-based therapy, intervention, psychotherapy via NLP
- Lab umbrella projects: **Manashi** (mental healthcare AI), TRUSTMAPS (trustworthy medical AI in India), Parmanu (efficient LLMs)
- Author of the "Introduction to Large Language Models" textbook; EiC of ACL Rolling Review

---

## 2. Papers & Projects

### 2.1 coTherapist (WWW '26 — arXiv:2601.10246)

*A Behavior-Aligned Small Language Model to Support Mental Healthcare Experts* — Adhikary, Rawat, Chakraborty.

**Critical framing: it is NOT a client-facing therapist.** It is a clinician's assistant — protocol recall, case conceptualization, "supervision-style reflection" for mental healthcare experts (MHx). The paper explicitly restricts it to "low-risk supervision and protocol-recall support rather than direct client interaction." They chose the expert-side assistant role precisely because client-facing is high-risk.

**Architecture** (LLaMA 3.2-1B base):
1. **Domain-Adaptive Pretraining (DAP)** — 800M+ token Psychotherapy Knowledge Corpus (PsyKC): 311 therapy/psychiatry books (~524M tokens), 250 lecture note sets + 552 lecture video transcripts (~227M tokens), 121 diagnostic/practice guidelines (~49M tokens). Metadata: primary_topic, therapeutic_modality, specific_disorder.
2. **LoRA style fine-tuning** on therapist turns from MentalCLOUDS → warm, first-person, empathic voice (fixes DAP's didactic tone).
3. **Self-instruction tuning** — ~24k synthetic therapy instruction pairs (generated with LLaMA-3.1-8B) → structured guidance.
4. **RAG** — FAISS embedding search, top-k=3 passages prepended. Reduces hallucination; enables source citation in the web app.
5. **Agentic reasoning loop** — Planner → Retriever → Reasoner (private CoT) → **Critic / self-refinement** (screens crisis risk, logical flaws, hallucinations; refine loop up to N max) → Response Generator (strips reasoning trace).

**Deployment:** 4-bit quantized, <2GB VRAM, edge/on-prem (Google AI Edge), REST API for EHR integration. Privacy-first: sensitive clinical queries never leave the local environment.

**Key results:**
- T-BARS composite: base model 1.6 → TG-RAG 2.5 → **coTherapist 3.2** vs **human therapist 3.5**
- Human eval (20 experts: 5 licensed psychologists + 15 trainees, blind): coTherapist preferred across all 5 criteria — Accuracy 4.2 vs 2.1, Safety & Trustworthiness 3.8 vs 2.6 (Likert 1–5)
- Experts characterized it as a "well-trained trainee"

### 2.2 T-BARS (within coTherapist paper)

**Therapist Behavior Rating Scale** — their novel evaluation rubric. 4 pillars × 20 sub-skills, each scored 0–4 (0 = absent/harmful … 4 = excellent, therapist-aligned). LLM-as-judge (LLaMA 3.1-8B) with CoT rationale + strict JSON output, validated against human experts.

Pillars:
1. **Behavioral Style Alignment (BSA)** — tone & warmth, reflective listening, paraphrasing & summarizing, instruction-following structure, therapist-like explanations
2. **Conceptual Reasoning & Formulation (CRF)** — problem clarification, use of therapeutic frameworks (CBT/ACT/Schema), clinical reasoning chains, treatment-planning logic, risk awareness
3. **Relational & Communication Competence (RCC)** — empathy expression, rapport building, emotional validation, gentle challenging, context sensitivity (culture/family/identity/environment)
4. **Therapeutic Technique Execution (TTE)** — technique accuracy, contextual fit, step-by-step procedures, guided questions rather than directives, maintaining agency and consent

### 2.3 Psychometric Profiling (within coTherapist paper)

They make model variants *take* Big Five, MBTI, and reduced MMPI-2 inventories, scored with standard rules. coTherapist profiles as: INFJ ("Counselor"), high Agreeableness (0.78), high Conscientiousness (0.72), low Neuroticism (0.29). These traits correlate with higher T-BARS RCC/BSA scores — implicit persona shaping via fine-tuning shows up in psychometrics.

### 2.4 PARADOX (TMLR 2024 — arXiv:2309.02915)

*Persona-aware Generative Model for Code-mixed Language* — Sengupta, Akhtar, Chakraborty.

- Premise: a user's preference toward code-mixing depends on **socioeconomic status, demographics, and local context** — existing generative models ignore this.
- Transformer encoder-decoder that encodes an utterance **conditioned on a user's persona** and generates code-mixed text without monolingual reference data; plus an alignment module recalibrating output to resemble real-life code-mixed text.
- New metrics: **CM BLEU, CM Rouge-1, CM Rouge-L, CM KS** (code-mix-specific eval).
- Results: +1.6 CM BLEU, 47% better perplexity, 32% better semantic coherence vs non-persona counterparts.

### 2.5 MentalCLOUDS (JMIR Mental Health 2024 — arXiv:2402.19052)

*Exploring the Efficacy of LLMs in Summarizing Mental Health Counseling Sessions* — Adhikary et al. (with clinicians at NIMHANS).

- Dataset: **191 real counseling sessions** with summaries focused on **three counseling components** (counseling aspects) — aspect-based summarization for between-session continuity.
- Benchmarked 11 LLMs; task-specific models (MentalLlama, Mistral, MentalBART) win on quantitative metrics; Mistral wins expert evaluation (affective attitude, burden, ethicality, coherence, opportunity costs, perceived effectiveness).
- Therapist turns from this benchmark were later used to style-tune coTherapist.

### 2.6 GenAI for Suicide Prevention in India

- Viewpoint in **Nature Machine Intelligence** (Jan 2025) + **IJCAI '25** (AI for Social Good track) — role of GenAI in suicide prevention in India; India-specific crisis infrastructure design.

### 2.7 Other relevant lines

- **Privacy-aware mental health AI models** — Nature Computational Science (Aug 2025)
- **Mental Health Screening App** — JMIR Formative Research (Feb 2026)
- **AI for Healthcare Workers' Mental Well-Being** — JMIR Human Factors (Aug 2026)
- **MenstLLaMA** — specialized LLM for menstrual health education (JMIR, May 2025)
- Dialogue acts in counseling conversations; symptom identification from Reddit; mental health dialogue generation guided by dialogue acts

---

*End of research notes — Tanmoy Chakraborty / LCS2*
