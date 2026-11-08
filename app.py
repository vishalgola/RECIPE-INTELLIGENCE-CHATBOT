"""Streamlit UI for the Recipe Intelligence Chatbot.   Run:  streamlit run app.py

The UI is a thin layer: every fact comes from src.chat.Bot (retrieval + Python calculations).
The LLM (Gemini or Groq, set in .env) only helps to understand the message and, optionally, to
re-word the final answer; re-worded answers are verified against the original (numbers and recipe IDs)."""
import os
import re
import streamlit as st

from src import llm_handler
from src.chat import Bot
from src.index import load_index

DATA_DIR = os.getenv("DATA_DIR", "data")
EXAMPLES = [
    "Find a penne pasta recipe.",
    "I cannot have dairy.",
    "Show only recipes containing tomato.",
    "Show the first one",
    "How many recipes contain both garlic and onion? What percentage of the dataset is that?",
    "Among recipes containing tomato, which five have the fewest instruction steps?",
    "I have eggs, onions, tomatoes, and rice. Suggest five recipes with no peanuts and at most six steps. Prefer recipes that need the fewest additional ingredients.",
    "Exclude eggs too",
    "Take this banana bread recipe and remove eggs.",
    "Replace cream in this pasta recipe without dairy.",
    "How many calories does the first one have?",
]

st.set_page_config(page_title="Recipe Intelligence Chatbot", page_icon="🍳", layout="wide")


# ---------------------------------------------------------------- data (loaded once per server process)
@st.cache_resource(show_spinner=False)
def get_index(data_dir: str):
    return load_index(data_dir)


try:
    with st.spinner("Loading dataset (the first run builds a cache and can take a few minutes)..."):
        index = get_index(DATA_DIR)
except FileNotFoundError as exc:
    st.error(f"Dataset not found: {exc}\n\nPut the three recipes_raw_nosource_*.json files in the `{DATA_DIR}/` folder.")
    st.stop()
except Exception as exc:  # corrupt cache, out of memory, ...
    st.error(f"Could not load the dataset: {exc}")
    st.stop()

# ---------------------------------------------------------------- per-session conversation memory
if "bot" not in st.session_state:
    st.session_state.bot = Bot(index, use_llm=False)   # Bot keeps: dish, include/exclude, max steps, have, active recipe
    st.session_state.messages = []                     # chat history shown in the UI
bot: Bot = st.session_state.bot


def llm_rewrite(text: str) -> str:
    """Optional: let the LLM re-word the system answer. Rejected if it adds a number or drops/adds a recipe ID."""
    prompt = ("Rewrite the SYSTEM OUTPUT below as a clear, friendly answer for the user. Rules: use ONLY facts, numbers and "
              "recipe IDs that appear in it; keep every recipe ID exactly as written; do not add recipes, quantities, times, "
              "calories or advice; keep warnings and labels such as NOT AVAILABLE, VIOLATES, NO MATCH, WEAK, STRONG. "
              "Plain text only.\n\nSYSTEM OUTPUT:\n" + text)
    out = llm_handler._call(prompt)
    if not out:
        return text
    numbers = lambda t: set(re.findall(r"\d+(?:\.\d+)?", t))
    ids = lambda t: set(re.findall(r"\b(?:ar|epi|fn):[^\s\]\),;]+", t))
    return out if numbers(out) <= numbers(text) and ids(out) == ids(text) else text


def card_ids(reply: str):
    """Recipes to show as cards = recipes of the latest result list / selected recipe that the reply actually mentions."""
    cand = list(bot.st["last"]) + ([bot.st["active"]] if bot.st["active"] is not None else [])
    seen, out = set(), []
    for i in cand:
        rid = bot.ix.recipes[i].id
        if i not in seen and rid in reply:
            seen.add(i)
            out.append(rid)
    return out


def render_cards(ids):
    for rid in ids:
        r = index.recipes[index.pos[rid]]
        with st.expander(f"[{r.id}]  {r.title}  -  {len(r.ingredients)} ingredients, {len(r.steps)} steps"):
            left, right = st.columns(2)
            left.markdown("**Ingredients**")
            left.text("\n".join(f"- {line}" for line in r.ingredients))
            right.markdown("**Instructions**")
            right.text("\n".join(f"{n}. {s}" for n, s in enumerate(r.steps, 1)))
            st.caption(f"Source file: {r.source} | ID: {r.id} (original record preserved)")


