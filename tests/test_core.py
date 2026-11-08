import pytest
from src.normalization import normalize, strict_match, term_tokens
from src.constraints import resolve
from src.data import split_steps, STATS
from src import analytics, matcher


def test_normalize():
    assert normalize("2 (14.5 oz) cans diced tomatoes, drained")[0] == "tomato"  # 'diced' is a descriptor
    assert normalize("3 cloves garlic, minced")[0] == "garlic"
    assert normalize("1/4 cup peanut butter")[1] == frozenset({"peanut_butter"})


def test_strict_forms():
    g = term_tokens("garlic")
    assert strict_match(g, normalize("2 garlic cloves")[1])
    assert not strict_match(g, normalize("1 tsp garlic powder")[1])
    assert not strict_match(term_tokens("onion"), normalize("3 green onions")[1])


def test_dairy_group():
    d = resolve("dairy")[0]
    assert d.hits(normalize("1 cup heavy cream")[1])
    assert not d.hits(normalize("1 cup coconut milk")[1])
    assert not d.hits(normalize("1/4 cup peanut butter")[1])
    assert resolve("dairy-free")[0].label == "dairy"


# ---------- data loading (real-format quirks) ----------
def test_advertisement_marker_removed_but_raw_kept(ix):
    r = ix.recipes[ix.pos["ar:kar0"]]
    assert all("ADVERTISEMENT" not in l for l in r.ingredients)
    assert any("ADVERTISEMENT" in l for l in r.ingredients_raw)          # original preserved untouched
    assert "heavy cream" in r.canon and not any("advertisement" in c for c in r.canon)
    assert len(r.ingredients) == 5                                        # standalone marker line dropped


def test_bad_records_skipped_and_counted(ix):
    assert STATS["skipped"] == 3 and ix.N == 21


def test_repeated_instruction_block_counts_once():
    block = "Beat the egg whites. Fold in cream."
    assert split_steps(block + "\n" + block) == split_steps(block) and len(split_steps(block)) == 2
    assert len(split_steps("A.\nB.\nA.\nB.")) == 2
    assert len(split_steps("A.\nB.\nC.")) == 3


def test_count_garlic_onion(ix):
    r = analytics.count(ix, ["garlic", "onion"])
    brute = [i for i, x in enumerate(ix.recipes)
             if any(strict_match(term_tokens("garlic"), s) for s in x.sets) and any(strict_match(term_tokens("onion"), s) for s in x.sets)]
    assert r["ids"] == brute and r["N"] == len(ix.recipes) and r["n"] > 0
    assert abs(r["pct"] - 100 * r["n"] / r["N"]) < 1e-9
    naive = sum(1 for x in ix.recipes if "garlic" in " ".join(x.ingredients).lower() and "onion" in " ".join(x.ingredients).lower())
    assert naive > r["n"]            # substring matching would wrongly count garlic powder / onion powder / green onion


def test_rank_steps_tomato(ix):
    r = analytics.rank_steps(ix, ["tomato"], top_n=3)
    steps = [len(ix.recipes[i].steps) for i in r["rows"]]
    assert steps == sorted(steps) and steps[0] == 2


def test_followup_dairy(bot):
    a = bot.reply("Find a penne pasta recipe.")
    assert "Creamy Penne" in a
    b = bot.reply("I cannot have dairy.")
    assert "Creamy Penne" not in b and "Vegan Penne Cream" in b and "dairy" in b


def test_match_and_followup(bot):
    a = bot.reply("I have eggs, onions, tomatoes, and rice. Suggest five recipes with no peanuts and at most six steps. Prefer recipes that need the fewest additional ingredients.")
    assert "Peanut Noodles" not in a and "Egg Fried Rice" in a
    b = bot.reply("Exclude eggs too")
    assert "Egg Fried Rice" not in b and "Tomato Rice with Eggs" not in b and "Tomato Rice" in b


def test_no_match_never_relaxes(bot):
    a = bot.reply("I have peanut butter. Find recipes with no peanuts.")
    assert "NO MATCH" in a and "Peanut Noodles" not in a


def test_no_match_steps_marked(bot):
    a = bot.reply("I have rice, water. Find recipes at most one steps.")
    assert "NO MATCH" in a and "VIOLATES" in a


def test_substitution_eggs(bot):
    a = bot.reply("Take this banana bread recipe and remove eggs.")
    assert "Banana Bread" in a and "applesauce" in a.lower() and "Evidence strength" in a and "PREDICTIONS" in a
    assert "2 eggs" in a   # original line is cited
    assert "WEAK" in a or "NO direct" in a or "STRONG" in a


def test_substitution_respects_dairy(bot):
    a = bot.reply("Replace cream in this pasta recipe without dairy.")
    assert "yogurt" not in a.split("Updated ingredient list")[1].split("Revised")[0]


def test_unsupported_left_unchanged(bot):
    a = bot.reply("Take this tomato soup recipe and remove tomatoes.")
    assert "nothing to substitute" in a or "No vetted substitute" in a


# ---------- do not fabricate unavailable attributes ----------
@pytest.mark.parametrize("q", ["How many calories does the first one have?", "What is the protein content of it?",
                               "Which recipe is the healthiest?", "How many servings does it make?"])
def test_nutrition_and_other_missing_attributes_refused(bot, q):
    bot.reply("Find a penne pasta recipe.")
    a = bot.reply(q)
    assert "NOT AVAILABLE IN THE DATASET" in a and "will not guess" in a
    assert "[" not in a.split("\n")[0] and "recipes satisfy" not in a      # no junk search was run


def test_cooking_time_quotes_instruction_text_only(bot):
    bot.reply("Find a plain rice recipe.")
    a = bot.reply("How long does it take to cook?")
    assert "NOT AVAILABLE" in a and "18 minutes" in a and "not a verified total time" in a


def test_unsupported_word_does_not_break_search(bot):
    a = bot.reply("Find a quick penne recipe.")
    assert "NOT AVAILABLE" in a and "Penne" in a and "recipes satisfy" in a


def test_advertisement_not_shown_to_user(bot):
    bot.reply("Find a penne pasta recipe.")
    a = bot.reply("show the first one")
    assert "ADVERTISEMENT" in a and "hidden" in a      # only the explanatory note
    assert "- 1 lb penne" in a and "penne pasta ADVERTISEMENT" not in a
