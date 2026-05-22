"""
Sarvam streaming STT WebSocket client.

Connects to wss://api.sarvam.ai/speech-to-text/ws and exposes:
  - send_pcm(pcm_int16_bytes)         → forwards a PCM frame (16kHz, mono, int16-LE)
  - flush()                           → forces finalization of in-flight transcript
  - close()                           → closes the upstream WS
  - async iterator → yields events: {"type": "vad"|"transcript"|"error", ...}

Protocol (from docs.sarvam.ai AsyncAPI):
  client→server: {"audio": {"data": <b64 pcm>, "sample_rate": "16000", "encoding": "audio/wav"}}
                 {"type": "flush"}
  server→client: {"type": "data", "data": {"transcript": "...", "language_code": "..."}}
                 {"type": "events", "data": {"signal_type": "START_SPEECH"|"END_SPEECH", ...}}
                 {"type": "error", "data": {"error": "...", "code": "..."}}
"""
import asyncio
import base64
import json
import time
from urllib.parse import urlencode

import websockets

from config import settings

SARVAM_WS_URL = "wss://api.sarvam.ai/speech-to-text/ws"


class SarvamSTTStream:
    def __init__(self, language: str | None = None):
        self.language = language
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._closed = False

    async def connect(self):
        params = {
            "model": "saaras:v3",
            "input_audio_codec": "pcm_s16le",
            "sample_rate": "16000",
            "vad_signals": "true",
        }
        if self.language:
            lang = self.language if "-" in self.language else f"{self.language}-IN"
            params["language-code"] = lang
        url = f"{SARVAM_WS_URL}?{urlencode(params)}"
        headers = [("Api-Subscription-Key", settings.SARVAM_API_KEY or "")]
        print(f"[STT-WS] connecting → {url}")
        try:
            self.ws = await websockets.connect(url, additional_headers=headers, max_size=8 * 1024 * 1024)
        except Exception as e:
            print(f"[STT-WS] ✗ connect failed: {type(e).__name__}: {e}")
            raise
        print(f"[STT-WS] ✓ connected (lang={params.get('language-code','auto')})")
        self._tasks.append(asyncio.create_task(self._sender()))
        self._tasks.append(asyncio.create_task(self._receiver()))

    async def _sender(self):
        n = 0
        try:
            while not self._closed:
                msg = await self._send_queue.get()
                if msg is None:
                    break
                await self.ws.send(msg)
                n += 1
                if n == 1 or n % 50 == 0:
                    print(f"[STT-WS] → sent {n} audio frames")
        except Exception as e:
            print(f"[STT-WS] sender error ({n} sent): {type(e).__name__}: {e}")

    async def _receiver(self):
        print("[STT-WS] receiver listening")
        n = 0
        try:
            async for raw in self.ws:
                n += 1
                preview = raw if isinstance(raw, str) else "<binary>"
                print(f"[STT-WS] ← #{n} {preview[:300]}")
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mtype = msg.get("type")
                data = msg.get("data") or {}
                if mtype == "data":
                    text = (data.get("transcript") or "").strip()
                    if text:
                        await self._event_queue.put({
                            "kind": "transcript",
                            "text": text,
                            "language": data.get("language_code"),
                        })
                elif mtype == "events":
                    sig = data.get("signal_type")
                    if sig in ("START_SPEECH", "END_SPEECH"):
                        await self._event_queue.put({"kind": "vad", "signal": sig})
                elif mtype == "error":
                    await self._event_queue.put({"kind": "error", "message": data.get("error", "unknown")})
        except websockets.ConnectionClosed as e:
            print(f"[STT-WS] connection closed: code={e.code} reason={e.reason}")
        except Exception as e:
            print(f"[STT-WS] receiver error: {type(e).__name__}: {e}")
        finally:
            print(f"[STT-WS] receiver done ({n} messages)")
            await self._event_queue.put({"kind": "closed"})

    async def send_pcm(self, pcm_bytes: bytes):
        if self._closed:
            return
        b64 = base64.b64encode(pcm_bytes).decode("ascii")
        payload = json.dumps({
            "audio": {"data": b64, "sample_rate": "16000", "encoding": "audio/wav"}
        })
        await self._send_queue.put(payload)

    async def flush(self):
        if self._closed:
            return
        await self._send_queue.put(json.dumps({"type": "flush"}))

    async def next_event(self, timeout: float | None = None):
        if timeout is None:
            return await self._event_queue.get()
        try:
            return await asyncio.wait_for(self._event_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def close(self):
        if self._closed:
            return
        self._closed = True
        await self._send_queue.put(None)
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        for t in self._tasks:
            t.cancel()
