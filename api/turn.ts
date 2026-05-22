// POST /api/turn
//   multipart/form-data with: audio (Blob), language?, voice?
//   Returns: application/x-ndjson stream with events:
//     {type:"transcript_final", text, language}
//     {type:"audio", idx, text, b64}        // WAV (base64)
//     {type:"usage", prompt, completion, total}
//     {type:"done", text}                     // full LLM text
//     {type:"error", message}
//
// Vercel Edge runtime — bidirectional fetch streaming, no WebSocket.

import OpenAI from "openai";

export const config = {
    runtime: "edge",
    maxDuration: 60,
};

const SARVAM = "https://api.sarvam.ai";

const LANG_NAMES: Record<string, string> = {
    "mr-IN": "Marathi", "hi-IN": "Hindi", "en-IN": "English",
    "ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada",
    "ml-IN": "Malayalam", "gu-IN": "Gujarati", "bn-IN": "Bengali",
    "pa-IN": "Punjabi", "od-IN": "Odia",
};

const SYSTEM_PROMPT = `You are a fast voice assistant. CRITICAL RULES:
- Reply in the SAME language as user (Marathi/Hindi/English).
- Maximum 1-2 sentences. Be ultra-concise like Alexa.
- No lists, no bullets, no markdown. Just natural speech.
- If greeted, greet back in ONE short sentence.`;

const SENTENCE_END = /([.!?।]+['"\)\]]?)(\s+|$)/;

function corsHeaders(req: Request) {
    const allow = process.env.ALLOWED_ORIGIN || "*";
    const origin = req.headers.get("origin") || "";
    const value = allow === "*" ? "*" : (origin === allow ? origin : allow);
    return {
        "Access-Control-Allow-Origin": value,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
    };
}

function bufToBase64(buf: ArrayBuffer | Uint8Array): string {
    const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    let s = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
        s += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk) as unknown as number[]);
    }
    return btoa(s);
}

function base64ToBytes(b64: string): Uint8Array {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
}

async function sarvamSTT(audio: Blob, filename: string, language: string | null) {
    const fd = new FormData();
    fd.append("file", audio, filename);
    fd.append("model", "saaras:v3");
    let langCode = language || "unknown";
    if (langCode !== "unknown" && !langCode.includes("-")) langCode = `${langCode}-IN`;
    fd.append("language_code", langCode);
    const res = await fetch(`${SARVAM}/speech-to-text`, {
        method: "POST",
        headers: { "api-subscription-key": process.env.SARVAM_API_KEY! },
        body: fd,
    });
    if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(`Sarvam STT ${res.status}: ${txt.slice(0, 160)}`);
    }
    const data = await res.json();
    return {
        transcript: (data.transcript || "").trim() as string,
        language: (data.language_code || language || "en-IN") as string,
    };
}

