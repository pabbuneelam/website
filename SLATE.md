# Slate (working title)

**One line:** Nightly NBA fantasy where you back the stats nerds actually argue about, and get paid on how far your guy beat his own number.

---

## The pitch

Fantasy basketball scores raw box score totals. Slate doesn't.

- **You don't draft a player, you draft *what he does*.** Back Klay for shooting and you're scored on his true shooting tonight, not his rebounds.
- **You're scored against the projection, not the box score.** A star hitting his usual 30 loses to a role player who blew past his 12. Stars stop being free wins; finding tonight's outlier is the whole skill.
- **Niche categories pay more,** because they're harder to call. Corner threes pay more than points.
- **Lineups are hidden until lock.** Everyone submits blind. The reveal is the show.

It's fantasy for people who read Cleaning the Glass, but percentile scoring keeps it readable for anyone.

---

## The nightly round

1. **Slate opens.** Every player in tonight's games is listed with team and opponent. No stats shown.
2. **Spend your budget.** You get a fixed number of points for the night. Spread them across up to 7 `(player, category)` picks — as lopsided as you like. A player can only fill one category, and a category can only be picked once.
3. **Name backups.** Each pick gets a backup. If the starter doesn't play, the backup scores at 80%. The discount is deliberate: checking the injury report stays a skill, not a free hedge.
4. **Lock at first tip.** Late scratches after lock count against you, same as real fantasy.
5. **Reveal.** All lineups in the group go public. Scores update live as box scores come in.
6. **Settle.** Final scores, group leaderboard updates, head-to-head result posted.

The budget is a **scoring weight, not a wallet.** Nothing is won or lost from a balance and it resets every night. That's what keeps a half-trained projection model from being farmable — a weak model makes the game duller, never unfair.

---

## Categories

Anything computable from a box score is free and explainable. Anything needing shot location costs money (see Data).

| Tier | Categories |
|---|---|
| **Basic** | Points, Rebounds, Assists, Steals, Blocks, Fewest turnovers |
| **Combo** | Steals+blocks, Assists−turnovers, True shooting %, Plus/minus, Game Score |
| **Location** *(not live yet)* | Corner threes, Wing threes, Left-side makes, Lobs finished |

Guardrails apply before anything is scored: true shooting needs 8 FGA, plus/minus needs 15 minutes. Fail one and you're not last in that category — you're **absent from it**, and the pick scores zero. That's what stops a 1-for-1 night from winning the shooting category.

### Formulas

- **TS%** = PTS / (2 × (FGA + 0.44 × FTA))
- **Game Score** = PTS + 0.4×FG − 0.7×FGA − 0.4×(FTA − FT) + 0.7×ORB + 0.3×DRB + STL + 0.7×AST + 0.7×BLK − 0.4×PF − TOV

---

## Scoring: percentile of residual

12 rebounds and 62% TS aren't on the same scale, and neither are two players who were expected to do very different things. So:

```
actual − projection             = residual      how much he beat his own number
residual / dispersion           = z             normalised, so categories compare
percentile of z among tonight   = multiplier    0 to 1, always
allocated × multiplier × boost  = score
```

Percentiles are bounded by construction, so a bad projection makes the night noisy but can never blow up the scale. The reveal reads naturally: *"Your shooter beat his projection by more than 94% of the league tonight."*

A player is counted in his own pool, so a perfect night caps just under 1.0 rather than at it. That's deliberate — it keeps the multiplier honest on thin two-game slates.

### Niche boosts, self-tuning

Each category carries a boost. It starts as a hand-set seed and, once 20 nights of history exist, becomes the spread of that category's normalised residuals: **if the model can't call it, it pays more.** As the model learns a category, its boost falls back toward 1.

The known weakness is that noise and difficulty look identical from there, so a coin-flip category would otherwise claim the top multiplier. Three guards: residuals are normalised, the result is clamped to [1.0, 2.5], and seeds hold through cold start. The real fix is to change what's measured — once there's user data, retarget it from "hardest to predict" to "widest spread among entrants", which is much closer to skill.

---

## Why people come back

- **Two touchpoints a day:** draft in the afternoon, sweat the games at night.
- **Weekly head-to-head.** Paired with one friend in the group, best cumulative score over the week.
- **Monthly ladder** with tiers. Promotion and relegation so a bad week costs something.
- **Takes.** Before lock you can publicly call one pick ("Klay cooks tonight"). Takes show on the reveal. Being loudly wrong is the loss condition, and it's free.
- **Streaks** for consecutive nights with a valid lineup submitted, not for winning.

---

## Modes

- **Open** (default): everyone allocates from the full slate, duplicates allowed. Casual.
- **Snake**: turn-based, no duplicate players across the group. For groups that want it cutthroat.
- **Replay**: run any past date. Used for the demo and for off-season play. **Working today.**

---

## Data

Verified against the balldontlie docs:

| Tier | Price | Coverage |
|---|---|---|
| free | $0 | teams, players, games — **no player stats at all** |
| ALL-STAR | $9.99/mo | + per-game box scores, injuries |
| GOAT | $39.99/mo | + play-by-play with `coordinate_x/y`, advanced stats, odds & props, contracts |

Consequences:

- **The free tier cannot run the game.** Basic and combo categories need ALL-STAR at minimum.
- **Every location category needs GOAT**, as does any betting-odds work. They ship declared but disabled, and flip on with a config change.
- **Play-by-play only exists from the 2025 season forward.** The "lean on previous seasons with decay" plan has a hard floor for niche categories — points have years of history, corner threes have one.
- **Contracts are a GOAT endpoint**, which retires the Spotrac scraping plan.
- There's a **48-hour GOAT trial** (5 req/min). One afternoon of it pulls a real slate with coordinates — enough to build and validate the location categories before committing to a subscription.

Nothing is paid for yet. Everything runs on a committed fixture.

---

## Open questions

- **Does contract-as-cost come back?** The original pitch priced players by their real salary under a cap. The points budget replaced that mechanic, but contract-as-cost was the cross-sport hook and the reason rookie deals were the alpha. It could return as a *second* constraint layered on the budget. Undecided, deliberately.
- Is plus/minus too noisy to feel skill-based, even normalised against its own projection?
- Should backups be per pick or one global bench?
- Budget of 1000 across up to 7 picks, minimum 50 per pick — all guesses, all need playtesting.
- Is there a version for other sports? Percentile-of-residual works anywhere there's a box score and a projection.

---

## Build order

1. ~~**Scoring engine.**~~ **Done** — percentiles, guardrails, backups, boosts, over a committed fixture. See [README](README.md).
2. **Draft screen.** Slate list, category picker, budget meter, backup picker.
3. **Reveal screen.** Percentile bars per pick, lineup comparison, Takes.
4. **Group + leaderboard.** Nightly, weekly H2H, monthly ladder.
5. **Live data.** Swap the fixture for the API.
6. **The model.** Opponent adjustment, similar-team clustering, injury context, market odds — all as new `Projector` implementations. Nothing downstream changes.

---

## Demo plan

The season starts late October. For an interview before then:

- Ship in **Replay** mode: pick the date, allocate, lock, watch the round resolve in 30 seconds. *(The engine half of this works now.)*
- Seed 3 to 4 fake group members with pre-built lineups so the reveal and leaderboard have something to show.
