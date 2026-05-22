// GET /api/health → 200 OK with config sanity check (no secrets leaked)
export const config = { runtime: "edge" };

export default async function handler(_req: Request) {
    const hasSarvam = !!process.env.SARVAM_API_KEY;
    const hasOpenAI = !!process.env.OPENAI_API_KEY;
    const ok = hasSarvam && hasOpenAI;
    return new Response(
        JSON.stringify({
            ok,
            sarvam: hasSarvam,
            openai: hasOpenAI,
            model: process.env.OPENAI_MODEL || "gpt-4o-mini",
            defaultVoice: process.env.SARVAM_DEFAULT_VOICE || "shubh",
            defaultLanguage: process.env.SARVAM_DEFAULT_LANGUAGE || "en-IN",
        }),
        {
            status: ok ? 200 : 503,
            headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
        },
    );
}
