"""Turn a user message into a structured Intent. Rule-based by default; Gemini (optional) can parse instead,
but it only ever produces this JSON structure - it never produces facts or numbers."""
import re
from dataclasses import dataclass, field, fields

NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


# Attributes the Recipe Box dataset does NOT contain (it has only title / ingredient lines / instruction text).
UNSUPPORTED = {
    "nutrition": r"calories?|kcal|nutrition\w*|cholesterol|sodium|macros?|vitamins?|fib(?:er|re)|carbs?|carbohydrates?|"
                 r"healthiest|healthy|grams? of protein|protein content|high[- ]protein|low[- ]fat|low[- ]carb",
    "time": r"how long|cook(?:ing)? time|prep(?:aration)? time|total time|how many (?:minutes|hours)|ready in|quick(?:est)?|fast(?:est)?",
    "servings": r"servings?|serves|how many people",
    "cost": r"cost|price|cheap(?:est)?|expensive|budget",
    "rating": r"ratings?|rated|reviews?|popular(?:ity)?|difficulty|easiest",
}
_UNS_ALL = r"\b(?:" + "|".join(UNSUPPORTED.values()) + r")\b"


def detect_unsupported(text: str):
    low = text.lower()
    return [k for k, pat in UNSUPPORTED.items() if re.search(rf"\b(?:{pat})\b", low)]


@dataclass
class Intent:
    task: str = "search"            # search | stats | match | substitute | show | help
    dish: str = ""
    include: list = field(default_factory=list)
    exclude: list = field(default_factory=list)
    allow: list = field(default_factory=list)
    max_steps: int = None
    reset: bool = False
    stat: str = None                # count | common | avg | rank
    title_words: list = field(default_factory=list)
    scope_active: bool = False
    top_n: int = 5
    order: str = "asc"
    have: list = field(default_factory=list)
    prefer: str = None
    k: int = 5
    ref: str = None                 # recipe id or ordinal like '2'
    remove: list = field(default_factory=list)

    @staticmethod
    def from_dict(d):
        names = {f.name for f in fields(Intent)}
        return Intent(**{k: v for k, v in d.items() if k in names and v is not None})


def _num(s):
    s = (s or "").strip().lower()
    return int(s) if s.isdigit() else NUM.get(s)


def _terms(text):
    text = re.sub(r"\b(too|as well|also|please|then|both|either|any|all)\b", " ", text)
    return [p.strip(" .?!'\"") for p in re.split(r",|\band\b|\bor\b|&", text) if p.strip(" .?!'\"")]


STEPS_RE = r"(?:at most|no more than|max(?:imum)?(?: of)?|under|fewer than|less than|within|up to)\s+(\w+)\s+(?:instruction\s+)?steps?"
EXCL_RE = (r"(?:\bno\b|\bwithout\b|\bexclude\b|\bexcluding\b|\bavoid(?:ing)?\b|can'?t have|cannot have|can not have|"
           r"do not want|don'?t want|allergic to|allergy to|intolerant to|can'?t eat|cannot eat|free of)\s+([a-z\-', ]+?)"
           r"(?=$|[.?!;]|\bat most\b|\bwith\b|\bprefer\b|\bin\b|\bfrom\b|\bunder\b|\bbut\b|\bplease\b|\bwhich\b|\bfor\b)")
FILLER = set("""find search show give suggest recommend want like looking look for me a an some recipe recipes dish dishes
please can you i id i'd would need is are what any that this it the of to my with and also then instead how do make get
ideas idea another other more different""".split())


NOISE = {"cannot", "can't", "cant", "not", "too", "also", "no", "exclude", "avoid", "allergic", "restriction", "only",
         "just", "but", "ones"}
UNS_NOISE = {"many", "much", "does", "did", "have", "has", "take", "takes", "long", "low", "high", "lowest", "highest",
             "per", "total", "time", "first", "second", "third", "fourth", "fifth", "one", "content", "amount", "in",
            "about", "tell", "is", "be", "there", "cook", "cooks", "cooking", "bake", "prep", "preparation"}


