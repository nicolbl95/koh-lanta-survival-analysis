# Modeling Strategy — Koh-Lanta Survival Analysis

## Version 1 — July 2026

### Single All-Cause Model

One survival model predicts time until definitive exit from Koh-Lanta,
regardless of exit cause (council vote, challenge loss, medical evacuation,
voluntary quit, etc.).

**Research question**:
"Controlling for age, sex, and pre-show physical profile, how far can a
contestant expect to progress before definitively leaving the game?"

### Predictors (3 variables only)

| Variable | Type | Notes |
|---|---|---|
| `age` | continuous | Numeric age at season start |
| `gender_normalized` | categorical | FEMALE / MALE |
| `physical_score` | binary nullable | 1 = above-average physical profile, 0 = ordinary, null = ambiguous |

### Explicitly excluded

- profession_raw, profession_normalized, profession_category
- higher_education_job_proxy or any education proxy
- Any separate models per exit cause

### Physical score definition

`physical_score = 1`: documented muscular build, strength/combat sport,
high physical training volume, or direct physical profession.

`physical_score = 0`: ordinary profile — no muscular build, no qualifying
sport, no physically demanding profession.

`physical_score = null`: ambiguous indicators only (never auto-imputed).

### Target variable

`all_cause_exit_event`:
- 1 for all definitively eliminated contestants (including medical,
  voluntary, disciplinary, finalist)
- 0 for the winner only (censored at the end)

### Time variable

`analysis_exit_order` = final_exit_order (for this season, no returns).

Normalized: (analysis_exit_order - 1) / (N - 1), range [0, 1].

### Return handling

Saisons with systematic returnee mechanics are excluded from the
primary dataset (Le Retour des Héros, Le Choc des Héros, etc.).

For rare medical-replacement returns in a regular season, the first
exit order is used as the analytical event.

### Descriptive statistics

All departure types and categories are preserved for descriptive
statistics and cross-tabulations, but never used as separate model
targets.

### Future work

- Test age × physical_score interaction (not yet implemented)
- Test gender × physical_score interaction (not yet implemented)
- Extend to multi-season dataset (not yet implemented)