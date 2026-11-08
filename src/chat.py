"""Conversation manager + CLI. All facts in replies come from retrieved records or Python calculations."""
import argparse, re
from . import analytics, matcher, substitution, llm_handler as llm
from .constraints import resolve, Restriction
from .rule_parser import Intent, parse_rules, detect_unsupported
from .index import load_index
from .normalization import term_tokens, strict_match

HELP = """Try:
  Find a penne pasta recipe.            then:  I cannot have dairy.
  How many recipes contain both garlic and onion? What percentage of the dataset is that?
  Among recipes containing tomato, which five have the fewest instruction steps?
  I have eggs, onions, tomatoes, and rice. Suggest five recipes with no peanuts and at most six steps.  then: Exclude eggs too.
  Take this banana bread recipe and remove eggs.     /  Replace cream in this pasta recipe without dairy.
  How many calories does the first one have?   (the dataset has no nutrition data - the bot will say so)
  show the second one   |   reset   |   quit"""

UNS_LABEL = {"nutrition": "nutrition values (calories, protein, carbs, fat, ...)", "time": "cooking / prep / total time",
             "servings": "serving counts", "cost": "cost or price", "rating": "ratings, reviews, popularity or difficulty"}
TIME_RE = re.compile(r"\b\d+(?:\.\d+)?(?:\s*(?:to|-|or)\s*\d+(?:\.\d+)?)?\s*(?:seconds?|minutes?|mins?|hours?|hrs?)\b", re.I)


