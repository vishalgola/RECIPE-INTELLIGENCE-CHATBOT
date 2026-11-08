"""Ingredient-line normalisation and matching rules.

Pipeline for one raw line such as "2 (14.5 oz) cans diced tomatoes, drained":
  lowercase -> drop parentheses -> drop text after first comma -> protect compound
  products (peanut butter, coconut milk ...) -> strip leading quantity/unit ->
  drop preparation words (chopped, fresh ...) -> singularise -> apply a SMALL synonym map.
Result: (canonical_name, frozenset_of_tokens)  e.g. ("diced tomato", {"diced","tomato"}).
"""
import re
from functools import lru_cache

_FRACS = {"¼": " 0.25 ", "½": " 0.5 ", "¾": " 0.75 ", "⅓": " 0.333 ", "⅔": " 0.667 ", "⅛": " 0.125 "}

UNIT_MAP = {
    "cup": "cup", "cups": "cup", "c": "cup", "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp",
    "tbs": "tbsp", "tbsps": "tbsp", "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "tsps": "tsp",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb", "ounce": "oz", "ounces": "oz", "oz": "oz",
    "gram": "g", "grams": "g", "g": "g", "kg": "kg", "kilogram": "kg", "ml": "ml", "l": "l",
    "liter": "l", "liters": "l", "litre": "l",
}
OTHER_UNITS = {"can", "cans", "package", "packages", "pkg", "stick", "sticks", "quart", "quarts", "pint",
               "pints", "gallon", "gallons", "slice", "slices", "piece", "pieces", "bunch", "bunches",
               "head", "heads", "sprig", "sprigs", "handful", "pinch", "dash", "clove", "cloves"}

DESCRIPTORS = set("""chopped minced diced sliced fresh large small medium finely roughly coarsely peeled grated
shredded crushed melted softened packed divided optional boneless skinless cooked uncooked raw whole extra virgin
unsalted salted freshly thinly cut piece inch taste serving garnish more needed hot cold warm ripe firm thick thin
lean good quality heaping level rounded generous and or of for to as with into the a an about plus room
temperature pinch dash drained rinsed trimmed halved quartered torn""".split())

# Multi-word products that must NOT be confused with their head word (butter != peanut butter).
COMPOUNDS = [
    "peanut butter", "almond butter", "cashew butter", "cocoa butter", "apple butter", "sunflower seed butter",
    "coconut milk", "almond milk", "soy milk", "rice milk", "oat milk", "cashew milk", "hemp milk",
    "coconut cream", "cream of tartar", "cream of coconut", "butter bean", "rice flour", "almond flour",
    "coconut flour", "chickpea flour", "nutritional yeast", "flax seed", "apple sauce",
]
SYNONYMS = [  # deliberately small; each one is a true equivalence
    (r"\bscallion\b", "green onion"), (r"\bspring onion\b", "green onion"), (r"\baubergine\b", "eggplant"),
    (r"\bcourgette\b", "zucchini"), (r"\bgarbanzo bean\b", "chickpea"), (r"\bchick pea\b", "chickpea"),
    (r"\bconfectioner sugar\b", "powdered sugar"), (r"\bicing sugar\b", "powdered sugar"),
    (r"\bcapsicum\b", "bell pepper"), (r"\byoghurt\b", "yogurt"), (r"\bmayo\b", "mayonnaise"),
    (r"\bplain flour\b", "all-purpose flour"), (r"\bflax_seed\b", "flaxseed"), (r"\bapple_sauce\b", "applesauce"),
]
KEEP_S = {"molasses", "hummus", "asparagus", "couscous", "swiss", "grits", "watercress", "citrus", "lentils"}
SPECIAL = {"chilies": "chili", "cookies": "cookie", "brownies": "brownie", "pies": "pie", "leaves": "leaf",
           "smoothies": "smoothie", "veggies": "veggie", "loaves": "loaf", "halves": "half", "lentils": "lentil"}

