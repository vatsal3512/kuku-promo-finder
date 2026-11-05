# Raw outputs

Unedited outputs from running the tool on the full input pack (50 episodes).

- `final_run/` - the submitted run (Nemotron 3 Ultra + Mistral Large 4 as second judge). Start with `promos.md`.
- `v2_run/` - the same show run with the later, more robust version of the code (fast mode, more input formats, clearer model errors, a cliffhanger minimum). The blind MiniMax check scores it 0.78 against 0.80 for the submitted run, inside the judges' noise, so `final_run/` stays the official result. See `evaluation/audit_minimax_v2.json`.
- `rules_only_run/` - same input with `--offline`, rules only, no LLM. Used as the baseline.
- `evaluation/baseline_llm_only_nemotron.json` - the model asked to write promo timestamps directly (77/100 valid).
- `evaluation/audit_mistral.json`, `evaluation/audit_minimax.json` - blind audits by models that didn't pick the clips. MiniMax took no part in any run.
- `evaluation/ab_pairs.txt`, `ab_answers.csv`, `ab_key.json` - my blind A/B check: tool cut vs rules-only cut, 8 pairs.

The scripts themselves are Kuku's and are not included.
