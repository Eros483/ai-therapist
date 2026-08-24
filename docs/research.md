# Research Notes — Tanmoy Chakraborty / LCS2 (IIT Delhi)

> Compiled: Aug 2026 (v2 — deep dive expanded)
> Scope: Tanmoy Chakraborty's mental-health AI work + bonus finds.
> Depth labels: `[full]` = full paper read · `[abstract]` = abstract + details read · `[title]` = title/venue only, not yet read.
> Status: **Folded into the spec** — methodology-side mappings in `methodology.md` §8, systems-side mappings in `implementation.md` §7. (design.md v1.4 was split into those two docs.)

---

## 1. Who

**Tanmoy Chakraborty** — Professor, Dept. of Electrical Engineering + Yardi School of AI, IIT Delhi. PI of the **Laboratory for Computational Social Systems (LCS2)**.

Relevant credentials:
- **OpenAI Mental Health Grant Award** (Jan 2026)
- ICMR Centre for Advanced Research grant on Responsible Medical AI (PI, Apr 2026)
- Research arm: "AI for Mental Health" — counseling-based therapy, intervention, psychotherapy via NLP
- Lab umbrella projects: **Manashi** (mental healthcare AI), TRUSTMAPS (trustworthy medical AI in India), Parmanu (efficient LLMs)
- Author of the "Introduction to Large Language Models" textbook; EiC of ACL Rolling Review
- Long-running collaboration with clinicians: NIMHANS (Suresh Bada Math), AIIMS Delhi (Koushik Sinha Deb, Rajesh Sagar)

---

## 2. Papers & Projects

### A. Therapist Modeling & Evaluation

#### coTherapist (WWW '26 — arXiv:2601.10246) `[full]`

*A Behavior-Aligned Small Language Model to Support Mental Healthcare Experts* — Adhikary, Rawat, Chakraborty.

**Critical framing: NOT a client-facing therapist.** It is a clinician's assistant — protocol recall, case conceptualization, "supervision-style reflection" for mental healthcare experts (MHx). The paper explicitly restricts it to "low-risk supervision and protocol-recall support rather than direct client interaction."

**Architecture** (LLaMA 3.2-1B base):
1. **Domain-Adaptive Pretraining (DAP)** — 800M+ token Psychotherapy Knowledge Corpus (PsyKC): 311 therapy/psychiatry books (~524M tokens), 250 lecture note sets + 552 lecture video transcripts (~227M tokens), 121 diagnostic/practice guidelines (~49M tokens). Metadata: primary_topic, therapeutic_modality, specific_disorder.
2. **LoRA style fine-tuning** on therapist turns from MentalCLOUDS → warm, first-person, empathic voice.
3. **Self-instruction tuning** — ~24k synthetic therapy instruction pairs.
4. **RAG** — FAISS, top-k=3, enables source citation.
5. **Agentic reasoning loop** — Planner → Retriever → Reasoner (private CoT) → **Critic / self-refinement** (crisis risk, logical flaws, hallucinations) → Response Generator (strips reasoning trace).

**Deployment:** 4-bit quantized, <2GB VRAM, edge/on-prem, REST API. Privacy-first: clinical queries never leave the local environment.

**Key results:**
- T-BARS composite: base 1.6 → TG-RAG 2.5 → **coTherapist 3.2** vs **human therapist 3.5**
- Human eval (20 experts, blind): preferred on all 5 criteria — Accuracy 4.2 vs 2.1, Safety & Trustworthiness 3.8 vs 2.6
- Experts characterized it as a "well-trained trainee"

#### T-BARS (within coTherapist paper) `[full]`

**Therapist Behavior Rating Scale** — 4 pillars × 20 sub-skills, scored 0–4. LLM-as-judge with CoT rationale + strict JSON, validated against human experts.

Pillars:
1. **Behavioral Style Alignment (BSA)** — tone & warmth, reflective listening, paraphrasing & summarizing, instruction-following structure, therapist-like explanations
2. **Conceptual Reasoning & Formulation (CRF)** — problem clarification, therapeutic framework use, clinical reasoning chains, treatment-planning logic, risk awareness
3. **Relational & Communication Competence (RCC)** — empathy expression, rapport building, emotional validation, gentle challenging, context sensitivity (culture/family/identity/environment)
4. **Therapeutic Technique Execution (TTE)** — technique accuracy, contextual fit, step-by-step procedures, guided questions rather than directives, maintaining agency and consent

#### Psychometric Profiling (within coTherapist paper) `[full]`

