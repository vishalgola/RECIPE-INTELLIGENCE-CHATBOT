"""Task 3: evidence-based substitution.
Evidence = how often similar recipes in the LOCAL dataset that lack the ingredient use each candidate substitute.
Ratios / prep notes / effects come from a small curated table and are labelled EXTERNAL RULES OF THUMB, not dataset facts."""
from .normalization import normalize, strict_match, parse_quantity
from .constraints import resolve

STRONG, MIN_COMPARABLE = 5, 5


def S(tok, line, effect, prep=None):
    return dict(tok=tok, line=line, effect=effect, prep=prep)


CAND = {
    "egg": {"role": "binder / moisture / some leavening", "subs": [
        S("applesauce", "1/4 cup unsweetened applesauce per egg", "adds moisture and mild sweetness; denser, less springy crumb"),
        S("banana", "1/4 cup mashed ripe banana per egg", "adds moisture and banana flavour; denser, can brown faster"),
        S("flaxseed", "1 tbsp ground flaxseed + 3 tbsp water per egg", "binds well; denser, slightly nutty",
          "Whisk the flaxseed with the water and rest 5 minutes until gel-like before adding."),
        S("tofu", "1/4 cup blended silken tofu per egg", "binds and moistens with neutral flavour; denser"),
        S("yogurt", "1/4 cup yogurt per egg", "moist, slightly tangy crumb"),
        S("vinegar", "1 tbsp vinegar + 1 tsp baking soda per egg", "adds lift but no binding; best in cakes/quick breads"),
    ]},
    "cream": {"role": "fat / body / richness of a sauce", "subs": [
        S("coconut cream", "equal amount coconut cream", "rich and thick; mild coconut flavour"),
        S("coconut milk", "equal amount full-fat coconut milk", "slightly thinner than cream; mild coconut flavour"),
        S("soy milk", "equal amount soy milk + 1 tsp cornstarch per cup", "thinner and less rich", "Whisk the cornstarch into the cold soy milk before heating."),
        S("tofu", "equal amount blended silken tofu", "thick, neutral; can taste flat without extra seasoning"),
        S("vegetable broth", "equal amount vegetable broth + 1 tbsp olive oil", "much lighter, savoury, not creamy"),
        S("cashew", "equal amount blended soaked cashews", "very creamy (contains tree nuts)"),
    ]},
    "milk": {"role": "liquid / moisture", "subs": [
        S("soy milk", "equal amount soy milk", "close match in baking"), S("oat milk", "equal amount oat milk", "slightly sweet"),
        S("almond milk", "equal amount almond milk", "thinner (contains tree nuts)"),
        S("coconut milk", "equal amount coconut milk", "richer, coconut flavour"), S("water", "equal amount water", "less rich"),
    ]},
    "butter": {"role": "fat / tenderness / flavour", "subs": [
        S("olive oil", "3/4 of the amount as olive oil", "less flavour, softer texture"),
        S("vegetable oil", "3/4 of the amount as vegetable oil", "neutral, softer/greasier texture"),
        S("coconut oil", "equal amount coconut oil", "firm when cool, mild coconut flavour"),
        S("applesauce", "1/2 of the amount as applesauce", "lower fat, cakier texture (baking only)"),
    ]},
    "cheese": {"role": "salty/umami flavour, melt", "subs": [
        S("nutritional yeast", "2-3 tbsp nutritional yeast per 1/2 cup cheese", "savoury/umami but no melt or stretch"),
        S("tofu", "crumbled tofu seasoned with salt and lemon", "ricotta-like crumble only"),
    ]},
    "flour": {"role": "structure / thickening", "subs": [
        S("rice flour", "equal amount rice flour", "more crumbly, less chew"),
        S("cornstarch", "1/2 of the amount as cornstarch (thickening only)", "works only for thickening"),
        S("almond flour", "equal amount almond flour", "moist, dense; tree nuts"),
    ]},
}
KEY_ALIAS = {"parmesan": "cheese", "cheddar": "cheese", "mozzarella": "cheese", "ricotta": "cheese", "feta": "cheese",
             "buttermilk": "milk", "mascarpone": "cheese", "gruyere": "cheese", "gouda": "cheese", "romano": "cheese"}


