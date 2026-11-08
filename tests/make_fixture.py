"""Tiny synthetic dataset in the exact Recipe Box format (title/ingredients/instructions) for tests.
Mimics the real quirk: the 'ar' file appends ADVERTISEMENT to every ingredient line (+ one standalone line)."""
import json
from pathlib import Path

R = [
 ("Creamy Penne", ["1 lb penne pasta", "1 cup heavy cream", "2 cloves garlic, minced", "1/2 cup grated parmesan cheese", "salt"], "Boil pasta.\nHeat cream with garlic.\nToss with parmesan."),
 ("Penne Arrabbiata", ["1 lb penne", "2 cups diced tomatoes", "3 cloves garlic", "1 tsp red pepper flakes", "2 tbsp olive oil"], "Boil penne.\nSimmer tomatoes with garlic and oil.\nToss."),
 ("Vegan Penne Cream", ["1 lb penne pasta", "1 cup coconut milk", "2 garlic cloves", "1 onion, chopped"], "Boil penne.\nSimmer coconut milk with garlic and onion.\nToss."),
 ("Pasta Alfredo", ["12 oz fettuccine", "1 cup cream", "1/2 cup butter", "1 cup parmesan"], "Boil.\nMelt butter.\nAdd cream.\nToss."),
 ("Garlic Onion Soup", ["4 onions, sliced", "6 garlic cloves", "4 cups broth", "salt"], "Saute onions.\nAdd garlic.\nAdd broth.\nSimmer."),
 ("Garlic Powder Chicken", ["2 chicken breasts", "1 tsp garlic powder", "1 tsp onion powder"], "Season.\nBake."),
 ("Green Onion Rice", ["2 cups cooked rice", "3 green onions", "1 tbsp soy sauce"], "Heat rice.\nStir in onions and soy."),
 ("Tomato Salad", ["3 ripe tomatoes", "1 red onion", "2 tbsp olive oil"], "Slice.\nToss."),
 ("Tomato Soup", ["6 tomatoes", "1 onion", "2 cloves garlic", "2 cups broth"], "Roast tomatoes.\nBlend with broth.\nSeason.\nServe."),
 ("Tomato Toast", ["2 slices bread", "1 tomato"], "Toast bread. Top with tomato."),
 ("Egg Fried Rice", ["3 eggs", "2 cups cooked rice", "1 onion", "1 tomato", "1 tbsp oil"], "Scramble eggs.\nFry onion.\nAdd rice and tomato.\nServe."),
 ("Tomato Rice with Eggs", ["2 eggs", "1 cup rice", "2 tomatoes", "1 onion"], "Cook rice.\nFry onion and tomato.\nTop with fried eggs."),
 ("Peanut Noodles", ["8 oz noodles", "1/4 cup peanut butter", "2 eggs", "1 tomato"], "Boil.\nMix sauce.\nToss."),
 ("Banana Bread", ["3 ripe bananas", "2 cups all-purpose flour", "2 eggs", "1/2 cup butter", "3/4 cup sugar", "1 tsp baking soda"], "Mash bananas.\nCream butter and sugar.\nBeat in eggs.\nFold in flour.\nBake 60 minutes."),
 ("Vegan Banana Bread", ["3 bananas", "2 cups flour", "1/4 cup applesauce", "1/2 cup vegetable oil", "3/4 cup sugar", "1 tsp baking soda"], "Mash bananas.\nMix wet.\nFold in flour.\nBake."),
 ("Eggless Banana Muffins", ["2 bananas", "1.5 cups flour", "1/4 cup applesauce", "1/3 cup oil", "1/2 cup sugar", "1 tsp baking powder"], "Mix.\nBake."),
 ("Flax Banana Loaf", ["2 bananas", "2 cups flour", "1 tbsp ground flaxseed", "1/2 cup oil", "1/2 cup sugar", "1 tsp baking soda"], "Mix flax with water.\nMix.\nBake."),
 ("Applesauce Cake", ["2 cups flour", "1 cup applesauce", "1/2 cup oil", "1 cup sugar", "1 tsp cinnamon"], "Mix.\nBake."),
 ("Banana Pancakes", ["1 banana", "1 cup flour", "1 cup milk", "1 egg", "1 tbsp butter"], "Mash.\nMix.\nCook."),
 ("Plain Rice", ["1 cup rice", "2 cups water", "salt"], "Boil water.\nAdd rice.\nCook 18 minutes.\nRest."),
 ("Tomato Rice", ["1 cup rice", "2 tomatoes", "1 onion", "1 tbsp olive oil"], "Fry.\nAdd rice.\nCook."),
]


def make(path):
    path = Path(path); path.mkdir(parents=True, exist_ok=True)
    parts = {"ar": R[:8], "epi": R[8:15], "fn": R[15:]}
    for src, rows in parts.items():
        d = {}
        for n, (t, ing, ins) in enumerate(rows):
            if src == "ar":      # real AllRecipes quirk: marker on every line + one standalone line
                ing = [f"{i} ADVERTISEMENT" for i in ing] + ["ADVERTISEMENT"]
                ins = ins + "\n"
            d[f"k{src}{n}"] = {"title": t, "ingredients": ing, "instructions": ins, "picture_link": None}
        d["bad1"] = {"title": None, "ingredients": ["1 cup x"], "instructions": "x"}   # skipped: no title
        (path / f"recipes_raw_nosource_{src}.json").write_text(json.dumps(d))