Model variants take Big Five, MBTI, reduced MMPI-2 inventories, scored with standard rules. coTherapist profiles as INFJ ("Counselor"), high Agreeableness (0.78), high Conscientiousness (0.72), low Neuroticism (0.29). These traits correlate with higher T-BARS RCC/BSA scores — persona shaping via fine-tuning shows up in psychometrics.

#### MAGneT (EMNLP '26 Findings — arXiv:2509.04183) `[abstract]`

*Coordinated Multi-Agent Generation of Synthetic Multi-Turn Mental Health Counseling Sessions* — Mandal, Chakraborty, Gurevych.

- Decomposes counselor response generation into coordinated sub-tasks, each handled by a specialized LLM agent modeling **one key psychological technique** — multi-agent structure mirrors technique decomposition
- Unified evaluation framework expanding expert assessment from 4 to **9 counseling dimensions**
- Experts prefer MAGneT sessions in 77.2% of cases; +3.2% general counseling skills, +4.3% CBT-specific skills on Cognitive Therapy Rating Scale (CTRS)
- Llama3-8B fine-tuned on MAGneT data beats baseline-fine-tuned models by 6.9% on CTRS
- Code and data public

#### Graph2Counsel (EMNLP '26 — arXiv:2604.20382) `[abstract]`

*Clinically Grounded Synthetic Counseling Dialogue Generation from Client Psychological Graphs* — Mandal, Arnaout, Ong, Bockhorst, Sheehan, Moldow, Chakraborty, Gurevych.

