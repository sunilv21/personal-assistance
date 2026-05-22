// GET /api/voice-preview?voice=<name>&language=<bcp47>
// Returns a short WAV sample of the requested voice in the requested language.

export const config = {
    runtime: "edge",
    maxDuration: 30,
};

const SARVAM = "https://api.sarvam.ai";

const PREVIEW_SAMPLES: Record<string, string> = {
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
};

function corsHeaders(req: Request) {
    const allow = process.env.ALLOWED_ORIGIN || "*";
    const origin = req.headers.get("origin") || "";
    const value = allow === "*" ? "*" : (origin === allow ? origin : allow);
    return {
        "Access-Control-Allow-Origin": value,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    };
}

export default async function handler(req: Request) {
    if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders(req) });
    if (req.method !== "GET") {
        return new Response("Method not allowed", { status: 405, headers: corsHeaders(req) });
    }
    if (!process.env.SARVAM_API_KEY) {
        return new Response("Server missing SARVAM_API_KEY", { status: 500, headers: corsHeaders(req) });
    }

    const url = new URL(req.url);
    const voiceRaw = (url.searchParams.get("voice") || process.env.SARVAM_DEFAULT_VOICE || "shubh").trim().toLowerCase();
    const langRaw = url.searchParams.get("language") || process.env.SARVAM_DEFAULT_LANGUAGE || "en-IN";
    const lang = langRaw.includes("-") ? langRaw : `${langRaw}-IN`;
    const text = PREVIEW_SAMPLES[lang] || PREVIEW_SAMPLES["en-IN"];

    const res = await fetch(`${SARVAM}/text-to-speech`, {
        method: "POST",
        headers: {
            "api-subscription-key": process.env.SARVAM_API_KEY,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            text,
            target_language_code: lang,
            model: "bulbul:v3",
            speaker: voiceRaw,
            output_audio_codec: "wav",
            speech_sample_rate: "24000",
            enable_preprocessing: true,
        }),
    });
    if (!res.ok) {
        return new Response("TTS failed", { status: 502, headers: corsHeaders(req) });
    }
    const data = await res.json();
    if (!data.audios?.[0]) {
        return new Response("No audio returned", { status: 502, headers: corsHeaders(req) });
    }
    const bin = atob(data.audios[0]);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);

    return new Response(buf, {
        headers: {
            "Content-Type": "audio/wav",
            "Cache-Control": "public, max-age=3600, immutable",
            ...corsHeaders(req),
        },
    });
}
