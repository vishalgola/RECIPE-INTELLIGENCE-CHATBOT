"""Retrieval layer: exact filters over the FULL dataset (inverted index on normalised tokens) +
TF-IDF semantic ranking (title weighted x3 + normalised ingredients)."""
import pickle, re
from collections import defaultdict
from pathlib import Path
import numpy as np
from . import data as _data
from .data import load_recipes
from .normalization import term_tokens, strict_match, singular


CACHE_VERSION = 2      # bump when parsing/normalisation changes so stale caches are never reused


class RecipeIndex:
    def __init__(self, recipes, skipped=0):
        self.recipes = recipes
        self.skipped = skipped
        self.pos = {r.id: i for i, r in enumerate(recipes)}
        self.post = defaultdict(set)
        for i, r in enumerate(recipes):
            for s in r.sets:
                for t in s:
                    self.post[t].add(i)
        self._vec = self._X = None

    @property
    def N(self):
        return len(self.recipes)

    # ----- exact, complete filtering (used for every aggregate) -----
    def with_ingredient(self, tokens, strict=True):
        cand = None
        for t in tokens:
            p = self.post.get(t, set())
            cand = set(p) if cand is None else cand & p
            if not cand:
                return set()
        if strict:
            return {i for i in cand if any(strict_match(tokens, s) for s in self.recipes[i].sets)}
        return {i for i in cand if any(tokens <= s for s in self.recipes[i].sets)}

    def filter(self, include=(), exclude=(), max_steps=None, title_words=()):
        idx = None
        for term in include:
            s = self.with_ingredient(term_tokens(term))
            idx = s if idx is None else idx & s
        if idx is None:
            idx = set(range(self.N))
        if title_words:
            tw = {singular(w.lower()) for w in title_words}
            idx = {i for i in idx if tw <= self.recipes[i].title_toks}
        for rs in exclude:
            idx = {i for i in idx if not rs.hits_any(self.recipes[i].sets)}
        if max_steps is not None:
            idx = {i for i in idx if 0 < len(self.recipes[i].steps) <= max_steps}
        return sorted(idx)

    # ----- semantic ranking -----
    def _build(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        docs = [(r.title + " ") * 3 + " ".join(r.canon) for r in self.recipes]
        self._vec = TfidfVectorizer(sublinear_tf=True, stop_words="english", ngram_range=(1, 2),
                                    min_df=2 if len(docs) > 1000 else 1, max_features=400_000)
        self._X = self._vec.fit_transform(docs)

    def scores(self, text):
        if self._vec is None:
            self._build()
        q = self._vec.transform([text])
        return np.asarray(self._X.dot(q.T).todense()).ravel()

    def search(self, dish, allowed=None, k=5):
        """-> (top [(idx, score)], n_candidates). `allowed` = complete filtered set (list/None)."""
        if dish.strip():
            sc = self.scores(dish)
            if allowed is not None:
                mask = np.full(self.N, -1.0)
                mask[list(allowed)] = 0
                sc = np.where(mask >= 0, sc, -1.0)
            top = np.argsort(-sc, kind="stable")[:k]
            return [(int(i), float(sc[i])) for i in top if sc[i] > 0], (len(allowed) if allowed is not None else int((sc > 0).sum()))
        allowed = list(allowed) if allowed is not None else list(range(self.N))
        allowed.sort(key=lambda i: (len(self.recipes[i].steps) == 0, len(self.recipes[i].steps), self.recipes[i].id))
        return [(i, 0.0) for i in allowed[:k]], len(allowed)

    def similar(self, text, topn=400, skip=None):
        sc = self.scores(text)
        if skip is not None:
            sc[skip] = -1
        top = np.argsort(-sc, kind="stable")[:topn]
        return [int(i) for i in top if sc[i] > 0]


def load_index(data_dir="data", use_cache=True):
    data_dir = Path(data_dir)
    cache = data_dir / ".cache" / f"index_v{CACHE_VERSION}.pkl"
    files = [data_dir / f for f in ("recipes_raw_nosource_ar.json", "recipes_raw_nosource_epi.json", "recipes_raw_nosource_fn.json")]
    if use_cache and cache.exists() and all(f.exists() and cache.stat().st_mtime > f.stat().st_mtime for f in files):
        with open(cache, "rb") as f:
            return pickle.load(f)
    idx = RecipeIndex(load_recipes(data_dir), skipped=_data.STATS["skipped"])
    idx._build()
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with open(cache, "wb") as f:
            pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
    return idx
