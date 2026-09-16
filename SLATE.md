# Slate (working title)

**One line:** Nightly NBA fantasy where you draft by category, pay with real contracts, and get scored on the stats nerds actually argue about.

---

## The pitch

Fantasy basketball scores raw box score totals and prices players by a made-up salary. Slate does neither.

- **Cost is the player's real contract.** Public, honest, and it turns the game into value hunting. Rookie deals and vet minimums are the alpha.
- **Scoring is category-specific and advanced.** You don't draft a player, you draft *what he does*. Pick Klay for shooting and you get scored on his true shooting percentage tonight, not his rebounds.
- **Lineups are hidden until lock.** Everyone submits blind. The reveal is the show.

It's fantasy for people who read Cleaning the Glass, but the percentile scoring makes it readable for anyone.

---

## The nightly round

1. **Slate opens.** Every player in tonight's games is listed with team and annual contract. No stats shown.
2. **Fill the slots.** One player per category slot, under a salary cap. A player can only fill one slot.
3. **Name backups.** Each slot gets a backup. If the starter does not play, the backup scores at 80%. The discount is deliberate: checking the injury report stays a skill, not a free hedge.
4. **Lock at first tip.** Late scratches after lock count against you, same as real fantasy.
5. **Reveal.** All lineups in the group go public. Scores update live as box scores come in.
6. **Settle.** Final scores, group leaderboard updates, head-to-head result posted.

---

## Slots and metrics

Every metric is computable from a standard box score. That keeps the data free and makes every number on the reveal screen explainable.

| Slot | Metric | Guardrail |
|---|---|---|
| Bucket | Points | none |
| Shooter | True shooting % | min 8 FGA, otherwise scores 0 |
| Playmaker | Assists minus turnovers | none |
| Glass | Rebounds | none |
| Stopper | Steals + blocks | none |
| Impact | Plus/minus | min 15 minutes |
| Flex | Game Score (Hollinger) | none |

Slot count can scale with slate size: 5 slots on a 2-game night, all 7 on a full slate.

### Formulas

- **TS%** = PTS / (2 × (FGA + 0.44 × FTA))
- **Game Score** = PTS + 0.4×FG − 0.7×FGA − 0.4×(FTA − FT) + 0.7×ORB + 0.3×DRB + STL + 0.7×AST + 0.7×BLK − 0.4×PF − TOV

---

## Scoring: percentiles, not raw numbers

12 rebounds and 62% TS are not on the same scale, so summing raw metrics is meaningless. Instead:

- Each slot scores as the player's **percentile among everyone who played tonight** in that metric.
- Every slot is 0 to 100. A 7-slot lineup is out of 700.
- The reveal reads naturally: "Your Shooter was 94th percentile tonight."

Guardrails (min attempts, min minutes) apply before the percentile is computed, so a 1-for-1 night can't win the Shooter slot.

---

## Salary cap

- Cap = a fixed share of the total salary in tonight's pool (start at 20%, tune from there). This keeps a 2-game night and a 14-game night equally tight.
- Over the cap = lineup is void. No partial credit.
- **Points per dollar** gets its own leaderboard. "Best value drafter this month" is a title people will chase.

---

## Why people come back

- **Two touchpoints a day** built into the loop: draft in the afternoon, sweat the games at night.
- **Weekly head-to-head.** Paired with one friend in the group, best cumulative score over the week.
- **Monthly ladder** with tiers. Promotion and relegation so a bad week costs something.
- **Takes.** Before lock you can publicly call one pick ("Klay cooks tonight"). Takes show on the reveal. Being loudly wrong is the loss condition, and it's free.
- **Streaks** for consecutive nights with a valid lineup submitted, not for winning.

---

## Modes

- **Open** (default): everyone drafts from the full slate, duplicates allowed. Casual.
- **Snake**: turn-based draft, no duplicates. For groups that want it cutthroat.
- **Replay**: run any past date. Used for the demo and for off-season play.

---

## Data

| Need | Source | Notes |
|---|---|---|
| Tonight's games and box scores | balldontlie (free tier, API key) | Verify the free tier still covers per-game player stats and check rate limits before building on it |
| Player contracts | Spotrac / Basketball Reference | Scraped, not an API. Static JSON for this season is fine for a demo |
| Injury report | NBA official injury report | PDF, updated through the day. Manual or scraped; phase 2 |

Stay away from anything needing play-by-play or on/off data. Per-game advanced metrics are noisy; that's fine for a game, but don't market it as "true impact."

---

## Demo plan

The season starts late October. For an interview before then:

- Store one full slate from last season (games, box scores, contracts) as JSON.
- Ship in **Replay** mode: pick the date, draft, lock, and watch the round resolve in 30 seconds.
- Seed 3 to 4 fake group members with pre-built lineups so the reveal and leaderboard have something to show.

---

## Build order

1. **Scoring engine** over a saved box score JSON. Percentiles, guardrails, backups. This is the part you must be able to explain.
2. **Draft screen.** Slate list, slot picker, cap meter, backup picker.
3. **Reveal screen.** Percentile bars per slot, lineup comparison, Takes.
4. **Group + leaderboard.** Nightly, weekly H2H, monthly ladder, points per dollar.
5. **Live data.** Swap the JSON for the API.

---

## Open questions

- Does the Impact slot (plus/minus) survive playtesting, or is it too noisy to feel skill-based?
- Should backups be per slot or one global bench?
- Cap share: 20% is a guess. Needs tuning against real slates.
- Is there a version for other sports? Contract-as-cost works anywhere salaries are public.