class Bot:
    def __init__(self, index, use_llm=True):
        self.ix = index
        self.use_llm = use_llm
        self.reset()

    def reset(self):
        self.st = dict(dish="", include=[], exclude=[], max_steps=None, last=[], active=None, have=[], mode=None)

    # ---------- helpers ----------
    def _restrictions(self, terms=None):
        out = []
        for t in (self.st["exclude"] if terms is None else terms):
            out += resolve(t)
        return out

    def _summary(self):
        s = self.st
        return f"dish={s['dish']!r} include={s['include']} exclude={s['exclude']} max_steps={s['max_steps']} have={s['have']} mode={s['mode']}"

    def _parse(self, msg):
        rule = parse_rules(msg)
        if rule.task != "search" or rule.reset:      # rules recognised a specific task: trust them, not the LLM
            return rule
        if self.use_llm:
            d = llm.parse_intent(msg, self._summary())
            if d:
                try:
                    return Intent.from_dict(d)
                except Exception:
                    pass
        return parse_rules(msg)

    def _resolve_ref(self, ref):
        if ref is None:
            return self.st["active"]
        if ref in self.ix.pos:
            return self.ix.pos[ref]
        if ref.isdigit() and 1 <= int(ref) <= len(self.st["last"]):
            return self.st["last"][int(ref) - 1]
        return None

    def fmt(self, i, full=False, rs=(), tokens=()):
        r = self.ix.recipes[i]
        head = f"[{r.id}] {r.title}  ({len(r.ingredients)} ingredients, {len(r.steps)} steps)"
        if full:
            marker = any("ADVERTISEMENT" in l for l in r.ingredients_raw)
            return (head + ("\n  (scrape marker 'ADVERTISEMENT' hidden in display; the original lines are kept unchanged in the data)" if marker else "")
                    + "\n  Ingredients:\n" + "\n".join(f"    - {l}" for l in r.ingredients) + "\n  Instructions:\n" + "\n".join(f"    {n}. {s}" for n, s in enumerate(r.steps, 1)))
        rel = [l for l, s in zip(r.ingredients, r.sets) if any(t <= s for t in tokens)] or r.ingredients[:4]
        out = head + "\n  Relevant ingredients: " + "; ".join(rel[:6])
        for x in rs:
            hits = x.hit_lines(r.ingredients, r.sets)
            out += f"\n  Check '{x.label}': " + ("VIOLATION -> " + "; ".join(hits) if hits else f"none of the {len(r.ingredients)} ingredient lines matched the {x.label} word list (text screening only, not a safety guarantee)")
        return out

    # ---------- attributes the dataset does not have ----------
    def _unsupported_note(self, kinds, i=None):
        what = "; ".join(UNS_LABEL[k] for k in kinds)
        out = (f"NOT AVAILABLE IN THE DATASET: {what}.\n"
               "Recipe Box records contain only a title, ingredient lines and instruction text. I will not guess or estimate these values, "
               "and I have not filtered or ranked by them.")
        if "time" in kinds:
            out += " Step count is available, but it is not a measure of time."
            if i is not None:
                r = self.ix.recipes[i]
                hits = [f"    step {n}: {s[:160]}" for n, s in enumerate(r.steps, 1) if TIME_RE.search(s)][:4]
                if hits:
                    out += (f"\n  Durations that appear in the instruction text of [{r.id}] {r.title} "
                            "(quoted steps, not a verified total time):\n" + "\n".join(hits))
        return out

    # ---------- main entry ----------
    def reply(self, msg):
        it = self._parse(msg)
        if it.reset:
            self.reset()
            if not it.dish and it.task == "search":
                return "Okay - cleared the active search and restrictions."
        if it.allow:
            low = [a.lower() for a in it.allow]
            self.st["exclude"] = [e for e in self.st["exclude"] if not any(a in e.lower() or e.lower() in a for a in low)]
        note, uns = "", detect_unsupported(msg)
        if uns:
            pure = it.task in ("search", "show") and not (it.dish.strip() or it.include or it.exclude or it.have or it.remove)
            i = self._resolve_ref(it.ref) if it.ref else self.st["active"]
            note = self._unsupported_note(uns, i)
            if pure:
                return note
        h = {"search": self._search, "stats": self._stats, "match": self._match, "substitute": self._substitute, "show": self._show}
        if it.task == "search" and self.st["mode"] == "match" and not it.dish and not it.include and (it.exclude or it.max_steps):
            it.task = "match"                       # 'Exclude eggs too' after a matching request
        out = h.get(it.task, self._search)(it)
        return note + "\n\n" + out if note else out

    # ---------- Task 1: search ----------
    def _search(self, it):
        s = self.st
        for e in it.exclude:
            if e not in s["exclude"]:
                s["exclude"].append(e)
        if it.dish:
            s.update(dish=it.dish, include=list(it.include), max_steps=it.max_steps)
        else:
            s["include"] += [x for x in it.include if x not in s["include"]]
            if it.max_steps:
                s["max_steps"] = it.max_steps
        if not (s["dish"] or s["include"]):
            return f"Noted. Restrictions so far: exclude [{', '.join(s['exclude']) or '-'}]. Now tell me a dish or ingredient to search for."
        s["mode"] = "search"
        rs = self._restrictions()
        allowed = self.ix.filter(s["include"], rs, s["max_steps"])
        top, n = self.ix.search(s["dish"], allowed if (s["include"] or rs or s["max_steps"]) else None, k=5)
        s["last"] = [i for i, _ in top]
        s["active"] = s["last"][0] if s["last"] else None
        hdr = f"Active search: dish='{s['dish'] or '-'}' | must contain: {', '.join(s['include']) or '-'} | exclude: {', '.join(s['exclude']) or '-'} | max steps: {s['max_steps'] or '-'}"
        if not top:
            return hdr + "\nNo recipe in the dataset matches all of these. I did not relax any restriction. Try removing one filter (e.g. 'reset')."
        toks = [term_tokens(w) for w in (s["dish"].split() + s["include"])]
        body = "\n".join(f"{n_}. " + self.fmt(i, rs=rs, tokens=toks) for n_, (i, _) in enumerate(top, 1))
        return (f"{hdr}\n{n} of {self.ix.N} recipes satisfy the filters; top {len(top)} by TF-IDF relevance (title+ingredients):\n{body}\n"
                "Say 'show the first one' for full ingredients and instructions.")

    def _show(self, it):
        i = self._resolve_ref(it.ref)
        if i is None:
            return "Which recipe? Give an ID (e.g. ar:xxxx) or run a search first."
        self.st["active"] = i
        return self.fmt(i, full=True)

    # ---------- Task 1: analytics ----------
    def _stats(self, it):
        s = self.st
        include, tw = list(it.include), list(it.title_words)
        rs = []
        if it.scope_active:
            include = s["include"] + include
            tw = tw or s["dish"].split()
            rs = self._restrictions()
        ex = rs + self._restrictions(it.exclude)
        if it.stat == "count" and include:
            r = analytics.count(self.ix, include, tw, ex)
            lines = [f"Filters: {r['filters']}", f"Result: {r['n']} recipes out of {r['N']} analysed = {r['pct']:.2f}% of the dataset.",
                     f"Calculation: {r['method']}", analytics.NORMALIZATION_NOTE]
            for t, e in r["examples"].items():
                lines.append(f"Examples matched for '{t}': " + ("; ".join(e) or "none"))
            return "\n".join(lines)
        if it.stat == "common":
            r = analytics.common(self.ix, include, tw, ex, 10)
            return f"Filters: {r['filters']}\nRecipes analysed: {r['n']}\nMost common ingredients (recipes containing each):\n" + "\n".join(f"  {k}: {v}" for k, v in r["top"]) + f"\nCalculation: {r['method']}"
        if it.stat == "avg":
            r = analytics.ingredient_counts(self.ix, include, tw, ex)
            if not r["n"]:
                return f"Filters: {r['filters']}\nNo recipes match."
            return f"Filters: {r['filters']}\nRecipes analysed: {r['n']}\nMean ingredients: {r['mean']:.2f} | Median: {r['median']} | Min: {r['min']} | Max: {r['max']}\nCalculation: {r['method']}"
        if it.stat == "rank":
            r = analytics.rank_steps(self.ix, include, tw, ex, it.top_n, it.order)
            rows = "\n".join(f"  {n}. [{self.ix.recipes[i].id}] {self.ix.recipes[i].title} - {len(self.ix.recipes[i].steps)} steps" for n, i in enumerate(r["rows"], 1))
            self.st["last"] = r["rows"]
            return f"Filters: {r['filters']}\nRecipes analysed: {r['n']}\n{'Fewest' if it.order == 'asc' else 'Most'} instruction steps:\n{rows}\nCalculation: {r['method']}"
        return "I can count recipes ('how many recipes contain X and Y'), list common ingredients, give mean/median ingredient counts, or rank by step count. Please name an ingredient filter for counts."

    # ---------- Task 2 ----------
    def _match(self, it):
        s = self.st
        if it.have:
            s["have"] = it.have
            s["exclude"] = list(it.exclude)
            s["max_steps"] = it.max_steps
            s["prefer"] = it.prefer
        else:
            for e in it.exclude:
                if e not in s["exclude"]:
                    s["exclude"].append(e)
                s["have"] = [h for h in s["have"] if term_tokens(e) != term_tokens(h)]
            if it.max_steps:
                s["max_steps"] = it.max_steps
            it.prefer = it.prefer or s.get("prefer")
        s["mode"] = "match"
        if not s["have"]:
            return "No ingredients left on your list. Tell me what you have ('I have ...')."
        rs = self._restrictions()
        res = matcher.match(self.ix, s["have"], rs, s["max_steps"], it.prefer or s.get("prefer"), it.k)
        s["last"] = [r["idx"] for r in res["results"]]
        s["active"] = s["last"][0] if s["last"] else None
        wu, wc = res["weights"]
        out = [f"Ingredients on hand: {', '.join(h.name for h in res['haves'])}",
               f"Hard constraints: exclude [{', '.join(s['exclude']) or '-'}]; max steps: {s['max_steps'] or '-'}. Water and salt are assumed available (not counted).",
               f"Ranking: sorted by how many of your ingredients the recipe uses (most first), then fewer missing ingredients, then fewer steps; score = {wu}*usage + {wc}*coverage is shown for transparency; usage = share of your ingredients the recipe uses; coverage = share of the recipe's required ingredients you have. Ties -> fewer missing ingredients, then fewer steps. Matching is name-level (e.g. garlic powder != garlic).",
               f"{res['n_candidates']} recipes use at least one of your ingredients; {res['n_eligible']} pass the hard constraints."]
        if not res["results"]:
            out.append("NO MATCH FOUND that satisfies all hard constraints.")
            if res["alternatives"]:
                out.append("Closest alternatives that VIOLATE a constraint (shown only for reference; allergen/exclusion violations are never offered):")
                out += [self._fmt_match(r, k + 1) for k, r in enumerate(res["alternatives"])]
            return "\n".join(out)
        out += [self._fmt_match(r, k + 1) for k, r in enumerate(res["results"])]
        return "\n".join(out)

    def _fmt_match(self, r, n):
        t = f"{n}. [{r['id']}] {r['title']}  score={r['score']:.2f} (usage {r['n_used']}/{len(self.st['have'])}, coverage {r['n_taken']}/{r['n_req']}), {r['steps']} steps"
        if r.get("violates"):
            t += f"\n   !! VIOLATES: {r['violates']}"
        t += "\n   Matched: " + "; ".join(f"{h} -> '{l}' [qty: {q}]" for h, l, q in r["matched"])
        t += "\n   Not used from your list: " + (", ".join(r["unused"]) or "-")
        t += "\n   Missing / extra required: " + ("; ".join(r["missing"][:8]) + (" ..." if len(r["missing"]) > 8 else "") if r["missing"] else "none")
        return t

    # ---------- Task 3 ----------
    def _substitute(self, it):
        s = self.st
        i = None
        if it.ref:
            i = self._resolve_ref(it.ref)
        if i is None and it.dish:
            pool = self.ix.filter(list(it.remove)) or None      # only recipes that really contain the ingredient
            top, _ = self.ix.search(it.dish, pool, k=1)
            if top:
                i = top[0][0]
                note = f"(No recipe ID given - using best title match for '{it.dish}'.)\n"
            else:
                return f"No recipe found for '{it.dish}'."
        elif i is None:
            i = s["active"]
        if i is None:
            return "Which recipe should I adapt? Search first or give an ID."
        if not it.remove:
            return "What should I remove or replace (e.g. 'remove eggs', 'replace cream without dairy')?"
        note = locals().get("note", "")
        s["active"], s["mode"] = i, "substitute"
        remove = self._restrictions(it.remove)
        keep = self._restrictions(it.exclude + s["exclude"])
        res = substitution.propose(self.ix, i, remove, keep)
        r = res["recipe"]
        if not res["plan"]:
            return f"{note}[{r.id}] {r.title}: none of its {len(r.ingredients)} ingredient lines match '{', '.join(it.remove)}', so nothing to substitute."
        ad = substitution.build_adaptation(res)
        out = [f"{note}Recipe: [{r.id}] {r.title}", f"Request: remove {', '.join(it.remove)}; also respecting: {', '.join(it.exclude + s['exclude']) or '-'}"]
        ev_seen = set()
        for p in res["plan"]:
            if p["key"] is None or p["key"] in ev_seen:
                continue
            ev_seen.add(p["key"])
            ev = p["ev"]
            out.append(f"\nEvidence for replacing '{p['key']}' (role: {substitution.CAND[p['key']]['role']}):")
            out.append(f"  Compared against {ev['n_comparable']} similar local recipes that do not use '{p['key']}' (TF-IDF similarity on title + other ingredients).")
            if not ev["options"]:
                out.append("  No allowed substitute with presence in the dataset - cannot propose a reliable adaptation.")
            for o in ev["options"][:4]:
                ids = ", ".join(o["support"][:4]) or "none"
                out.append(f"  - {o['sub']['tok']}: used in {len(o['support'])} of those recipes (e.g. {ids}); appears in {o['global_count']} recipes overall")
            st = substitution.strength(ev)
            msg = {"strong": "STRONG local evidence for the top option.", "weak": "WEAK local evidence (few supporting recipes) - treat as a guess.",
                   "conflicting": "CONFLICTING/ambiguous: several substitutes are about equally common, no clear winner.",
                   "none": "NO direct local evidence; any suggestion is indirect/external and unverified."}[st]
            out.append("  Evidence strength: " + msg)
        out.append("\nUpdated ingredient list:\n" + "\n".join(f"  - {l}" for l in ad["ingredients"]))
        out.append("\nRevised instructions:" + ("".join(f"\n  Prep: {p}" for p in ad["prep"])) + "\n" + "\n".join(f"  {n}. {t}" for n, t in enumerate(ad["steps"], 1)))
        if ad["effects"]:
            out.append("\nExpected effects (PREDICTIONS from general cooking knowledge, not verified by the dataset; amounts/ratios are external rules of thumb):\n" + "\n".join(f"  - {e}" for e in ad["effects"]))
        if res["notes"]:
            out.append("\nWarnings:\n" + "\n".join(f"  - {n}" for n in res["notes"]))
        out.append("\nThis is a text-based adaptation, not medical/allergy advice. For allergies, verify every product label.")
        return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--no-llm", action="store_true", help="rule-based intent parsing only")
    a = ap.parse_args()
    print("Loading index (first run builds a cache, can take a few minutes)...")
    bot = Bot(load_index(a.data), use_llm=not a.no_llm)
    print(f"Loaded {bot.ix.N} recipes ({bot.ix.skipped} records without title/ingredients skipped).\n{HELP}")
    while True:
        try:
            msg = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in ("quit", "exit"):
            break
        if msg.lower() in ("help", "?"):
            print(HELP)
        elif msg:
            print("\nbot>", bot.reply(msg))


if __name__ == "__main__":
    main()