def render_message(msg):
    if msg["role"] == "user":
        st.text(msg["content"])
        return
    st.text(msg["content"])
    if msg.get("original"):
        st.caption("Re-worded by the LLM; numbers and recipe IDs verified against the system output.")
        with st.expander("Original system output"):
            st.text(msg["original"])
    render_cards(msg.get("cards", []))


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🍳 Recipe Chatbot")
    st.subheader("Dataset")
    st.metric("Recipes loaded", f"{index.N:,}")
    st.caption(f"Recipe Box (eightportions.com), all 3 JSON files. {index.skipped:,} records skipped (no title or ingredients).")

    st.subheader("LLM")
    provider = llm_handler.provider()
    has_key = bool(os.getenv("GROQ_API_KEY") if provider == "groq" else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")))
    if st.button("Test API connection", use_container_width=True):
        with st.spinner("Contacting the LLM..."):
            st.session_state.llm_status = llm_handler.status()
    status = st.session_state.get("llm_status")
    if status is None:
        (st.info if has_key else st.warning)(f"Provider: **{provider}** - " + ("key found, not tested yet." if has_key else "no API key in .env. Rule-based mode works without it."))
    elif status[0]:
        st.success(status[1])
    else:
        st.warning(f"{status[1]}\n\nRule-based mode still works.")
    bot.use_llm = st.checkbox("Use LLM to understand messages", value=has_key, key="use_llm")
    use_rewrite = st.checkbox("Re-word answers with LLM (verified)", value=False, key="rewrite")

    st.subheader("Conversation memory")
    memory_box = st.empty()

    c1, c2 = st.columns(2)
    if c1.button("New Chat", use_container_width=True, help="Clears the chat AND the remembered restrictions"):
        bot.reset()
        st.session_state.messages = []
        st.rerun()
    if c2.button("Clear Chat", use_container_width=True, help="Clears the messages only; restrictions stay remembered"):
        st.session_state.messages = []
        st.rerun()

    st.subheader("Try these")
    for example in EXAMPLES:
        if st.button(example, key=f"ex_{example}", use_container_width=True):
            st.session_state.pending = example


def render_memory():
    s = bot.st
    active = index.recipes[s["active"]].id if s["active"] is not None else "-"
    with memory_box.container():
        st.markdown(
            f"- **Task:** {s['mode'] or '-'}\n- **Dish / query:** {s['dish'] or '-'}\n"
            f"- **Must contain:** {', '.join(s['include']) or '-'}\n- **Excluded:** {', '.join(s['exclude']) or '-'}\n"
            f"- **Max steps:** {s['max_steps'] or '-'}\n- **Ingredients on hand:** {', '.join(s['have']) or '-'}\n"
            f"- **Selected recipe:** {active}")


# ---------------------------------------------------------------- main chat area
st.header("Recipe Intelligence Chatbot")
st.caption("Search recipes, ask dataset statistics, match what is in your kitchen, or adapt a recipe. "
           "Counts and rankings are computed in Python over the full filtered dataset, never guessed by an LLM.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        render_message(message)

typed = st.chat_input("Ask about recipes, e.g. 'Find a penne pasta recipe'")
prompt = typed or st.session_state.pop("pending", None)

if prompt:
    user_msg = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_msg)
    with st.chat_message("user"):
        render_message(user_msg)
    with st.chat_message("assistant"):
        with st.spinner("Searching the dataset..."):
            try:
                reply = bot.reply(prompt)
                bot_msg = {"role": "assistant", "content": reply, "cards": card_ids(reply)}
                if use_rewrite:
                    worded = llm_rewrite(reply)
                    if worded != reply:
                        bot_msg.update(content=worded, original=reply)
            except Exception as exc:  # never crash the chat on a bad query
                bot_msg = {"role": "assistant", "cards": [], "content": f"Sorry, something went wrong while handling that ({type(exc).__name__}: {exc}). "
                                                                       "Try rephrasing, or click New Chat."}
        render_message(bot_msg)
    st.session_state.messages.append(bot_msg)

render_memory()
