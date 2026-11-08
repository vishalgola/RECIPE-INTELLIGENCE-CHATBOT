"""Reproducible evaluation: python evaluation/run_eval.py --data data [--baseline]
Runs eval_set.json against the real dataset, checks invariants independently of the bot, and writes
  evaluation/transcripts.md  (full conversations)   and   evaluation/results.md  (PASS/FAIL table + baseline comparison).
Baselines for 'why not just ask an LLM / grep?':
  * naive substring count (always runs, no key needed)  - shows how an ungrounded method over-counts
  * one-shot LLM answer without retrieval (--baseline, needs an API key in .env) - compared to the computed truth"""
import argparse, json, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.index import load_index
from src.chat import Bot
from src.constraints import resolve
from src.normalization import term_tokens, strict_match
from src import analytics, llm_handler as llm

ap = argparse.ArgumentParser(); ap.add_argument("--data", default="data"); ap.add_argument("--baseline", action="store_true")
a = ap.parse_args()
ix = load_index(a.data)
here = Path(__file__).parent
cases = json.load(open(here / "eval_set.json"))
log, results = [], {}


def ids_in(text):
    return re.findall(r"\[((?:ar|epi|fn):[^\]]+)\]", text)


for c in cases:
    bot = Bot(ix, use_llm=False)
    replies = [bot.reply(t) for t in c["turns"]]
    log.append(f"## {c['id']}\n" + "\n".join(f"**you:** {t}\n\n```\n{r}\n```" for t, r in zip(c["turns"], replies)))
    last, ok, why = replies[-1], True, ""
    if c["id"] == "T1-followup-dairy":
        dairy = resolve("dairy")[0]
        bad = [i for i in ids_in(last) if i in ix.pos and dairy.hits_any(ix.recipes[ix.pos[i]].sets)]
        ok, why = not bad and (len(ids_in(last)) > 0 or "No recipe" in last), f"dairy hits: {bad}"
    elif c["id"] == "T1-aggregate":
        t1, t2 = term_tokens("garlic"), term_tokens("onion")
        brute = sum(1 for r in ix.recipes if any(strict_match(t1, s) for s in r.sets) and any(strict_match(t2, s) for s in r.sets))
        ok, why = f"{brute} recipes out of {ix.N}" in last, f"brute-force={brute}"
    elif c["id"] == "T1-rank-steps":
        st = [int(x) for x in re.findall(r"- (\d+) steps", last)]
        ok, why = bool(st) and st == sorted(st), f"steps={st}"
    elif c["id"] == "T1-unsupported-nutrition":
        ok = all("NOT AVAILABLE IN THE DATASET" in r for r in replies[1:]) and not re.search(r"\b\d+\s*(kcal|calories)\b", " ".join(replies[1:]), re.I)
        why = "both follow-ups refused; no invented numbers" if ok else "fabrication risk"
    elif c["id"] == "T2-match-followup":
        ids = ids_in(last)
        eggs = resolve("egg")[0]
        ok = all(len(ix.recipes[ix.pos[i]].steps) <= 6 and not eggs.hits_any(ix.recipes[ix.pos[i]].sets) for i in ids if i in ix.pos) and replies[0] != replies[1]
        top_usage = int(re.search(r"usage (\d+)/", last).group(1)) if "usage " in last else 0
        ok, why = ok and top_usage >= 2, f"{len(ids)} ids; top result uses {top_usage} of your ingredients"
    elif c["id"] == "T2-no-match":
        ok, why = "NO MATCH" in last, ""
    elif c["id"] == "T3-no-vetted-substitute":
        ok = "No vetted substitute" in last or "nothing to substitute" in last
        why = "refused to invent a substitute" if ok else "check reply"
    elif c["id"] in ("T3-weak-evidence", "T3-dairy-cream"):
        ok = "Evidence strength" in last or "nothing to substitute" in last
        why = "evidence label present" if ok else "missing evidence label"
        if c["id"] == "T3-dairy-cream":
            ok = "Evidence strength" in last and "yogurt" not in last.split("Updated ingredient list")[-1].split("Revised")[0]
    results[c["id"]] = (ok, why)

# ---- baselines on the aggregate question ----
t1, t2 = term_tokens("garlic"), term_tokens("onion")
truth = analytics.count(ix, ["garlic", "onion"])
naive = sum(1 for r in ix.recipes if "garlic" in " ".join(r.ingredients).lower() and "onion" in " ".join(r.ingredients).lower())
base = [f"## Baselines for: 'How many recipes contain both garlic and onion?'",
        f"- **System (normalised, strict forms):** {truth['n']} of {truth['N']} ({truth['pct']:.2f}%)",
        f"- **Naive substring grep ('garlic' and 'onion' anywhere in the ingredient text):** {naive} - over-counts by {naive - truth['n']} because it also matches garlic powder/salt, onion powder, green onions, etc."]
if a.baseline:
    q = "How many recipes in the Recipe Box dataset (eightportions.com, 3 JSON files) contain both garlic and onion? Give one single number as your best estimate; do not refuse."
    ans = llm.one_shot(q)
    base.append(f"- **One-shot {llm.provider()} (no retrieval, forced to estimate):** {ans if ans else '(no API key set in .env - run with a key and paste the answer here)'}")
else:
    base.append("- **One-shot LLM:** not run (use --baseline with an API key in .env; paste its answer here to show it is ungrounded).")
log.append("\n".join(base))

(here / "transcripts.md").write_text("# Eval transcripts\n\n" + "\n\n".join(log), encoding="utf-8")
table = ["# Eval results", "", f"Dataset: {ix.N} recipes loaded ({ix.skipped} records skipped: no title/ingredients).", "",
         "| case | result | note |", "|---|---|---|"] + [f"| {k} | {'PASS' if ok else 'FAIL'} | {why} |" for k, (ok, why) in results.items()] + ["", "\n".join(base)]
(here / "results.md").write_text("\n".join(table), encoding="utf-8")
for k, (ok, why) in results.items():
    print(("PASS" if ok else "FAIL"), k, why)
print("\n".join(base))
print("Transcripts written to evaluation/transcripts.md, summary to evaluation/results.md")
