"""Dietary / allergen lexicons. These screen RECIPE TEXT only; they are not medical safety checks."""
from dataclasses import dataclass
from .normalization import normalize

GROUPS = {
    "dairy": "milk cream butter cheese yogurt ghee buttermilk whey casein custard ricotta mozzarella parmesan "
             "cheddar feta mascarpone paneer kefir creme fraiche gouda gruyere brie provolone romano halloumi "
             "half-and-half".split(),
    "gluten": "flour bread breadcrumb pasta noodle spaghetti penne macaroni fettuccine linguine lasagna couscous "
              "barley rye semolina tortilla cracker bulgur farro seitan beer wheat pita bagel".split(),
    "nuts": "almond walnut pecan cashew pistachio hazelnut macadamia almond_butter cashew_butter almond_milk "
            "almond_flour cashew_milk".split(),
    "peanut": "peanut groundnut peanut_butter".split(),
    "egg": "egg mayonnaise meringue".split(),
    "shellfish": "shrimp prawn crab lobster clam mussel oyster scallop crayfish".split(),
    "soy": "soy soybean tofu edamame miso tempeh soy_milk".split(),
    "fish": "fish salmon tuna cod tilapia anchovy sardine trout halibut".split(),
    "meat": "chicken beef pork bacon ham sausage lamb turkey veal salami pepperoni steak".split(),
    "honey": ["honey"],
}
GROUPS["vegetarian"] = GROUPS["meat"] + GROUPS["fish"]
ALIASES = {"dairy": "dairy", "lactose": "dairy", "gluten": "gluten", "wheat": "gluten", "nut": "nuts",
           "tree nut": "nuts", "peanut": "peanut", "egg": "egg", "shellfish": "shellfish", "soy": "soy",
           "soya": "soy", "fish": "fish", "meat": "meat", "vegetarian": "vegetarian"}
VEGAN = ["vegetarian", "dairy", "egg", "honey"]


@dataclass(frozen=True)
class Restriction:
    label: str
    sets: tuple  # tuple of frozensets; a line is a hit if any set is a subset of its tokens

    def hits(self, tokens) -> bool:
        return any(s <= tokens for s in self.sets)

    def hits_any(self, token_sets) -> bool:
        return any(self.hits(t) for t in token_sets)

    def hit_lines(self, lines, token_sets):
        return [l for l, t in zip(lines, token_sets) if self.hits(t)]


def _group(label):
    return Restriction(label, tuple(frozenset([t]) for t in GROUPS[label]))


def resolve(term: str):
    """User word -> list[Restriction]. Known allergen/diet words map to a group, anything else is a plain term."""
    t = term.lower().strip().removesuffix("-free").removesuffix(" free").strip()
    if t == "vegan":
        return [_group(g) for g in VEGAN]
    canon = normalize(t)[0]
    if canon in ALIASES:
        return [_group(ALIASES[canon])]
    return [Restriction(canon, (normalize(t)[1],))]