# Words that turn an ingredient into a DIFFERENT product (tomato != tomato paste, onion != green onion).
FORMS = set("""powder salt juice oil sauce paste extract flake seasoning soup broth stock vinegar flour milk butter
cream cheese yogurt syrup zest peel rind wine liqueur jam jelly bouillon mix spread green spring sweet sour
vodka""".split())


def _prep(raw: str) -> str:
    s = raw.lower()
    for k, v in _FRACS.items():
        s = s.replace(k, v)
    return re.sub(r"\([^)]*\)", " ", s)


def singular(t: str) -> str:
    if t in SPECIAL:
        return SPECIAL[t]
    if len(t) <= 3 or t in KEEP_S:
        return t
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith("oes"):
        return t[:-2]
    if t.endswith(("ches", "shes", "xes")):
        return t[:-2]
    if t.endswith(("ss", "us", "is")):
        return t
    return t[:-1] if t.endswith("s") else t


@lru_cache(maxsize=600_000)
def normalize(raw: str):
    s = _prep(raw).split(",")[0]
    s = re.sub(r"\bgarlic cloves?\b", "garlic", s)
    for phrase in COMPOUNDS:
        s = s.replace(phrase, phrase.replace(" ", "_"))
    s = re.sub(r"[^a-z0-9/._\- ]", " ", s)
    toks, i, seen = s.split(), 0, False
    while i < len(toks):
        t = toks[i]
        if re.fullmatch(r"[\d./\-]+(?:inch|cm)?", t):
            seen = True
            i += 1
        elif seen and (t in UNIT_MAP or t in OTHER_UNITS):
            i += 1
        else:
            break
    toks = [singular(t) for t in toks[i:] if not re.fullmatch(r"[\d./\-]+", t)]
    toks = [t for t in toks if t not in DESCRIPTORS]
    s = " ".join(toks)
    for pat, rep in SYNONYMS:
        s = re.sub(pat, rep, s)
    toks = s.split()
    if not toks:
        toks = re.findall(r"[a-z]+", raw.lower())[:3] or ["?"]
    return " ".join(toks), frozenset(toks)


def term_tokens(text: str) -> frozenset:
    return normalize(text)[1]


def strict_match(term: frozenset, ing: frozenset) -> bool:
    """Include/ingredient-presence rule: all query tokens present AND the line is not a different
    product form (e.g. 'garlic powder' does not count as 'garlic')."""
    return term <= ing and not ((ing - term) & FORMS)


def broad_match(term: frozenset, ing: frozenset) -> bool:
    """Exclusion rule: conservative, any line containing the tokens is a hit."""
    return term <= ing


# ---------- quantities ----------
_VOL = {"tsp": 4.929, "tbsp": 14.787, "cup": 236.588, "ml": 1.0, "l": 1000.0}
_WT = {"g": 1.0, "oz": 28.35, "lb": 453.6, "kg": 1000.0}


def parse_quantity(raw: str):
    toks = _prep(raw).split()
    val, i, found = 0.0, 0, False
    while i < len(toks) and re.fullmatch(r"\d+(\.\d+)?|\d+/\d+", toks[i]):
        t = toks[i]
        val += int(t.split("/")[0]) / int(t.split("/")[1]) if "/" in t else float(t)
        found, i = True, i + 1
    if not found:
        return None
    unit = UNIT_MAP.get(toks[i]) if i < len(toks) else None
    if unit is None:
        unit = toks[i] if i < len(toks) and toks[i] in OTHER_UNITS else "count"
    return val, unit


def to_base(q):
    """-> (family, amount) or None when not safely comparable."""
    if q is None:
        return None
    v, u = q
    if u in _VOL:
        return "volume", v * _VOL[u]
    if u in _WT:
        return "weight", v * _WT[u]
    if u == "count":
        return "count", v
    return None