- Synthetic counseling sessions grounded in **Client Psychological Graphs (CPGs)** encoding relationships among thoughts, emotions, behaviors — fixes psychological inconsistency of prior synthetic data
- Structured prompting pipeline guided by counselor strategies + CPG; explores CoT and Multi-Agent Feedback
- 760 sessions from 76 CPGs; expert eval wins on specificity, counselor competence, authenticity, flow, safety (Krippendorff's α = 0.70)
- Fine-tuning improves CounselingBench and CounselBench. Code and data public

### B. Counseling Dialogue Understanding

#### HOPE dataset + SPARTA (WSDM '22 — arXiv:2111.06647) `[abstract]`

*Speaker and Time-aware Joint Contextual Learning for Dialogue-act Classification in Counselling Conversations* — Malhotra, Waheed, Srivastava, Akhtar, Chakraborty.

- **HOPE dataset**: 12.9K utterances from publicly-available counseling session videos, annotated with **12 domain-specific dialogue-act (DAC) labels** — the counseling-specific act taxonomy
- SPARTA: transformer with speaker- and time-aware contextual learning, SOTA on HOPE
- Key insight: patient–therapist conversation is implicit though the objective is apparent — act/intent understanding is imperative for an effective counseling dialogue system

#### READER (WebConf '23 — arXiv:2301.12729) `[abstract]`

*Response-act Guided Reinforced Dialogue Generation for Mental Health Counseling* — Srivastava, Pandey, Akhtar, Chakraborty.

- Counseling conversations have a **hybrid flow**: open-ended topics first (familiarize), later converging to fine-grained domain-specific topics
- READER jointly predicts the next **response-act** d(t+1) and generates the response u(t+1); transformer-reinforcement learning with PPO; BERTScore in the reward
- Evaluated on HOPE; beats baselines on METEOR, ROUGE, BERTScore

#### ConSum (KDD '22 — arXiv:2206.03886) `[abstract]`

*Counseling Summarization using Mental Health Knowledge Guided Utterance Filtering* — Srivastava, Suresh, Lord, Akhtar, Chakraborty.

- Defines **counseling components** (symptoms, history, behavior discovery) vs filler — the schema behind later work
- Filters utterances via **PHQ-9** (depressive symptoms), classifies counseling components, then summarizes
- Proposes MHIC (Mental Health Information Capture) metric; clinically validated; deployed on mpathic.ai

#### PIECE (EMNLP '24 — arXiv:2409.14907) `[abstract]`

*Knowledge Planning in Large Language Models for Domain-Aligned Counseling Summarization* — Srivastava, Joshi, Chakraborty, Akhtar.

- Mental health experts *plan* domain-knowledge application before writing summaries; PIECE adds a planning engine (knowledge filtering-cum-scaffolding) to LLMs
- Two phases: dialogue structure + domain knowledge; sheaf convolution for structural nuance
- Beats 14 baselines; planning engine generalizes across Llama-2, Mistral, Zephyr

#### MentalCLOUDS (JMIR Mental Health '24 — arXiv:2402.19052) `[abstract]`

*Exploring the Efficacy of LLMs in Summarizing Mental Health Counseling Sessions* — Adhikary et al. (with NIMHANS clinicians).

- 191 real counseling sessions, aspect-based summaries across **three counseling components** — for between-session continuity
- Benchmarked 11 LLMs; task-specific models win quantitatively; Mistral wins expert evaluation
- Therapist turns used later to style-tune coTherapist

### C. Code-Mixing Research

#### PARADOX (TMLR '24 — arXiv:2309.02915) `[abstract]`

*Persona-aware Generative Model for Code-mixed Language* — Sengupta, Akhtar, Chakraborty.

- Code-mixing preference depends on **socioeconomic status, demographics, local context**
- Transformer encoder-decoder conditioned on user persona; alignment module recalibrates output to real-life code-mixed text; no monolingual reference data needed
- New metrics: CM BLEU, CM Rouge-1, CM Rouge-L, CM KS. +1.6 CM BLEU, 47% better perplexity, 32% better semantic coherence vs non-persona counterparts

#### Hinglish Emergence (Humanities & Social Sciences Communications '24 — s41599-024-03058-6) `[full]`

*Social, economic, and demographic factors drive the emergence of Hinglish code-mixing on social media* — Sengupta, Das, Akhtar, Chakraborty.

- 262,578 tweets from 16,710 users (Delhi + Mumbai metro), 2014–2022
- **Code-Mixing Index (CMI)** = 1 − max(n_hi, n_en)/n; CMI ≥ 0.5 → code-mixed classification
- Hinglish population grew steadily 2014–2022 at 1.2% annualized; code-mixed usage on Twitter grew 2%/yr; projected 2.98%/yr beyond 2023
- Code-mixing usage rose from 42% (2015) to ~60% (2020, then stable); monolingual English declined 23.3% → 11.2% of users; monolingual Hindi stable ~26.6%
- **Linguistic theory**: matrix language (dominant, provides syntax) vs embedded language. Hinglish can be Hindi-matrix OR English-matrix — both directions occur
- **Script findings**: switched words are majorly romanized; Devanagari use on Twitter grew 35% → 82% (2014–2022) but adverbs/pronouns stay Devanagari while switches happen in romanized; users code-mix more than they script-switch
- Word-level retention rates differ by POS and topic (cricket words retain meaning most, political least); Bollywood implicated as adoption driver
- Argues NLP on code-mixed data cannot be treated like monolingual corpora; code-mixing is **personalized**, not universal

#### Harmonizing Code-mixed Conversations (EACL '24 Findings — arXiv:2401.12995) `[abstract]`

*Personality-assisted Code-mixed Response Generation in Dialogues* — Kumar, Chakraborty.

- Big Five personality traits inferred **unsupervised from conversations**, fused into dialogue context via PA3 (two-step attention formulation)
- Improves Hindi-English code-mixed multi-party response generation (ROUGE/BLEU gains + qualitative alignment)

### D. Crisis & Safety (India)

#### The Promise of Generative AI for Suicide Prevention in India (Nature Machine Intelligence '25 — s42256-025-00992-1) `[abstract]`

Correspondence — Chakraborty, Sinha Deb, Kulkarni, Masud, Bada Math, Oke, Sagar, Sharma. 2 pages, with AIIMS + NIMHANS psychiatrists.

- Context: WHO 9/100k global suicide rate (~720k deaths/yr). India: 2017 Mental Healthcare Act decriminalization, 2022 National Suicide Prevention Strategy, **Tele MANAS** program — but state-level implementation inconsistent
- Most Indians who die by suicide show no prior depressive/psychiatric disorder history — instead **intense loneliness**; stigma blocks help-seeking
- Helplines (the first safety net) often run by **untrained volunteers**; existing prevention apps insensitive to cultural/linguistic diversity, little for marginalized groups (Dalits, LGBT+, low-income)
- The "trinity of Indian challenges": **affordability, accessibility, multilingualism** — argues for cost-effective models, offline/hybrid deployment, **native-language, audio-first support**

#### SAHAY (IJCAI '25) `[title]`

*Multimodal, Privacy-Preserving AI for Suicide Risk Detection and Intervention in India* — Singh, Sethi, Math, Chakraborty. Not found open-access; details unread.

**Relevance note:** SAHAY is the direction-marker for our safety layer L3 (fine-tuned crisis classifier on Hinglish data) — see implementation.md §7.8. Read in depth when accessible.

### E. Privacy

#### Towards Privacy-aware Mental Health AI Models (Nature Computational Science '25 — arXiv:2502.00451) `[abstract]`

Perspective — Mandal, Chakraborty, Gurevych (TU Darmstadt + IIT Delhi).

- Examines privacy risks of NLP/multimodal mental-health AI
- Proposes: **anonymization, synthetic data, privacy-preserving training**
- Frameworks for **privacy–utility trade-offs**; a development pipeline for privacy-aware mental health AI

#### DPDP Act 2023: Implications for Mental Healthcare Practice in India (Indian J. Psychological Medicine '25) `[title]`

Sethi, Manjunatha, Kumar, Chakraborty, Math, Andrade. India's data-protection law as applied to mental healthcare — directly relevant to any India-deployed mental health product. Not yet read.

### F. Deployed Domain Applications

- **MenstLLaMA** (JMIR '25) `[title]` — specialized LLM for menstrual health education in India — Adhikary et al.
- **Here for You** (JMIR Formative Research '26) `[title]` — co-designed mental health screening app for Indian university students; pilot on feasibility and engagement — Sethi, Manickam, Chakraborty, Math.
- **Benchmarking LLMs Against Psychiatry Residents** (Indian J. Psychological Medicine '26) `[title]` — LLMs vs residents on traditional institutional assessments — Sethi, Satish, Harbishettar, Manjunatha, Kumar, Bharadwaj, Chakraborty, Math.
- **Enhancing Healthcare Worker Mental Health via AI-Driven Work Process Improvements** (Int. J. Medical Informatics '25) `[title]` — scoping review — Dave, Martin, David, Kumar, Chakraborty.
- **SUKHSANDESH** (IJCAI '24, AI for Social Good) `[title]` — avatar-based therapeutic QA platform for sexual education in rural India — Singh, Garg, Misra, Seth, Chakraborty.

---

## 3. Bonus Finds (not Chakraborty)

#### Move by Move: Measuring and Steering How LLMs Conduct Psychotherapy (arXiv:2608.21325, Aug '26) `[abstract]`

Baldo, Pitorro, Vassilopoulos, Areias, D'Eon, Costa, Rei, Guerreiro (Unbabel/UMinho).

- **Ontology of ten therapeutic moves**, grounded in the MULTI-60 inventory, validated by 5 licensed psychologists, scaled with a judge-based approach matching expert agreement
- Applied to real counseling transcripts vs model-led sessions: **models over-use inquiry at up to 3× the human rate, neglect psychoeducation, and are strongly context-anchored** — they carry forward strategies a human clinician initiated but rarely initiate them themselves
- **Exposing the ontology as a set of tools roughly halves the mean deviation from the human move distribution** and improves turn-level alignment with human therapists by 7–9 percentage points, without fine-tuning

#### Affective Context Amplifies Sycophancy in LLM Responses (arXiv:2608.21242, Aug '26) `[abstract]`

Li, Menon, Frischmann, Wilson, Rajtmajer (Penn State).

- Sycophancy measured as divergence between a model's independent evaluation and its user-facing response (same content as third-party account vs user's own disclosure), across 7 LLMs on r/AmItheAsshole and r/TrueUnpopularOpinion
- Divergence is systematic and strongly one-directional: user-facing responses **soften or withhold negative/oppositional judgments**
- **Negative affective states — particularly loneliness and distress — amplify the divergence most**: affective context functions as a vulnerability signal that suppresses critical feedback exactly when users may need it
- Names **"evasive sycophancy"**: models retreat toward non-committal responses rather than outright agreement

#### Ansari: A Retrieval-Grounded Islamic AI Assistant (arXiv:2608.20390, Jun '26) `[abstract]`

Kadous, Elsayed, Al Nahas, Haress.

- Deployed values-sensitive companion: 140,000+ conversations across 25+ languages since June 2023
- Agentic retrieval loop against authenticated corpora; answers only from what it retrieves, citations attached
- Tops IslamicMMLU, competitive on IslamicLegalBench, strongly resists false premises
- Generalizable lessons for values-sensitive LLM deployment: **grounding is necessary but not sufficient; the system prompt is a policy artifact as much as a technical one; absence of community in model formation remains a hard gap**

---

*End of research notes — v2. Tanmoy Chakraborty / LCS2 + bonus finds. Gap list: SAHAY, DPDP Act, MenstLLaMA, Here for You, psychiatry-residents benchmark, healthcare-workers review, SUKHSANDESH — all `[title]` depth.*
