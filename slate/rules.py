"""Tunable game constants. Deliberately a flat namespace so playtesting is a
one-line edit rather than a refactor."""

BUDGET = 1000.0           # points allocated per night; resets, never a balance
MAX_PICKS = 7
MIN_ALLOCATION = 50.0     # stops 1-point sprinkling across every category
BACKUP_FACTOR = 0.80      # starter did not play -> backup scores at 80%

MIN_FGA_FOR_TS = 8        # SLATE.md guardrail
MIN_MINUTES_FOR_PM = 15.0

BOOST_MIN = 1.0
BOOST_MAX = 2.5
MIN_NIGHTS_TO_TUNE = 20   # below this, seed_boost stands
