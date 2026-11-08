# Eval results

Dataset: 122971 recipes loaded (2193 records skipped: no title/ingredients).

| case | result | note |
|---|---|---|
| T1-followup-dairy | PASS | dairy hits: [] |
| T1-aggregate | PASS | brute-force=15920 |
| T1-rank-steps | PASS | steps=[1, 1, 1, 1, 1] |
| T1-unsupported-nutrition | PASS | both follow-ups refused; no invented numbers |
| T2-match-followup | PASS | 5 ids; top result uses 3 of your ingredients |
| T2-no-match | PASS |  |
| T3-weak-evidence | PASS | evidence label present |
| T3-dairy-cream | PASS | evidence label present |
| T3-no-vetted-substitute | PASS | refused to invent a substitute |

## Baselines for: 'How many recipes contain both garlic and onion?'
- **System (normalised, strict forms):** 15920 of 122971 (12.95%)
- **Naive substring grep ('garlic' and 'onion' anywhere in the ingredient text):** 20245 - over-counts by 4325 because it also matches garlic powder/salt, onion powder, green onions, etc.
- **One-shot groq (no retrieval, forced to estimate):** I’m not able to examine the contents of that dataset directly, so I can’t give you an exact count. However, you can determine the number yourself by loading the three JSON files, iterating over each recipe, and checking whether both “garlic” and “onion” appear in the ingredient list (or in the recipe text). The total of recipes that meet both conditions will be the number you’re looking for. If you need help writing a script to do this, let me know!