async function sarvamTTS(text: string, language: string, voice: string): Promise<Uint8Array | null> {
    const lang = language.includes("-") ? language : `${language}-IN`;
    const res = await fetch(`${SARVAM}/text-to-speech`, {
        method: "POST",
        headers: {
            "api-subscription-key": process.env.SARVAM_API_KEY!,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            text,
            target_language_code: lang,
            model: "bulbul:v3",
            speaker: voice.toLowerCase(),
            output_audio_codec: "wav",
            speech_sample_rate: "24000",
            enable_preprocessing: true,
        }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.audios?.[0]) return null;
    return base64ToBytes(data.audios[0]);
}

export default async function handler(req: Request) {
    if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders(req) });
    if (req.method !== "POST") {
        return new Response(JSON.stringify({ error: "Method not allowed" }), {
            status: 405,
            headers: { "Content-Type": "application/json", ...corsHeaders(req) },
        });
    }

    if (!process.env.SARVAM_API_KEY || !process.env.OPENAI_API_KEY) {
        return new Response(JSON.stringify({ error: "Server missing SARVAM_API_KEY or OPENAI_API_KEY" }), {
            status: 500,
            headers: { "Content-Type": "application/json", ...corsHeaders(req) },
        });
    }

    let form: FormData;
    try {
        form = await req.formData();
    } catch {
        return new Response(JSON.stringify({ error: "Bad form data" }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders(req) },
        });
    }
    const audio = form.get("audio");
    if (!(audio instanceof Blob)) {
        return new Response(JSON.stringify({ error: "audio required" }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders(req) },
        });
    }
    const language = (form.get("language") as string) || null;
    const voice = ((form.get("voice") as string) || process.env.SARVAM_DEFAULT_VOICE || "shubh").toLowerCase();
    const filename = (audio as File).name || "audio.webm";

    // 1) STT (blocking — quick, ~1s)
    let stt: { transcript: string; language: string };
    try {
        stt = await sarvamSTT(audio, filename, language);
    } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return new Response(JSON.stringify({ error: msg }), {
            status: 502,
            headers: { "Content-Type": "application/json", ...corsHeaders(req) },
        });
    }

    if (!stt.transcript) {
        return new Response(null, { status: 204, headers: corsHeaders(req) });
    }

    const outLanguage = language || stt.language || "en-IN";
    const langName = LANG_NAMES[outLanguage] || outLanguage;

    // 2) Stream LLM + per-sentence TTS as NDJSON
    const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
            const enc = new TextEncoder();
            const send = (obj: unknown) => controller.enqueue(enc.encode(JSON.stringify(obj) + "\n"));

            try {
                send({ type: "transcript_final", text: stt.transcript, language: outLanguage });

                const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
                const systemContent = `${SYSTEM_PROMPT}\n- LANGUAGE LOCK: reply ONLY in ${langName}. Never switch languages, no matter what the user says.`;

                const llmStream = await openai.chat.completions.create({
                    model: process.env.OPENAI_MODEL || "gpt-4o-mini",
                    messages: [
                        { role: "system", content: systemContent },
                        { role: "user", content: stt.transcript },
                    ],
                    temperature: 0.4,
                    max_completion_tokens: 80,
                    stream: true,
                    stream_options: { include_usage: true },
                });

                let buf = "";
                let fullText = "";
                let idx = 0;
                // Run TTS calls in PARALLEL but emit their audio events in ORDER.
                // Each sentence's emit awaits the previous emit's completion.
                let emitChain: Promise<void> = Promise.resolve();

                const flushSentence = (sentence: string) => {
                    const text = sentence.trim();
                    if (!text) return;
                    const myIdx = ++idx;
                    // Kick TTS immediately — runs concurrently with siblings
                    const ttsResult = sarvamTTS(text, outLanguage, voice);
                    // Chain emit: wait for prior emit + own TTS, then send
                    emitChain = emitChain.then(async () => {
                        const audio = await ttsResult;
                        if (audio) {
                            send({ type: "audio", idx: myIdx, text, b64: bufToBase64(audio) });
                        }
                    });
                };

                for await (const event of llmStream) {
                    const delta = event.choices?.[0]?.delta?.content;
                    if (delta) {
                        buf += delta;
                        fullText += delta;
                        while (true) {
                            const m = buf.match(SENTENCE_END);
                            if (!m || m.index === undefined) break;
                            const end = m.index + m[0].length;
                            const sentence = buf.slice(0, end);
                            buf = buf.slice(end);
                            flushSentence(sentence);
                        }
                    }
                    if (event.usage) {
                        send({
                            type: "usage",
                            prompt: event.usage.prompt_tokens,
                            completion: event.usage.completion_tokens,
                            total: event.usage.total_tokens,
                        });
                    }
                }
                if (buf.trim()) flushSentence(buf);
                // Drain all chained emits before sending done
                await emitChain;

                send({ type: "done", text: fullText });
            } catch (e: unknown) {
                const msg = e instanceof Error ? e.message : String(e);
                send({ type: "error", message: msg });
            } finally {
                controller.close();
            }
        },
    });

    return new Response(stream, {
        headers: {
            "Content-Type": "application/x-ndjson; charset=utf-8",
            "Cache-Control": "no-store",
            ...corsHeaders(req),
        },
    });
}
