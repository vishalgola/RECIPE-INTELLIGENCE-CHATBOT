"""All statistics are computed in Python over the COMPLETE filtered set - never by an LLM."""
import statistics
from collections import Counter
from .normalization import term_tokens, strict_match

NORMALIZATION_NOTE = ("Ingredient lines are normalised (lowercased, quantities/units/prep words such as 'chopped' removed, "
                      "plurals singularised, a few true synonyms merged). A term counts only if all its words are in the "
                      "line AND the line is not a different product form (garlic powder/salt != garlic; green onion != onion; "
                      "tomato paste/sauce/juice != tomato).")


def describe_filters(include, title_words, exclude):
    parts = []
    if include:
        parts.append("ingredients contain: " + " AND ".join(include))
    if title_words:
        parts.append("title contains: " + " ".join(title_words))
    if exclude:
        parts.append("excluding: " + ", ".join(r.label for r in exclude))
    return "; ".join(parts) or "none (whole dataset)"


def _examples(index, idxs, term, n=3):
    toks, out = term_tokens(term), []
    for i in idxs:
        r = index.recipes[i]
        for line, s in zip(r.ingredients, r.sets):
            if strict_match(toks, s):
                out.append(f"'{line}' [{r.id}]")
                break
        if len(out) >= n:
            break
    return out


def count(index, include, title_words=(), exclude=()):
    sub = index.filter(include, exclude, None, title_words)
    n, N = len(sub), index.N
    return {"kind": "count", "n": n, "N": N, "pct": 100 * n / N if N else 0.0, "ids": sub,
            "filters": describe_filters(include, title_words, exclude),
            "method": f"count = number of recipes whose ingredient lines match every term; percentage = count / {N} (all recipes loaded from the three files, duplicates across files NOT removed) x 100.",
            "examples": {t: _examples(index, sub, t) for t in include}}


def common(index, include=(), title_words=(), exclude=(), top_n=10):
    sub = index.filter(include, exclude, None, title_words)
    c = Counter()
    for i in sub:
        c.update(set(index.recipes[i].canon))   # each ingredient counted once per recipe
    return {"kind": "common", "n": len(sub), "top": c.most_common(top_n), "filters": describe_filters(include, title_words, exclude),
            "method": "For each recipe in the filtered set, take its set of normalised ingredient names; count in how many recipes each name appears; show the top ones (salt/water/oil are NOT removed)."}


def ingredient_counts(index, include=(), title_words=(), exclude=()):
    sub = index.filter(include, exclude, None, title_words)
    vals = [len(index.recipes[i].ingredients) for i in sub]
    if not vals:
        return {"kind": "avg", "n": 0, "filters": describe_filters(include, title_words, exclude)}
    return {"kind": "avg", "n": len(vals), "mean": statistics.mean(vals), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals), "filters": describe_filters(include, title_words, exclude),
            "method": "Number of ingredient lines per recipe (blank lines and 'ADVERTISEMENT' scrape markers removed); mean and median over the filtered set."}


def rank_steps(index, include=(), title_words=(), exclude=(), top_n=5, order="asc"):
    sub = [i for i in index.filter(include, exclude, None, title_words) if index.recipes[i].steps]
    sub.sort(key=lambda i: ((len(index.recipes[i].steps) if order == "asc" else -len(index.recipes[i].steps)), index.recipes[i].id))
    return {"kind": "rank", "n": len(sub), "rows": sub[:top_n], "order": order, "filters": describe_filters(include, title_words, exclude),
            "method": "Steps = non-empty lines of the instructions (if the instructions are one line, sentences are counted; an instruction block repeated verbatim is counted once). Sorted by step count, ties broken by recipe ID; recipes with 0 parsable steps are excluded. Ties beyond the cut-off may exist."}
