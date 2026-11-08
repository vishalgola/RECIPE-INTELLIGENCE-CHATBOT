"""Task 2: rank EXISTING recipes against ingredients on hand. Never invents recipes."""
from dataclasses import dataclass
from .normalization import normalize, strict_match, parse_quantity, to_base

PANTRY = {"water", "salt"}          # assumed available; neither counted as required nor missing
W_DEFAULT, W_FEWEST_MISSING = (0.6, 0.4), (0.4, 0.6)   # (usage, coverage)


@dataclass
class Have:
    raw: str
    name: str
    tokens: frozenset
    qty: tuple


def parse_have(items):
    out = []
    for raw in items:
        q = parse_quantity(raw)
        name, toks = normalize(raw)
        out.append(Have(raw, name, toks, q))
    return out


def _qty_status(have, line):
    if have.qty is None:
        return "not verified (no quantity given)"
    h, n = to_base(have.qty), to_base(parse_quantity(line))
    if not h or not n or h[0] != n[0] or (h[0] == "count" and have.qty[1] != "count"):
        return "not verified (units not comparable)"
    return f"sufficient (have {have.qty[0]:g}, need ~{n[1]:g} in same base unit)" if h[1] + 1e-9 >= n[1] else "INSUFFICIENT"


def score_recipe(index, i, haves, weights):
    r = index.recipes[i]
    req = [(line, s) for line, s in zip(r.ingredients, r.sets) if normalize(line)[0] not in PANTRY]
    if not req:
        return None
    matched, used, taken = [], set(), set()
    for hi, h in enumerate(haves):
        for j, (line, s) in enumerate(req):
            if strict_match(h.tokens, s):
                matched.append((h, line)); used.add(hi); taken.add(j)
                break
    if not matched:
        return None
    missing = [req[j][0] for j in range(len(req)) if j not in taken]
    usage, coverage = len(used) / len(haves), len(taken) / len(req)
    return dict(idx=i, id=r.id, title=r.title, usage=usage, coverage=coverage, score=weights[0] * usage + weights[1] * coverage,
                matched=[(h.raw, line, _qty_status(h, line)) for h, line in matched], missing=missing,
                unused=[haves[k].raw for k in range(len(haves)) if k not in used], steps=len(r.steps),
                n_used=len(used), n_taken=len(taken), n_req=len(req))


def match(index, have_items, exclude=(), max_steps=None, prefer=None, k=5):
    haves = parse_have(have_items)
    weights = W_FEWEST_MISSING if prefer == "fewest_missing" else W_DEFAULT
    cand = set()
    for h in haves:
        cand |= index.with_ingredient(h.tokens)
    scored, blocked = [], []
    for i in cand:
        r = index.recipes[i]
        if any(rs.hits_any(r.sets) for rs in exclude):
            continue                              # hard exclusion: never shown, not even as an 'alternative'
        s = score_recipe(index, i, haves, weights)
        if not s:
            continue
        too_long = max_steps is not None and not (0 < s["steps"] <= max_steps)
        (blocked if too_long else scored).append(s)

    def key(s):
        tie = (s["steps"], len(s["missing"])) if prefer == "fewest_steps" else (len(s["missing"]), s["steps"])
        return (-s["n_used"],) + tie + (s["id"],)

    scored.sort(key=key)
    blocked.sort(key=key)
    for b in blocked:
        b["violates"] = f"max steps {max_steps} (recipe has {b['steps']})"
    return dict(haves=haves, weights=weights, n_candidates=len(cand), results=scored[:k], n_eligible=len(scored),
                alternatives=blocked[:k] if not scored else [])