def key_for(tokens):
    for k in CAND:
        if k in tokens:
            return k
    for a, k in KEY_ALIAS.items():
        if a in tokens:
            return k
    return None


def _evidence(index, target_i, key):
    r = index.recipes[target_i]
    kt = frozenset([key])
    text = r.title + " " + " ".join(c for c, s in zip(r.canon, r.sets) if not (kt <= s))
    sim = index.similar(text, topn=400, skip=target_i)
    without = [i for i in sim if not any(kt <= s for s in index.recipes[i].sets)]
    return without


def propose(index, target_i, remove, keep_restrictions=()):
    """remove: list[Restriction] to eliminate; keep_restrictions: other hard restrictions substitutes must respect."""
    r = index.recipes[target_i]
    allr = list(remove) + list(keep_restrictions)
    plan, notes, ev_cache = [], [], {}
    for li, (line, toks) in enumerate(zip(r.ingredients, r.sets)):
        if not any(rs.hits(toks) for rs in remove):
            continue
        key = key_for(toks)
        if not key:
            notes.append(f"No vetted substitute for '{line}' - left unchanged, so the recipe still contains it.")
            plan.append(dict(li=li, line=line, key=None))
            continue
        if key not in ev_cache:
            without = _evidence(index, target_i, key)
            opts = []
            for sub in CAND[key]["subs"]:
                st = normalize(sub["tok"])[1]
                if any(rs.hits(st) for rs in allr):
                    continue                                     # would violate a restriction
                if any(strict_match(st, t) for t in r.sets):
                    continue                                     # already in the recipe: evidence would be confounded
                gcount = len(index.with_ingredient(st))
                if gcount == 0:
                    continue                                     # not present in the dataset at all
                sup = [index.recipes[i].id for i in without if any(strict_match(st, s) for s in index.recipes[i].sets)]
                opts.append(dict(sub=sub, support=sup, global_count=gcount))
            opts.sort(key=lambda o: (-len(o["support"]), -o["global_count"]))
            ev_cache[key] = dict(n_comparable=len(without), options=opts)
        ev = ev_cache[key]
        plan.append(dict(li=li, line=line, key=key, ev=ev))
    return dict(recipe=r, plan=plan, notes=notes)


def strength(ev):
    if not ev["options"]:
        return "none"
    top = ev["options"][0]
    n = len(top["support"])
    if ev["n_comparable"] < MIN_COMPARABLE or n == 0:
        return "none" if n == 0 else "weak"
    if n < STRONG:
        return "weak"
    if len(ev["options"]) > 1 and len(ev["options"][1]["support"]) >= 0.8 * n:
        return "conflicting"      # two substitutes about equally supported -> no clear winner
    return "strong"


def build_adaptation(result):
    """-> updated ingredient list + revised instructions (+ prep notes). Uses the top-supported allowed option per line."""
    r = result["recipe"]
    new_lines, prep, effects, changed = list(r.ingredients), [], [], {}
    for p in result["plan"]:
        if p["key"] is None or not p["ev"]["options"]:
            continue
        best = p["ev"]["options"][0]["sub"]
        q = parse_quantity(p["line"])
        mult = f" (x{q[0]:g} - original line was '{p['line']}')" if q and q[1] == "count" and q[0] != 1 else f" (replaces '{p['line']}')"
        new_lines[p["li"]] = f"{best['line']}{mult}"
        changed[p["key"]] = best["tok"]
        if best["prep"]:
            prep.append(best["prep"])
        effects.append(f"{p['key']} -> {best['tok']}: {best['effect']}")
    import re
    steps = []
    for st in r.steps:
        s2 = st
        for k, tok in changed.items():
            s2 = re.sub(rf"\b{k}s?\b", tok, s2, flags=re.I)
        steps.append(s2 + (" [adjusted]" if s2 != st else ""))
    return dict(ingredients=new_lines, steps=steps, prep=prep, effects=effects)
