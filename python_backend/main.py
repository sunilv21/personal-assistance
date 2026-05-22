from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, FileResponse, StreamingResponse
from .sarvam_services import sarvam_stt, sarvam_tts
from .sarvam_stream import SarvamSTTStream
from .llm_service import generate_response, stream_response
from .memory import add_to_memory, get_memory
from .config import settings
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os, sys, time, json, base64, re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = FastAPI()

_key = settings.SARVAM_API_KEY or ""
print(f"[STARTUP] Key: {_key[:8]}...{_key[-4:]} | LLM: {settings.OPENAI_MODEL}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.get("/")
async def serve_ui():
    # index.html lives at project root (one level above python_backend/).
    path = os.path.join(_PROJECT_ROOT, "index.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return Response(content="index.html not found", status_code=404)


@app.get("/favicon.svg")
async def favicon_svg():
    path = os.path.join(_PROJECT_ROOT, "favicon.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml")
    return Response(status_code=404)


@app.get("/favicon.png")
async def favicon_png():
    path = os.path.join(_PROJECT_ROOT, "favicon.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png")
    return Response(status_code=404)


@app.get("/favicon.ico")
async def favicon_ico():
    # Browsers ask for favicon.ico by reflex — redirect to the SVG.
    return FileResponse(os.path.join(_PROJECT_ROOT, "favicon.svg"), media_type="image/svg+xml")


# ── Voice preview — short sample MP3 so the user can audition a voice ──
PREVIEW_SAMPLES = {
    "en-IN": "Hello! I am your voice assistant. I can help you with questions, ideas, and more.",
    "hi-IN": "नमस्ते! मैं आपका वॉइस असिस्टेंट हूँ। आप जो भी पूछना चाहें, मैं मदद के लिए तैयार हूँ।",
    "mr-IN": "नमस्कार! मी तुमचा व्हॉइस असिस्टंट आहे. तुम्हाला हवी असलेली मदत मी आनंदाने करेन.",
    "ta-IN": "வணக்கம்! நான் உங்கள் குரல் உதவியாளர். உங்களுக்கு எப்படி உதவலாம் என்று சொல்லுங்கள்.",
    "te-IN": "నమస్కారం! నేను మీ వాయిస్ అసిస్టెంట్‌ని. మీకు ఎలా సహాయం చేయగలను?",
    "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ ಧ್ವನಿ ಸಹಾಯಕ. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ ಎಂದು ತಿಳಿಸಿ.",
    "ml-IN": "നമസ്കാരം! ഞാൻ നിങ്ങളുടെ വോയ്സ് അസിസ്റ്റന്റ് ആണ്. എങ്ങനെ സഹായിക്കാം?",
    "gu-IN": "નમસ્તે! હું તમારો વોઇસ આસિસ્ટન્ટ છું. હું તમારી શું મદદ કરી શકું?",
    "bn-IN": "নমস্কার! আমি আপনার ভয়েস অ্যাসিস্ট্যান্ট। আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    "pa-IN": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਤੁਹਾਡਾ ਵੌਇਸ ਅਸਿਸਟੈਂਟ ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    "od-IN": "ନମସ୍କାର! ମୁଁ ଆପଣଙ୍କ ଭଏସ୍ ସହାୟକ। ମୁଁ କିପରି ସାହାଯ୍ୟ କରିପାରେ?",
}

@app.get("/voice-preview")
@app.get("/api/voice-preview")
async def voice_preview(voice: str = "shubh", language: str = "en-IN"):
    lang = language if "-" in language else f"{language}-IN"
    text = PREVIEW_SAMPLES.get(lang, PREVIEW_SAMPLES["en-IN"])
    audio = sarvam_tts(text, lang, voice.strip().lower())
    if not audio:
        return Response(content=b"", status_code=502)
    return Response(content=audio, media_type="audio/wav")


@app.get("/api/health")
async def health():
    return {
        "ok": bool(settings.SARVAM_API_KEY and settings.OPENAI_API_KEY),
        "sarvam": bool(settings.SARVAM_API_KEY),
        "openai": bool(settings.OPENAI_API_KEY),
        "model": settings.OPENAI_MODEL,
    }

# ── Wake word check — lightweight STT, returns {wake: true/false} ──
WAKE_WORDS = ['hello sarvam','hey sarvam','hi sarvam','hello servam','hey servam',
              'हेलो सरवम','हे सरवम','hello sarvan','hey sarvan','hello servant','hey servant']

@app.post("/wake-check")
async def wake_check(audio: UploadFile = File(...), language: str | None = Form(None)):
    t0 = time.time()
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.wav"

    transcript, language, confidence = sarvam_stt(audio_bytes, filename, language)

    if not transcript:
        return {"wake": False, "text": ""}

    text_lower = transcript.lower().strip()
    found = any(w in text_lower for w in WAKE_WORDS)
    print(f"[WAKE] \"{transcript}\" → {'✅ WAKE' if found else '—'} ({time.time()-t0:.1f}s)")
    return {"wake": found, "text": transcript}


SENTENCE_END = re.compile(r"([\.!\?।]+['\"\)\]]?)(\s+|$)")

def _ndjson(event: dict) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


@app.post("/voice-agent")
@app.post("/api/turn")
async def turn(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    voice: str | None = Form(None),
):
    """Streaming pipeline mirroring the Vercel Edge function shape:
      STT (blocking) → LLM stream → per-sentence TTS → NDJSON events.
    Events: transcript_final, audio, usage, done, error.
    """
    t0 = time.time()
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.wav"

    transcript, detected_language, _ = sarvam_stt(audio_bytes, filename, language)
    if not transcript:
        print(f"[AGENT] No transcript ({time.time()-t0:.1f}s)")
        return Response(content=b"", status_code=204)

    out_language = language or detected_language
    selected_voice = (voice or "").strip().lower() or None
    print(f"[AGENT] \"{transcript}\" (lang={out_language}, voice={selected_voice or 'default'})")

    def stream_pipeline():
        yield _ndjson({"type": "transcript_final", "text": transcript, "language": out_language})
        add_to_memory("user", transcript)

        full_text = ""
        buf = ""
        sentence_idx = 0

        def flush_sentence(sentence: str):
            nonlocal sentence_idx
            sentence = sentence.strip()
            if not sentence:
                return None
            audio_out = sarvam_tts(sentence, out_language, selected_voice)
            if not audio_out:
                return None
            sentence_idx += 1
            return _ndjson({
                "type": "audio",
                "idx": sentence_idx,
                "text": sentence,
                "b64": base64.b64encode(audio_out).decode("ascii"),
            })

        try:
            for ev in stream_response(transcript, get_memory(), out_language):
                kind = ev.get("kind")
                if kind == "token":
                    buf += ev["text"]
                    full_text += ev["text"]
                    while True:
                        m = SENTENCE_END.search(buf)
                        if not m:
                            break
                        sentence = buf[:m.end()]
                        buf = buf[m.end():]
                        chunk = flush_sentence(sentence)
                        if chunk:
                            yield chunk
                elif kind == "usage":
                    yield _ndjson({
                        "type": "usage",
                        "prompt": ev["prompt_tokens"],
                        "completion": ev["completion_tokens"],
                        "total": ev["total_tokens"],
                    })

            if buf.strip():
                chunk = flush_sentence(buf)
                if chunk:
                    yield chunk

            add_to_memory("assistant", full_text)
            print(f"[AGENT] ✅ done in {time.time()-t0:.1f}s ({sentence_idx} chunks)")
            yield _ndjson({"type": "done", "text": full_text})
        except Exception as e:
            print(f"[AGENT] stream error: {e}")
            yield _ndjson({"type": "error", "message": str(e)})

    return StreamingResponse(stream_pipeline(), media_type="application/x-ndjson")


# ════════════════════════════════════════════════════════════════════
#  WebSocket live-streaming pipeline
#    browser PCM 16kHz int16 LE  →  Sarvam streaming STT
#    Sarvam END_SPEECH           →  LLM stream  →  per-sentence TTS
#    MP3 frames + JSON events    →  browser (queued playback)
# ════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    language: str | None = None
    voice: str | None = None       # current TTS voice (None → server default)
    stt: SarvamSTTStream | None = None
    turn_in_progress = False
    pending_transcript = ""        # latest interim transcript from Sarvam
    final_transcript_event = asyncio.Event()
    locked_transcript = ""         # transcript at moment of END_SPEECH

    async def send_json(obj: dict):
        try:
            await websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    async def send_bin(b: bytes):
        try:
            await websocket.send_bytes(b)
        except Exception:
            pass

    async def run_turn():
        """Triggered after END_SPEECH. Runs LLM stream + TTS chunks back to browser."""
        nonlocal turn_in_progress, locked_transcript
        if turn_in_progress or not locked_transcript.strip():
            return
        turn_in_progress = True
        transcript = locked_transcript.strip()
        out_language = language or "mr-IN"
        print(f"[WS] turn → \"{transcript}\" ({out_language})")

        await send_json({"type": "transcript_final", "text": transcript, "language": out_language})
        add_to_memory("user", transcript)

        full_text = ""
        buf = ""
        idx = 0
        try:
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()
            def producer():
                try:
                    for ev in stream_response(transcript, get_memory(), out_language):
                        loop.call_soon_threadsafe(queue.put_nowait, ev)
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, {"kind": "err", "message": str(e)})
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, {"kind": "end"})
            asyncio.create_task(asyncio.to_thread(producer))

            async def flush_sentence(text: str):
                nonlocal idx
                text = text.strip()
                if not text:
                    return
                audio_bytes = await asyncio.to_thread(sarvam_tts, text, out_language, voice)
                if not audio_bytes:
                    return
                idx += 1
                await send_json({"type": "audio_start", "idx": idx, "text": text, "size": len(audio_bytes)})
                await send_bin(audio_bytes)
                await send_json({"type": "audio_end", "idx": idx})

            while True:
                ev = await queue.get()
                kind = ev.get("kind")
                if kind == "token":
                    buf += ev["text"]
                    full_text += ev["text"]
                    while True:
                        m = SENTENCE_END.search(buf)
                        if not m:
                            break
                        sentence = buf[:m.end()]
                        buf = buf[m.end():]
                        await flush_sentence(sentence)
                elif kind == "usage":
                    session_tokens["prompt"] += ev["prompt_tokens"]
                    session_tokens["completion"] += ev["completion_tokens"]
                    session_tokens["total"] += ev["total_tokens"]
                    await send_json({
                        "type": "usage",
                        "prompt": ev["prompt_tokens"],
                        "completion": ev["completion_tokens"],
                        "total": ev["total_tokens"],
                        "session_prompt": session_tokens["prompt"],
                        "session_completion": session_tokens["completion"],
                        "session_total": session_tokens["total"],
                    })
                    print(f"[LLM] usage: turn={ev['total_tokens']} session={session_tokens['total']}")
                elif kind == "err":
                    await send_json({"type": "error", "message": ev["message"]})
                    break
                else:  # end
                    break
            if buf.strip():
                await flush_sentence(buf)
            add_to_memory("assistant", full_text)
            await send_json({"type": "done", "text": full_text})
            print(f"[WS] turn done ({idx} chunks)")
        finally:
            # Reset transcript state so the next utterance can start cleanly
            locked_transcript_local_reset()

    def locked_transcript_local_reset():
        nonlocal turn_in_progress, locked_transcript, pending_transcript
        turn_in_progress = False
        locked_transcript = ""
        pending_transcript = ""

    async def stt_event_loop():
        nonlocal pending_transcript, locked_transcript
        while stt is not None:
            ev = await stt.next_event()
            if ev is None or ev["kind"] == "closed":
                break
            if ev["kind"] == "transcript":
                # Sarvam's 'data' event is emitted after VAD detects end of an utterance,
                # so each transcript IS a complete final. Trigger the turn immediately.
                text = ev["text"]
                pending_transcript = text
                await send_json({"type": "transcript_partial", "text": text})
                if not turn_in_progress and text.strip():
                    locked_transcript = text
                    asyncio.create_task(run_turn())
            elif ev["kind"] == "vad":
                sig = ev["signal"]
                await send_json({"type": "vad", "signal": sig})
            elif ev["kind"] == "error":
                await send_json({"type": "error", "message": ev.get("message", "")})

    stt_task: asyncio.Task | None = None
    pcm_bytes_total = 0
    session_tokens = {"prompt": 0, "completion": 0, "total": 0}
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            # Binary frame = raw PCM int16 16kHz LE from browser
            if "bytes" in msg and msg["bytes"] is not None:
                pcm_bytes_total += len(msg["bytes"])
                if stt is not None:
                    await stt.send_pcm(msg["bytes"])
                # Log periodically: ~1 line per second of audio
                if pcm_bytes_total // 32000 != (pcm_bytes_total - len(msg["bytes"])) // 32000:
                    print(f"[WS] browser→server: {pcm_bytes_total} bytes ({pcm_bytes_total/32000:.1f}s of audio)")
                continue
            # Text frame = JSON control message
            text = msg.get("text")
            if not text:
                continue
            try:
                ctl = json.loads(text)
            except Exception:
                continue
            ctype = ctl.get("type")
            print(f"[WS] ctl: {ctype}")
            if ctype == "start":
                # Open Sarvam streaming STT for this session
                language = ctl.get("language") or None
                voice = (ctl.get("voice") or "").strip().lower() or None
                if stt is None:
                    stt = SarvamSTTStream(language=language)
                    try:
                        await stt.connect()
                    except Exception as e:
                        err = f"sarvam connect failed: {type(e).__name__}: {e}"
                        print(f"[WS] {err}")
                        await send_json({"type": "error", "message": err})
                        stt = None
                        continue
                    stt_task = asyncio.create_task(stt_event_loop())
                    await send_json({"type": "ready", "voice": voice})
            elif ctype == "set_voice":
                v = (ctl.get("voice") or "").strip().lower() or None
                voice = v
                print(f"[WS] voice → {voice or '(default)'}")
            elif ctype == "flush":
                if stt is not None:
                    await stt.flush()
            elif ctype == "end_utterance":
                # Client-side VAD says user is done. Flush Sarvam, brief grace period
                # for the final transcript, then trigger the LLM turn.
                if stt is not None and not turn_in_progress and pending_transcript.strip():
                    await stt.flush()
                    await asyncio.sleep(0.2)
                    locked_transcript = pending_transcript
                    if locked_transcript.strip():
                        asyncio.create_task(run_turn())
            elif ctype == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] error: {e}")
    finally:
        if stt is not None:
            await stt.close()
        if stt_task is not None:
            stt_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
        print("[WS] closed")
