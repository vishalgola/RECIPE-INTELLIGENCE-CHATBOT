# Evaluation Report - Recipe Intelligence Chatbot

Dataset: Recipe Box (eightportions.com), 3 JSON files, **122,971 recipes loaded** (2,193 records skipped: no title or no ingredients).
Reproduce: `python evaluation/run_eval.py --data data --baseline` (writes `transcripts.md` and `results.md`).

## 1. Results (9 conversations, all PASS)

| Case | Task | What is checked | Result |
|---|---|---|---|
| T1-followup-dairy | 1 | "Find a penne pasta recipe." then "I cannot have dairy." - no dairy ingredient in results (re-verified independently); 51,526 recipes remain eligible | PASS |
| T1-aggregate | 1 | Garlic AND onion count equals a brute-force recount: **15,920 of 122,971 (12.95%)** | PASS |
| T1-rank-steps | 1 | Five tomato recipes with fewest steps (15,112 candidates), step counts non-decreasing | PASS |
| T1-unsupported-nutrition | 1 | Calories / cooking time are refused as "NOT AVAILABLE IN THE DATASET", no invented numbers | PASS |
| T2-match-followup | 2 | eggs/onions/tomatoes/rice, no peanuts, <= 6 steps, fewest extra ingredients; follow-up "Exclude eggs too" changes results and no egg remains | PASS |
| T2-no-match | 2 | "I have peanut butter. Find recipes with no peanuts." - 1,874 candidates, 0 pass, system says NO MATCH | PASS |
| T3-weak-evidence | 3 | Banana bread without eggs: evidence cited with recipe IDs, strength labelled, effects labelled as predictions | PASS |
| T3-dairy-cream | 3 | Cream replaced without dairy: evidence section present, no dairy substitute proposed | PASS |
| T3-no-vetted-substitute | 3 | Tomato soup without tomatoes: system refuses to invent a substitute | PASS |

## 2. System vs one-shot LLM / naive method

Question: "How many recipes contain both garlic and onion?"

| Method | Answer | Comment |
|---|---|---|
| This system (normalised, strict ingredient forms, full dataset) | **15,920** (12.95%) | Computed over all 122,971 recipes |
| Naive substring grep | 20,245 | +4,325 (27% too high): also matches garlic powder/salt, onion powder, green onions |
| One-shot Gemini (plain question) | Declined to give a number | Cannot see the dataset |
| One-shot Groq (forced to estimate) | Declined to give a number | Cannot see the dataset |

Honest reading: the one-shot LLM answer is **ungrounded / unavailable**, not "wrong". An LLM without retrieval has no way to count rows in a 123k-recipe dataset; the system can, and the number is verifiable by brute force.

## 3. What worked
- Python computes every count, filter, ranking and constraint; the LLM only parses intent or re-words (and re-worded text is verified: no new numbers, same recipe IDs).
- Follow-up memory (dish, exclusions, max steps, ingredients on hand, selected recipe) behaves correctly across turns.
- Unsupported attributes (nutrition, time, servings, cost, rating) are refused instead of guessed.
- Substitution is evidence-based: it is drawn from the 400 most similar recipes lacking the ingredient, and labelled STRONG / WEAK / NONE / CONFLICTING.

## 4. Problems found and fixed
- **LLM misrouting** of "I have peanut butter. Find recipes with no peanuts." -> rule-first router; the LLM is used only for plain search phrasing.
- **Ranking bias to tiny recipes** -> rank by number of your ingredients used first, then fewer missing, then fewer steps.
- **Cream demo picked a recipe without cream** -> the substitution target is chosen from recipes that contain the ingredient.
- **"How long does it take to cook?" ran a junk search for "cook"** -> noise words added and the unsupported-attribute refusal applied first.
- **Empty-dish search returned 0-step recipes** -> guard message plus sorting that puts 0-step recipes last.

## 5. Remaining weaknesses (honest)
- "egg noodles" counts as egg (e.g. "Paprika Chicken" matched "Suggested accompaniment: egg noodles or rice").
- Substitution evidence can be WEAK: banana bread without egg - yogurt / applesauce / flaxseed appear in 3 of 57 similar recipes each; cream - vegetable broth 2 of 227, coconut milk 0 locally (1,392 overall).
- The rule-based instruction rewrite is sometimes awkward ("slightly beaten yogurt", "stir until thickened" for broth).
- The tomato-soup case still shows the unchanged ingredient list under the heading.
- "At most N steps" can return 1-step recipes (a few entries are only one line of text).
- The dietary word list (dairy, nuts, ...) is a lexicon, not medical or allergy advice.

## 6. Handling of information not in the dataset
The dataset has only title, ingredient lines and instruction text. Questions about calories, nutrition, cooking time, servings, cost or ratings get an explicit "NOT AVAILABLE IN THE DATASET" reply. Times are only quoted if they literally appear in the instruction text.
