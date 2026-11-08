"""Load all three Recipe Box JSON files. Stable ID = '<source>:<original key>' (ar / epi / fn).
Original title, ingredient list and instructions are kept untouched in `title`, `ingredients_raw`, `instructions`.
Scrape artefacts are removed ONLY from the derived fields used for matching/display: the word 'ADVERTISEMENT'
(the AllRecipes file appends it to every ingredient line and adds one standalone 'ADVERTISEMENT' line)."""
import json, re
from dataclasses import dataclass, field
from pathlib import Path
from .normalization import normalize, singular

FILES = {"ar": "recipes_raw_nosource_ar.json", "epi": "recipes_raw_nosource_epi.json",
         "fn": "recipes_raw_nosource_fn.json"}
AD_RE = re.compile(r"\bADVERTISEMENT\b")
STATS = {"total": 0, "skipped": 0}       # filled by load_recipes; recipes without title or ingredients are skipped


@dataclass
class Recipe:
    id: str
    source: str
    title: str                 # original
    ingredients_raw: list      # original list, untouched (contains ADVERTISEMENT markers in the ar file)
    instructions: str          # original
    ingredients: list = field(default_factory=list)   # cleaned display lines (marker removed, blanks dropped)
    steps: list = field(default_factory=list)
    canon: list = field(default_factory=list)
    sets: list = field(default_factory=list)
    title_toks: frozenset = frozenset()


def clean_line(s: str) -> str:
    return re.sub(r"\s+", " ", AD_RE.sub(" ", s)).strip()


def split_steps(instr: str):
    """Step-counting rule: non-empty lines; an instruction block repeated verbatim (seen in the epi file) counts once;
    if the text is a single line, split it into sentences."""
    parts = [p.strip() for p in re.split(r"\n+", instr or "") if p.strip()]
    h = len(parts) // 2
    if h and len(parts) % 2 == 0 and parts[:h] == parts[h:]:
        parts = parts[:h]
    if len(parts) == 1:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", parts[0]) if p.strip()]
    return parts


def build(rid, src, d):
    title = d.get("title") or ""
    ing_raw = [i for i in (d.get("ingredients") or []) if isinstance(i, str)]
    r = Recipe(rid, src, title, ing_raw, d.get("instructions") or "")
    r.ingredients = [c for c in (clean_line(i) for i in ing_raw) if c]
    r.steps = split_steps(r.instructions)
    norm = [normalize(i) for i in r.ingredients]
    r.canon = [n[0] for n in norm]
    r.sets = [n[1] for n in norm]
    r.title_toks = frozenset(singular(w) for w in re.findall(r"[a-z]+", title.lower()))
    return r


def load_recipes(data_dir):
    data_dir, out = Path(data_dir), []
    STATS.update(total=0, skipped=0)
    for src, fn in FILES.items():
        p = data_dir / fn
        if not p.exists():
            raise FileNotFoundError(f"{p} missing - run: python scripts/download_data.py")
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        for key, d in raw.items():
            STATS["total"] += 1
            if isinstance(d, dict) and d.get("title") and d.get("ingredients"):
                r = build(f"{src}:{key}", src, d)
                if r.ingredients:
                    out.append(r)
                    continue
            STATS["skipped"] += 1
    return out