def parse_rules(msg: str) -> Intent:
    low = msg.lower().strip()
    it = Intent()
    uns = detect_unsupported(low)
    if re.search(r"\b(start over|new search|reset|clear (all|everything|filters))\b", low):
        it.reset = True
    m = re.search(STEPS_RE, low)
    if m and _num(m.group(1)):
        it.max_steps = _num(m.group(1))
        low_ns = low.replace(m.group(0), " ")
    else:
        low_ns = low
    for mm in re.finditer(r"(?:i can (?:now )?(?:have|eat)|ignore the|drop the)\s+([a-z\- ]+?)(?=$|[.?!;,]| restriction)", low_ns):
        it.allow += _terms(mm.group(1))
    for mm in re.finditer(EXCL_RE, low_ns):
        it.exclude += _terms(mm.group(1))
    it.exclude += [t for t in re.findall(r"\b([a-z]+)-free\b", low_ns)]
    it.exclude = [t for t in it.exclude if t not in ("more",)]
    rm = re.search(r"\b(?:remove|replace|substitute|swap(?: out)?|get rid of|eliminate|omit)\s+(?:the\s+)?([a-z\-, ]+?)(?=\s+(?:from|in|with|using|for|by|and use|without|instead)\b|[.?!;]|$)", low_ns)
    ref = re.search(r"\b((?:ar|epi|fn):[^\s,;?!]+)", msg)
    ordinal = re.search(r"\b(?:#|number |no\. ?)?(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\b|#(\d+)", low)
    if ref:
        it.ref = ref.group(1)
    elif ordinal:
        o = ordinal.group(1) or ordinal.group(2)
        it.ref = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "1st": "1", "2nd": "2", "3rd": "3", "4th": "4", "5th": "5"}.get(o, o)
    kk = re.search(r"\b(\w+)\s+recipes\b", low)
    if kk and _num(kk.group(1)):
        it.k = _num(kk.group(1))
    if re.search(r"fewest (additional|missing|extra)|fewer (additional|missing)|least (additional|missing)", low):
        it.prefer = "fewest_missing"
    elif re.search(r"(fewest|fewer|least|shortest) steps", low) and re.search(r"\bprefer", low):
        it.prefer = "fewest_steps"

    # ---- task routing ----
    h = re.search(r"\bi (?:have|got)\b(.+)", low_ns)
    if h:
        body = re.split(r"[.?!;]|\bsuggest\b|\bfind\b|\bgive\b|\bshow\b|\bwith no\b|\bno\b|\bat most\b|\bwithout\b|\bprefer\b|\bplease\b", h.group(1))[0]
        it.task, it.have = "match", _terms(body)
        it.exclude = [t for t in it.exclude if t not in it.have]
        return it
    if re.search(r"\b(replace|substitut\w*|swap|adapt|modify)\b|\b(remove|take out|omit|eliminate|get rid of)\b", low) and not re.search(r"restriction", low) and not re.search(r"\bhow many\b", low):
        it.task = "substitute"
        if rm:
            it.remove = _terms(rm.group(1))
        dm = re.search(r"\b(?:this|the|that)\s+([a-z\- ]+?)\s+recipe", low)
        if dm:
            it.dish = dm.group(1).strip()
        if not it.remove and it.exclude:           # 'make this dairy-free'
            it.remove, it.exclude = list(it.exclude), []
        return it
    if not uns and re.search(r"\bhow many\b|\bpercent|\bpercentage\b|\baverage\b|\bmedian\b|\bmean\b|\bmost common\b|\bcommonly used\b|\bfewest\b|\bmost steps\b|\blongest\b|\bshortest\b|\bleast\b|\brank\b", low) \
            and not re.search(r"\bprefer\b", low):
        it.task = "stats"
        first = re.split(r"[?.!]", low)[0]
        it.scope_active = bool(re.search(r"\b(of those|among these|among those|in these|of these)\b", low))
        if re.search(r"\b(median|average|mean)\b", low) and "ingredient" in low:
            it.stat = "avg"
        elif re.search(r"most common|commonly used|top ingredients|popular ingredient", low):
            it.stat = "common"
        elif re.search(r"step", low) and re.search(r"fewest|most|least|shortest|longest|rank|lowest|highest", low):
            it.stat = "rank"
            it.order = "desc" if re.search(r"\bmost steps\b|longest|highest", low) else "asc"
            tn = re.search(r"(?:which|top|the)\s+(\w+)\s+(?:recipes\s+)?(?:have|with|has|use|take|require|are)", low)
            it.top_n = (_num(tn.group(1)) if tn and _num(tn.group(1)) else 5)
        else:
            it.stat = "count"
        inc = re.search(r"(?:containing|contains?|with|using|that use|that have|include|including)\s+(?:both\s+)?(.+?)(?=,|\?|\.|\bwhich\b|\bwhat\b|$)", first)
        if inc:
            it.include = _terms(inc.group(1))
        tw = re.search(r"(?:in|for|among|of)\s+(?:the\s+)?([a-z\- ]+?)\s+recipes", first)
        if tw and not re.search(r"\b(all|the|these|those)\b$", tw.group(1)):
            it.title_words = [w for w in tw.group(1).split() if w not in FILLER and w not in ("number", "ingredients")]
        return it
    inc = re.search(r"\b(?:containing|contains?|using|that use|with)\s+(.+?)(?=[.?!;]|\bno\b|\bwithout\b|\bat most\b|$)", low_ns)
    if it.ref and re.search(r"\b(show|ingredient|instruction|step|how (?:do|to)|make it|full|detail|list)\b", low):
        it.task = "show"
        return it
    if re.search(r"\b(ingredients?|instructions?|steps)\b.*\b(of|for)\b.*\b(it|that|this|one)\b|\bhow (do i|to) (make|cook) (it|that|this)\b", low):
        it.task, it.ref = "show", it.ref or "1"
        return it
    # search / refinement
    d = low_ns
    d = re.sub(EXCL_RE, " ", d)
    d = re.sub(r"\b[a-z]+-free\b|\bi can (?:now )?(?:have|eat)\b.*", " ", d)
    if inc:
        it.include = _terms(inc.group(1))
        d = d.replace(inc.group(0), " ")
    if uns:
        d = re.sub(_UNS_ALL, " ", d)
    skip = NOISE | (UNS_NOISE if uns else set())
    words = [w for w in re.findall(r"[a-z\-]+", d) if w not in FILLER and w not in skip]
    it.dish = " ".join(words)
    return it
