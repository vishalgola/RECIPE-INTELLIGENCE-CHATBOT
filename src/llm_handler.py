"""One interface for Gemini or Groq, chosen in .env. The LLM only parses intents / rephrases; it never computes facts."""
import json, os
from dotenv import load_dotenv
load_dotenv()

LAST_ERROR = ""
SCHEMA = """Return ONLY JSON with keys: task (search|stats|match|substitute|show), dish (string, dish name words only),
include (list of ingredients that must be present), exclude (list of ingredients/allergens/diets to avoid),
allow (restrictions the user now lifts), max_steps (int|null), reset (bool), stat (count|common|avg|rank|null),
title_words (list), scope_active (bool: refers to 'those'/'these' recipes), top_n (int), order (asc|desc),
have (list of ingredients on hand, keep quantities), prefer (fewest_missing|fewest_steps|null), k (int),
ref (recipe id like ar:xyz, or ordinal '1'..'5', or null), remove (ingredients to remove/replace)."""


def provider():
    return os.getenv("LLM_PROVIDER", "groq").strip().lower()


def _gemini(prompt, json_mode):
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    from google import genai
    cfg = {"temperature": 0}
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    r = genai.Client(api_key=key).models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), contents=prompt, config=cfg)
    return r.text


def _groq(prompt, json_mode):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    from groq import Groq
    kw = dict(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0,
              messages=[{"role": "user", "content": prompt}])
    if json_mode:
        kw["response_format"] = {"type": "json_object"}   # prompt must contain the word JSON (SCHEMA does)
    return Groq(api_key=key).chat.completions.create(**kw).choices[0].message.content


def _call(prompt, json_mode=False):
    global LAST_ERROR
    fn = {"gemini": _gemini, "groq": _groq}.get(provider())
    if fn is None:
        LAST_ERROR = f"Unknown LLM_PROVIDER '{provider()}' (use gemini or groq)"
        return None
    try:
        return fn(prompt, json_mode)
    except Exception as e:                      # network/quota/model errors must never crash the chat
        LAST_ERROR = str(e)
        return None


def status():
    """(ok, message) for the sidebar 'API connection status'."""
    out = _call("Reply with the single word OK")
    return (True, f"{provider()} connected") if out else (False, LAST_ERROR or f"no API key set for {provider()}")


def parse_intent(msg, state_summary):
    out = _call(f"{SCHEMA}\nConversation state: {state_summary}\nUser message: {msg}", json_mode=True)
    if not out:
        return None
    try:
        return json.loads(out.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        return None


def one_shot(question):
    """Baseline for eval: LLM with NO retrieval (expected to be ungrounded)."""
    return _call(question)