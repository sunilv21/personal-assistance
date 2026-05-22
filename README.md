# Personal Assistance — Multilingual Voice Agent

A real-time, browser-based voice assistant that listens in any of **11 Indic languages + English**, replies in the same language with a choice of **39 natural voices**, and runs end-to-end on a streaming pipeline: **Sarvam AI** for speech, **OpenAI** for thinking, and **Vercel Edge Functions** (or local Python) for orchestration.

Tap once, talk normally, get answered in 4–5 seconds. No wake word, no manual buttons mid-conversation, no recording-and-uploading delay.

> **Repo:** https://github.com/sunilv21/personal-assistance

---

## Table of contents

- [What it does](#what-it-does)
- [Live demo](#live-demo)
- [Features](#features)
- [Architecture](#architecture)
- [How it works — full pipeline](#how-it-works--full-pipeline)
- [Tech stack](#tech-stack)
- [Supported languages](#supported-languages)
- [Supported voices](#supported-voices)
- [UI walkthrough](#ui-walkthrough)
- [Quick start (Vercel deploy)](#quick-start-vercel-deploy)
- [Local development (Python)](#local-development-python)
- [Environment variables](#environment-variables)
- [API reference](#api-reference)
- [Configuration knobs](#configuration-knobs)
- [Project structure](#project-structure)
- [Production hardening](#production-hardening)
- [Limitations](#limitations)
- [Cost model](#cost-model)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [License](#license)

---

## What it does

You open the page → tap the orb → grant mic permission once → start talking.

The assistant detects when you stop speaking, transcribes what you said in your chosen language, generates a short reply with GPT-4o-mini, and speaks the reply back in a voice of your choice — all without you having to click a "send" button or press anything else. When the reply finishes, it's already listening for your next utterance.

Two deployment modes coexist in the same repo:

| Mode | Backend | Streaming STT | End-of-speech → first audio | Where to host |
|---|---|---|---|---|
| **Vercel Edge** (default for production) | TypeScript Edge functions, HTTP only | No (Sarvam REST) | ~4–5 s | Vercel, free tier |
| **Python local** | FastAPI + WebSocket | Yes (Sarvam streaming WS) | ~2 s | Your machine, or Railway / Fly / Render |

Both backends serve the **same `index.html`** with the same UI and the same NDJSON event protocol — you can flip between them with zero frontend changes.

---

## Live demo

```
[ tokens chip ]                 VOICE AGENT · LIVE ●           [ ☰ settings ]

                          ╭─────────────────╮
                       ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒
                     ⌒                       ⌒
                   ⌒          ╭─────╮          ⌒
                  ⌒          ╱       ╲          ⌒        ← rings react to voice
                 ⌒          │  ▌▌▌▌▌ │          ⌒
                  ⌒          ╲       ╱          ⌒
                   ⌒          ╰─────╯          ⌒
                     ⌒                       ⌒
                       ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒ ⌒
                          ╰─────────────────╯

           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~  ← live waveform
                       ──●────              ← silence countdown bar

                       ● Listening
                "what's the weather like today?"   ← transcript
```

---

## Features

### Audio pipeline

- **Local VAD with calibration** — measures the ambient noise floor on first activation (1.2 s sample, median + outlier trimming + 1.5σ), then triggers on speech relative to that floor.
- **End-of-speech detection** — drops the recording and uploads as soon as silence holds for *Pause* ms (default 500 ms, slider goes down to 300 ms).
- **Web Audio limiter** — `DynamicsCompressor` (threshold −3 dB, ratio 8:1) prevents the kind of speaker overdrive that sounds like "the speaker is damaged".
- **Back-to-back chunk playback** — each TTS sentence is decoded to an `AudioBuffer` and `start()`-ed at the previous chunk's end timestamp on the audio clock, so there's no inter-sentence gap or click.
- **High-pass / low-pass filters** — 120 Hz HP cuts AC hum and rumble, 4 kHz LP cuts hiss, before audio reaches the analyser. Makes the noise floor calibration meaningful.
- **Browser-level effects** — `echoCancellation`, `noiseSuppression`, AGC disabled (so the analyser reads true levels).
- **Tap-to-interrupt** — tapping the orb while the assistant is speaking drains the playback queue, aborts the in-flight `fetch`, and resumes listening instantly.

### LLM + TTS streaming

- **Streaming Chat Completions** with `stream: true` and `stream_options: { include_usage: true }` so the first token arrives within ~0.5–1 s.
- **Sentence-boundary chunking** on `.!?।` (Devanagari danda included) — finishes a sentence, immediately hands it to TTS while the next LLM tokens are still arriving.
- **Parallel TTS, in-order emit** — each sentence's TTS call is fired immediately, but the results are emitted to the client in the original order via a promise chain. So three short sentences in a row don't queue up serially.
- **Live token usage** — every turn's `prompt_tokens`, `completion_tokens`, and cumulative `session_total` are pushed to the client and shown in the top-left chip.

### Language and voice control

- **11 languages**: English (en-IN), Hindi (hi-IN), Marathi (mr-IN), Tamil (ta-IN), Telugu (te-IN), Kannada (kn-IN), Malayalam (ml-IN), Gujarati (gu-IN), Bengali (bn-IN), Punjabi (pa-IN), Odia (od-IN) — plus Auto-detect.
- **Hard language lock** — when a language is picked, the system prompt explicitly tells the LLM *"reply ONLY in [language]. Never switch languages, no matter what the user says."*
- **39 voices** organized by gender (23 male + 16 female), from Sarvam Bulbul v3.
- **Voice preview button** — sample any voice in the current language *without disturbing the conversation*. The sample text is a natural greeting in that language.
- **Live voice switching** — change voice mid-conversation; the next reply uses the new voice immediately.

### Visualization

- **Audio-reactive orb rings** — 9 concentric ellipses behind the orb. Each ring's perimeter is the live time-domain audio waveform wrapped around it, so they ripple in sync with whoever's currently speaking (you or the assistant).
- **Continuous slow morphing** — each ring has its own slow drift speeds (warp phase, axial breathing, micro-rotation) so even in silence the rings drift organically rather than freezing.
- **Reserve-margin clipping** — ring radii are computed adaptively to the canvas size so they always form complete closed loops, never get cut off at canvas edges.
- **Linear waveform** below the orb — classic oscilloscope view of the same audio.
- **32-segment level meter** in the settings panel, green→yellow→red gradient.

### UI / UX

- **Light "Aurora" theme** with soft surfaces, subtle shadows, indigo/violet/amber state coloring.
- **State machine** drives the orb's color, the status pill, and the ring tint:
  - `setup` → muted gradient, "Tap to start"
  - `listening` → green glow, cyan rings
  - `thinking` → violet pulse
  - `speaking` → amber/orange bloom
- **Responsive mobile layout** — settings panel collapses behind a hamburger drawer with a backdrop blur. Noise-floor pill stays pinned to the bottom of the main view so calibration is always visible.
- **Session token counter** in the top-left, updated after every turn — `total · X in / Y out`.
- **Toast notifications** (cyan for info, rose for error).

---

## Architecture

### Vercel Edge (production)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser                                                             │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  index.html  (static, served from Vercel CDN)                  │  │
│  │  • MediaRecorder (webm/opus)                                   │  │
│  │  • Web Audio analyser + local VAD                              │  │
│  │  • fetch(/api/turn, body=FormData) → ReadableStream reader     │  │
│  │  • Decode WAV chunks → DynamicsCompressor → speakers           │  │
│  └────────────────────┬───────────────────────────────────────────┘  │
└────────────────────── │ ─────────────────────────────────────────────┘
                        ▼
            multipart/form-data
                        │
                        ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Vercel Edge Function   api/turn.ts                                   │
│                                                                       │
│   1. multipart parse                                                  │
│   2. fetch Sarvam STT (REST, audio/webm in, JSON transcript out)      │
│   3. emit  {type:"transcript_final"}                                  │
│   4. OpenAI Chat Completions stream                                   │
│        ├─► detect sentence boundaries                                 │
│        ├─► per sentence: fetch Sarvam TTS (WAV, 24 kHz)               │
│        │                  └─► emit {type:"audio", b64} when ready     │
│        └─► on usage event: emit {type:"usage"}                        │
│   5. emit {type:"done"}                                               │
│                                                                       │
│  Response: application/x-ndjson stream                                │
└───────────────────────────────────────────────────────────────────────┘
```

### Python WebSocket (low-latency local)

```
┌───────────────────────────────────────────────────────────────────────┐
│  Browser                                                              │
│  • AudioWorklet: continuous 16 kHz int16 PCM frames                   │
│  • WebSocket to /ws                                                   │
└────────────────────┬──────────────────────────────────────────────────┘
                     ▼
        binary PCM frames + JSON control
                     │
                     ▼
┌───────────────────────────────────────────────────────────────────────┐
│  FastAPI  main.py    /ws                                              │
│                                                                       │
│   ┌────────────────────────────┐                                      │
│   │ SarvamSTTStream            │ ◄── outbound WebSocket to Sarvam     │
│   │  • PCM forwarded as JSON   │     wss://api.sarvam.ai/             │
│   │    {audio:{data, ...}}     │     speech-to-text/ws                │
│   │  • VAD signals + finals    │                                      │
│   └────────────┬───────────────┘                                      │
│                ▼                                                      │
│  on "data" event (finalized utterance) →                              │
│    same LLM stream + per-sentence TTS pipeline as the Edge version    │
│    → JSON events + binary MP3/WAV frames back over the same WS        │
└───────────────────────────────────────────────────────────────────────┘
```

The Python version achieves true streaming STT (Sarvam emits transcripts as you speak, with a server-side VAD that fires `END_SPEECH` right after you stop). This shaves ~2 seconds off the latency vs. the Vercel REST path.

---

## How it works — full pipeline

A single end-user turn:

1. **User taps the orb** → browser asks for mic permission (once) → Web Audio chain initialised → 1.2 s noise-floor calibration → "Listening".
2. **Local VAD runs at 25 Hz** (40 ms tick). Computes RMS from the analyser node. Reads relative to noise floor:
   - `speechThresh = max(0.012, noiseFloor × SNR)` where SNR is set by the **Sensitivity** slider (1 → 5×, 10 → 1.5×).
   - When 3 consecutive frames cross the threshold (~120 ms of sustained voice), VAD enters "speaking" — `MediaRecorder.start(100)`.
3. **User talks.** MediaRecorder accumulates webm/opus blobs every 100 ms.
4. **User stops.** VAD detects RMS below the silence threshold for *Pause* ms (default 500 ms). Triggers stop:
   - `MediaRecorder.stop()` — emits one final `dataavailable` event.
   - All blobs concatenated → single `Blob('audio/webm')`.
   - Posted as `FormData` to `/api/turn` with `audio`, `language`, `voice`.
5. **Edge function receives the audio**, calls Sarvam STT (`POST /speech-to-text`, model `saaras:v3`), gets back the transcript and detected language.
6. **First NDJSON event emitted:** `{type:"transcript_final", text, language}` — frontend shows the italic transcript under the orb.
7. **OpenAI Chat Completions stream opened** with `stream:true, stream_options:{include_usage:true}`, `gpt-4o-mini`, `max_completion_tokens:80`, temperature 0.4.
8. **As tokens stream in**, server buffers them. The moment a sentence boundary appears (`. ! ? ।`), the sentence is yanked from the buffer and a Sarvam TTS call (`bulbul:v3`, `output_audio_codec:wav`, `speech_sample_rate:24000`, `enable_preprocessing:true`) fires immediately — *without waiting for that call to finish before the next sentence starts*.
9. **TTS results emit in order** via a promise chain — sentence #2's audio waits for sentence #1's audio event to flush, even if its TTS call returned faster.
10. **Each `{type:"audio", idx, text, b64}` event** is received by the browser, base64-decoded into a `Uint8Array`, then `audioCtx.decodeAudioData()` → `AudioBufferSourceNode.start(nextStartTime)`. `nextStartTime` accumulates each buffer's duration, so chunks play perfectly seamless.
11. **The audio is routed through a limiter** (`DynamicsCompressor`) and a master gain (the **Volume** slider in the panel) before reaching `audioCtx.destination`.
12. **`{type:"usage"}` event** fires after the LLM stream completes (it's the last chunk OpenAI sends when `include_usage` is on). Frontend updates the token chip.
13. **`{type:"done"}` event** signals the response stream is complete. Frontend waits for the playback queue to drain.
14. **When the last `AudioBufferSourceNode.onended` fires**, `clearAudio()` resets state, the rings transition back to mic input, and `startLocalVAD()` is called again — ready for the next utterance.

If the user taps the orb during step 9–13, the playback queue is drained, the `fetch` is aborted via `AbortController`, and the agent goes straight back to listening.

---

## Tech stack

| Layer | What | Why |
|---|---|---|
| Frontend | Single `index.html`, no framework | Easy to host as static asset; no build step needed for the UI |
| Audio capture | `MediaRecorder` (webm/opus) | ~16 kbps mono; tiny upload payloads |
| Audio analysis | Web Audio API: `BiquadFilter`, `AnalyserNode`, `DynamicsCompressor`, `AudioBufferSourceNode` | Low-latency level metering, VAD, playback limiting |
| Visualization | `<canvas>` + `requestAnimationFrame` | Rings + waveform driven by `getByteTimeDomainData` |
| STT | Sarvam **Saaras v3** | High accuracy across 11 Indic languages + English |
| LLM | OpenAI **gpt-4o-mini** with streaming | Cheap, fast, supports `stream_options.include_usage` |
| TTS | Sarvam **Bulbul v3** | 39 natural Indic-accent voices, WAV output for cleanest playback |
| Production backend | Vercel **Edge Functions** (TypeScript) | Edge-region distribution, HTTP/2 streaming responses, no cold-start for hot functions |
| Local dev backend | **FastAPI + uvicorn**, optional WebSocket bridge to Sarvam streaming STT | Lowest possible latency for development |
| Typography | Inter + JetBrains Mono | Readable at all sizes; numerals tabular |

---

## Supported languages

| Code | Language | UI label |
|---|---|---|
| `en-IN` | English (Indian accent) | English |
| `hi-IN` | Hindi | Hindi (हिन्दी) |
| `mr-IN` | Marathi | Marathi (मराठी) |
| `ta-IN` | Tamil | Tamil (தமிழ்) |
| `te-IN` | Telugu | Telugu (తెలుగు) |
| `kn-IN` | Kannada | Kannada (ಕನ್ನಡ) |
| `ml-IN` | Malayalam | Malayalam (മലയാളം) |
| `gu-IN` | Gujarati | Gujarati (ગુજરાતી) |
| `bn-IN` | Bengali | Bengali (বাংলা) |
| `pa-IN` | Punjabi | Punjabi (ਪੰਜਾਬੀ) |
| `od-IN` | Odia | Odia (ଓଡ଼ିଆ) |
| `""` (empty) | — | Auto-detect |

When a specific language is selected, both Sarvam STT and the LLM are locked to it; the LLM system prompt includes a hard rule preventing language switching.

---

## Supported voices

All 39 Sarvam Bulbul v3 voices are exposed, grouped by gender. Voice quality varies slightly by language — preview before deciding.

**Male (23):** Shubh (default), Aditya, Rahul, Rohan, Amit, Dev, Ratan, Varun, Manan, Sumit, Kabir, Aayan, Ashutosh, Advait, Anand, Tarun, Sunny, Mani, Gokul, Vijay, Mohit, Rehan, Soham.

**Female (16):** Ritu, Priya, Neha, Pooja, Simran, Kavya, Ishita, Shreya, Roopa, Amelia, Sophia, Tanya, Shruti, Suhani, Kavitha, Rupali.

---

## UI walkthrough

```
Topbar
─────────────────────────────────────────────────────────────
[ logo ]   [ Tokens: 1,044  949 in / 95 out ]   VOICE AGENT · LIVE  [ ☰ ]
                                                                    ^^^^
                                          (live green dot)          (mobile only)

Main stage
─────────────────────────────────────────────────────────────
                Audio-reactive concentric rings
                            ╲
                  ╭───────────╮
                  │   ▌▌▌▌▌   │   ← orb (state-colored)
                  ╰───────────╯
                            /
                  ~~~~~~~~~~~~~~~~      ← linear waveform
                    ────●────────         ← silence countdown bar (during speech)
                ● Thinking…                ← status pill (state-colored)
            "your question here"           ← transcript (italic)

Right panel  (mobile: hamburger drawer)
─────────────────────────────────────────────────────────────
  CONVERSATION
    🌐 Language              [ English ▾ ]
    🎙 Voice                 [ Shubh   ▾ ] [ ▶ Test ]

  AUDIO
    🎚 Sensitivity   5       ━━━━●━━━━━     1 ─ 10
    ⏸ Pause          0.50s   ━━●━━━━━━━     0.3s ─ 2.0s
    🔊 Volume         75%     ━━━━━●━━━━     0% ─ 120%
    📶 Mic Level             ▌▌▌▌▌▌▌▌▌░░░░░░░░░░░░  (live)

  CALIBRATION
    📊 Noise Floor           [ RECAL ]
       floor 0.0030 · trig 0.0120

  💡 Tip — Adjust sensitivity and pause to match your environment.
```

---

## Quick start (Vercel deploy)

### Prerequisites

- A [Sarvam AI](https://dashboard.sarvam.ai) account → API key
- An [OpenAI](https://platform.openai.com/api-keys) account → API key
- A [Vercel](https://vercel.com) account
- Node 18+ and Git locally

### Deploy

```powershell
# 1. Clone
git clone https://github.com/sunilv21/personal-assistance.git
cd personal-assistance

# 2. Install
npm install

# 3. Install Vercel CLI (once, globally)
npm i -g vercel

# 4. Link the local folder to a Vercel project
vercel link

# 5. Set env vars in Vercel (do this in the dashboard OR with CLI)
vercel env add SARVAM_API_KEY production
vercel env add OPENAI_API_KEY production
# Optional:
vercel env add OPENAI_MODEL production              # default: gpt-4o-mini
vercel env add SARVAM_DEFAULT_VOICE production      # default: shubh
vercel env add SARVAM_DEFAULT_LANGUAGE production   # default: en-IN
vercel env add ALLOWED_ORIGIN production            # default: * (lock to your URL)

# 6. Pull them locally for `vercel dev`
vercel env pull .env.local

# 7. Deploy to production
vercel --prod
```

### Verify

```powershell
curl https://YOUR-APP.vercel.app/api/health
# {"ok":true,"sarvam":true,"openai":true,"model":"gpt-4o-mini",...}
```

Open `https://YOUR-APP.vercel.app/` and tap the orb.

### Local Vercel dev

```powershell
vercel dev
# → http://localhost:3000
```

This runs the same TypeScript Edge functions locally — identical behavior to production.

---

## Local development (Python)

The Python backend lives in [`python-backend/`](python-backend/) and mirrors the same HTTP API (`/api/turn`, `/api/voice-preview`, `/api/health`) **plus** a `/ws` endpoint for true low-latency streaming STT.

```powershell
# 1. Move into the backend folder
cd python-backend

# 2. Install deps
pip install -r requirements.txt

# 3. Create .env with your keys (copy from ../.env.example, or use the root .env)
copy ..\.env.example .env
notepad .env

# 4. Run with auto-reload — note the index.html path
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000.

The frontend uses `/api/turn` by default (HTTP), so it works identically to the Vercel deploy. If you want to switch to the lower-latency WebSocket path, the `/ws` endpoint is already there — you'd need a small frontend tweak to route audio via the AudioWorklet PCM streamer (see git history; this code is intact in `sarvam_stream.py` and the WS endpoint in `main.py`).

---

## Environment variables

| Name | Required | Default | Purpose |
|---|---|---|---|
| `SARVAM_API_KEY` | yes | — | Sarvam Saaras (STT) + Bulbul (TTS) auth |
| `OPENAI_API_KEY` | yes | — | Chat Completions auth |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | Any OpenAI chat model that supports streaming |
| `SARVAM_DEFAULT_VOICE` | no | `shubh` | Voice when the user doesn't pick one |
| `SARVAM_DEFAULT_LANGUAGE` | no | `en-IN` | Language fallback |
| `ALLOWED_ORIGIN` | no | `*` | CORS lockdown — set to your Vercel URL in prod |

The Python `config.py` reads from `.env` via `python-dotenv` (with `override=True`, so `.env` always wins over shell env). The Edge functions read `process.env.*` directly from Vercel's env var system.

---

## API reference

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| `GET` | `/` | — | `index.html` | Vercel rewrites this to the static file |
| `GET` | `/api/health` | — | `{ok, sarvam, openai, model, ...}` | Returns 503 if either key is missing |
| `GET` | `/api/voice-preview?voice=X&language=Y` | — | `audio/wav` | Cached `max-age=3600`. Sample text is a localized greeting. |
| `POST` | `/api/turn` | `multipart/form-data` | `application/x-ndjson` stream | See below |
| `POST` | `/voice-agent` | same | same | Alias of `/api/turn` (Python only) |
| `WS` | `/ws` | binary PCM + JSON control | binary WAV + JSON events | Python-only low-latency path |

### `POST /api/turn` form fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `audio` | Blob (`audio/webm`, `audio/mp4`, or `audio/wav`) | yes | Recorded user utterance |
| `language` | string | no | BCP-47 code (e.g. `mr-IN`); empty/missing = Sarvam auto-detect |
| `voice` | string | no | Voice slug (e.g. `shubh`); falls back to `SARVAM_DEFAULT_VOICE` |

### `/api/turn` NDJSON events

Each line of the response is a single JSON object, terminated by `\n`. Events arrive in this order:

```json
{ "type": "transcript_final", "text": "what time is it", "language": "en-IN" }
{ "type": "audio", "idx": 1, "text": "It is half past five.", "b64": "UklGR..." }
{ "type": "audio", "idx": 2, "text": "Do you want me to set a reminder?", "b64": "UklGR..." }
{ "type": "usage", "prompt": 49, "completion": 18, "total": 67 }
{ "type": "done",  "text": "It is half past five. Do you want me to set a reminder?" }
```

On failure:

```json
{ "type": "error", "message": "Sarvam STT 401: ..." }
```

### `WS /ws` (Python only)

Client → server:

```json
{ "type": "start", "language": "mr-IN", "voice": "ritu" }
{ "type": "set_voice", "voice": "neha" }
{ "type": "end_utterance" }            // force-flush pending transcript
{ "type": "stop" }
```

…plus binary frames of raw `pcm_s16le` @ 16 kHz mono.

Server → client (JSON):

```json
{ "type": "ready" }
{ "type": "vad", "signal": "START_SPEECH" }
{ "type": "vad", "signal": "END_SPEECH" }
{ "type": "transcript_partial", "text": "..." }
{ "type": "transcript_final",   "text": "...", "language": "mr-IN" }
{ "type": "audio_start", "idx": 1, "text": "...", "size": 38400 }
{ "type": "audio_end",   "idx": 1 }
{ "type": "usage", "prompt": ..., "completion": ..., "total": ..., "session_total": ... }
{ "type": "done", "text": "..." }
{ "type": "error", "message": "..." }
```

…plus binary WAV chunks (per sentence).

---

## Configuration knobs

All exposed in the right-hand settings panel.

| Knob | Range | Default | What it changes |
|---|---|---|---|
| **Language** | 11 + Auto | English | STT lang code, LLM system-prompt lock, TTS lang code |
| **Voice** | 39 (M/F grouped) | Shubh | TTS speaker |
| **Sensitivity** | 1–10 | 5 | SNR multiplier for VAD `speechThresh = noiseFloor × (5 − (sens−1)·0.389)` — lower = stricter |
| **Pause** | 300–2000 ms | 500 ms | Sustained-silence duration that ends an utterance |
| **Volume** | 10–120% | 75% | Master gain into the limiter |
| **Mic Level** | live | — | Real-time RMS bar |
| **Noise Floor** | live + Recal | calibrated | Floor / trigger threshold in the same units as the meter |

The **Test** button next to Voice plays a short sample of the chosen voice in the chosen language, without disturbing an in-progress conversation.

---

## Project structure

```
.
├── api/                                  # Vercel Edge Functions (TypeScript)
│   ├── turn.ts                            # Main pipeline: STT → LLM stream → per-sentence TTS
│   ├── voice-preview.ts                   # Voice sample generator (WAV)
│   └── health.ts                          # Config sanity check
│
├── index.html                            # Single-file frontend (no build step)
│
├── python-backend/                       # Local dev backend (excluded from Vercel deploy)
│   ├── main.py                            # FastAPI app
│   ├── llm_service.py                     # OpenAI streaming + token usage
│   ├── sarvam_services.py                 # Sarvam STT + TTS REST clients
│   ├── sarvam_stream.py                   # Sarvam streaming STT WebSocket client (for /ws)
│   ├── memory.py                          # In-process chat history (last 6 turns)
│   ├── config.py                          # Loads .env (override=True)
│   └── requirements.txt                   # Python deps
│
├── package.json                          # Node deps (OpenAI SDK + TS)
├── tsconfig.json
├── vercel.json                           # Vercel routing, headers, function timeouts
│
├── .env.example                          # Env var template
├── .gitignore
├── .vercelignore                         # Excludes Python files from Vercel deploys
└── README.md                             # This file
```

---

## Production hardening

The repo ships with the following defaults:

- ✅ **No secrets in code** — everything via env vars
- ✅ **CORS configurable** via `ALLOWED_ORIGIN` (default `*`, set to your domain in prod)
- ✅ **Security headers** in `vercel.json`:
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: microphone=(self)`
- ✅ `Cache-Control: no-store` on `/api/turn` and `/api/health`
- ✅ `Cache-Control: public, max-age=3600, immutable` on `/api/voice-preview`
- ✅ Per-function timeouts: 60 s turn, 30 s preview, 10 s health
- ✅ Graceful 500 with structured JSON when env vars missing
- ✅ Mic permission denial handled with a toast, no crash
- ✅ Tap-to-interrupt aborts in-flight fetch + drains playback queue
- ✅ Audio limiter cannot clip even on loud TTS output
- ✅ Local VAD adapts to noisy environments via noise-floor calibration

### Rate limiting (recommended for public deploys)

`/api/turn` is the expensive endpoint — each request calls Sarvam STT, OpenAI Chat Completions (streaming), and N × Sarvam TTS (one per sentence). For a public-facing deploy, put a rate limiter in front of it:

- **Vercel WAF** rules (built-in, dashboard)
- **Upstash Ratelimit** (Edge-compatible, free tier)

A sensible starting cap: **30 requests / minute / IP**.

---

## Limitations

- **Vercel Edge can't open outbound WebSocket** connections. The production deploy uses Sarvam's REST STT (batch per utterance), not their streaming WebSocket. This trades ~2 s of latency for "everything on Vercel" simplicity. Use the Python backend (or deploy it on Railway / Fly / Render) if you need the lowest possible latency.
- **No memory across page reloads.** `memory.py` is in-process; refresh = fresh conversation. Add Redis / Upstash / Vercel KV if persistence matters.
- **Single concurrent conversation** on the Python WS path (memory is shared). The Edge path is naturally per-request, so fine.
- **MediaRecorder browser quirks** — Safari supports `audio/mp4`, others prefer `audio/webm;codecs=opus`. The code probes both.
- **Sarvam audio max** — Bulbul v3 has a ~2500 char limit per TTS call. We chunk by sentence, so this is rarely hit.

---

## Cost model

Rough per-turn cost (en-IN, 5-second user utterance, ~50-word reply):

| Item | Provider | Approx. cost |
|---|---|---|
| 1 × STT (Saaras v3) | Sarvam | ~$0.0005 per minute |
| 1 × LLM stream (gpt-4o-mini, ~150 in / ~80 out tokens) | OpenAI | ~$0.00007 |
| 2–4 × TTS (Bulbul v3, ~80 chars each) | Sarvam | ~$0.002 per minute of speech |
| Vercel Edge invocation | Vercel | free tier covers ~100k turns/month |

Effectively **fractions of a cent per turn**. The token chip in the UI tracks live OpenAI usage. Sarvam usage is visible in their dashboard.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Mic denied — please allow and reload` | Browser → site settings → Microphone → Allow → reload page. |
| `Cannot connect to server` | Backend not running (Python) or env vars missing (Vercel). Check `curl /api/health`. |
| 404 on `/api/turn` (Python local) | Restart uvicorn — Python doesn't auto-reload without `--reload`. |
| Voice preview returns 502 | Bad `SARVAM_API_KEY`. Check `/api/health`. |
| First request very slow (~8 s) | Edge function cold start on Vercel. Stays warm after the first call. |
| Agent cuts you off mid-sentence | Increase **Pause** (0.8 – 1.2 s). |
| Mic triggers on background noise | Lower **Sensitivity** (2–3), click **Recal**. |
| Audio sounds harsh / distorted | Lower **Volume** to 50–70%. Limiter prevents *clipping* but extra headroom is gentler on small speakers. |
| Rings cut off at edges | Window very narrow — they adapt to canvas size, but extreme sizes can clip. Resize. |
| Token chip never updates | `stream_options.include_usage` not supported by the model. Switch to gpt-4o-mini or any `gpt-4o*`. |

---

## Roadmap

Things that would make this production-grade for many users:

- [ ] **Persistent conversation history** (Vercel KV / Upstash / Redis) — survive page reload
- [ ] **Streaming STT on Vercel** via a third-party WS proxy (e.g., Cloudflare Workers as a relay)
- [ ] **Multi-turn context window** beyond 6 messages with semantic compression
- [ ] **Wake-word** ("Hey Sarvam") to skip the initial tap
- [ ] **Custom voices** via Sarvam voice-cloning
- [ ] **Server-sent events** for typing indicators / interim transcripts on the Edge path
- [ ] **Function calling** so the assistant can do things (timers, web search, calendar)
- [ ] **Visitor analytics** (PostHog) — track latency P50/P95, language mix, voice usage
- [ ] **Tests** — unit tests for the VAD and the NDJSON parser, e2e tests via Playwright

---

## License

Personal / educational use. If you want to fork or build on top of this, open an issue first.

Built by [@sunilv21](https://github.com/sunilv21).
