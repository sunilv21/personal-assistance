from openai import OpenAI
from .config import settings
import time

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a fast voice assistant. CRITICAL RULES:
- Reply in the SAME language as user (Marathi/Hindi/English)
- Maximum 1-2 sentences. Be ultra-concise like Alexa.
- No lists, no bullets, no markdown. Just natural speech.
- If greeted, greet back in ONE short sentence."""

LANG_NAMES = {
    "mr-IN": "Marathi", "hi-IN": "Hindi", "en-IN": "English",
    "ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada",
    "ml-IN": "Malayalam", "gu-IN": "Gujarati", "bn-IN": "Bengali",
    "pa-IN": "Punjabi", "od-IN": "Odia",
}

def generate_response(user_input, memory, language=None):
    t0 = time.time()
    system_content = SYSTEM_PROMPT
    if language:
        code = language if "-" in language else f"{language}-IN"
        name = LANG_NAMES.get(code, code)
        system_content += f"\n- LANGUAGE LOCK: reply ONLY in {name}. Never switch languages, no matter what the user says."
    messages = [{"role": "system", "content": system_content}]
    messages.extend(memory[-6:])  # only last 3 turns for speed
    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        # temperature omitted — gpt-5 reasoning models only accept default
        max_completion_tokens=200,  # higher cap because gpt-5-nano uses some for reasoning
    )

    text = response.choices[0].message.content
    print(f"[LLM] {time.time()-t0:.2f}s → {text}")
    return text


def stream_response(user_input, memory, language=None):
    """Yield dicts: {"kind":"token","text":...} for content deltas and
    {"kind":"usage","prompt_tokens":...,"completion_tokens":...,"total_tokens":...} at end."""
    t0 = time.time()
    system_content = SYSTEM_PROMPT
    if language:
        code = language if "-" in language else f"{language}-IN"
        name = LANG_NAMES.get(code, code)
        system_content += f"\n- LANGUAGE LOCK: reply ONLY in {name}. Never switch languages, no matter what the user says."
    messages = [{"role": "system", "content": system_content}]
    messages.extend(memory[-6:])
    messages.append({"role": "user", "content": user_input})

    stream = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        # temperature omitted — gpt-5 reasoning models only accept default
        max_completion_tokens=200,  # higher cap because gpt-5-nano uses some for reasoning
        stream=True,
        stream_options={"include_usage": True},
    )
    first = True
    for event in stream:
        if event.choices:
            delta = event.choices[0].delta.content
            if delta:
                if first:
                    print(f"[LLM] first token in {time.time()-t0:.2f}s")
                    first = False
                yield {"kind": "token", "text": delta}
        usage = getattr(event, "usage", None)
        if usage is not None:
            yield {
                "kind": "usage",
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
    print(f"[LLM] stream done in {time.time()-t0:.2f}s")
