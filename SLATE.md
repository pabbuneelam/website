# Slate (working title) — NBA Player Builder

**One line:** Build the best basketball player you can out of tonight's NBA performances, then use the players you create to build and manage a championship roster.

---

## The pitch

You are not drafting an NBA player. You are picking a different NBA player to supply each **quality** of one custom player you create.

- **Outside Shooting:** Curry
- **Finishing:** someone else
- **Playmaking:** someone else
- …and so on

What you actually receive depends entirely on how each of them plays *that night*. Curry hitting eight contested threes gives you elite Outside Shooting. Pick someone for defense who gets cooked, and your created player is a turnstile.

Two things make it more than a novelty:

1. **Ratings measure quality, not fantasy points.** Two players shoot 6/12 from three; the one taking contested pull-ups rates higher than the one getting open catch-and-shoot looks.
2. **Cost is the real contract.** Your card's salary is the *average* of the six real NBA salaries you used. That makes rookie deals and minimums the alpha, and turns every build into a value problem, not a star-picking problem.

---

## Status

| | |
|---|---|
| ✅ **Built** | Attribute engine, ratings, OVR, contract, card, API, persistence |
| ⬜ Next | Collection → roster + cap → waivers/FA → trades → simulation |

No prediction model is needed anywhere in this design. See *Ratings*, below.

---

## The six attributes

An initial version uses six, to keep a daily build quick. Each has a metric that exists in real data and a guardrail that keeps small samples out.

| Attribute | Metric | Guardrail |
|---|---|---|
| Outside Shooting | 3P points added over league average, × difficulty | min 4 3PA |
| Finishing | rim points added over league average, × difficulty | min 3 rim FGA |
| Playmaking | AST + ½ secondary + ½ FT assists − turnovers | min 15 minutes |
| Rebounding | boards over league-average conversion of the same chances | min 4 rebound chances |
| Perimeter Defense | FGs prevented vs the man he guarded + deflections | min 10 matchup minutes |
| Interior Defense | rim FGs prevented + blocks | min 3 rim FGA defended |

**Rebounding is the clearest illustration of the whole design.** Twelve boards from thirty chances is a worse night than eight from twelve. Volume stats reward opportunity; this rewards the player.

Later candidates: Midrange, Shot Creation, Off-Ball Movement, Screen Navigation, Decision Making. Each is a row in `slate/attributes.py` plus a metric function — the engine does not change.

---

## Ratings

```
value  = what he produced
       − what a league-average player produces on the same opportunities
       × how hard those opportunities were

rating = percentile of value among everyone who qualified tonight  ×  99
OVR    = mean of the six ratings
```

One idea, six instances.

**Ratings are absolute quality tonight, not "did he beat his own average."** This is a deliberate choice against the obvious alternative. A card joins a roster and eventually a simulator, so a 97 has to mean the performance was genuinely elite — a 99 off a 3-for-3 night would poison everything downstream. Stars therefore rate well more often, exactly as they should: picking a star means paying for a higher probability of a good night, and **the salary denominator is the balancing mechanism, not the scoring**.

Percentiles are bounded by construction, so ratings compare across nights and across attributes with no tuning. A player is counted in his own pool, so a perfect night caps just under 99 — deliberate, because it keeps ratings honest on a thin two-game slate.

A metric returning nothing — guardrail failed, or the data tier lacks the field — removes the player from that attribute's pool entirely *and* scores the pick zero.

### Difficulty

`contested_share` — the fraction of a player's shots that were contested — is the difficulty signal. Where it is absent it falls back to 1.0, neutral rather than zero, so an attribute degrades to plain efficiency instead of breaking.

Shot difficulty ratings, expected FG%, and closest-defender distance are Second Spectrum proprietary and not purchasable at any realistic price. The design works around them rather than pretending.

---

## Contracts

The created player's contract is the **average annual salary** of the six players used.

> $55M + $45M + $30M + $15M + $8M + $3M, over 6 = **$26M/year**
>
> **93 OVR · $26M/year · 3.58 OVR per $M**

A player with no salary on file is excluded from the average rather than counted as free — otherwise missing data would masquerade as a bargain.

---

## The daily loop

1. See tonight's games. Players are listed with team, opponent and salary — **no stats**.
2. Fill six attribute slots. One player supplies one quality; nobody fills two.
3. Selections lock at tip.
4. Games happen.
5. The engine rates each performance.
6. You get a card: ratings, OVR, contract, and the real performances behind every number.
7. The card joins your collection.

---

## The economy *(specced, not built)*

### Collection and roster

Cards persist. You build a starting five plus bench out of players you have created, under a team payroll limit.

### Cap penalties

Exceeding the cap is allowed but progressively punished — luxury tax, then apron levels, with restrictions on adding new players and reduced rewards. Over the cap is a strategic choice, not an invalid roster.

### Waiving and dead cap

Waiving retains **~20% of the contract as dead cap**. Waiving a $30M player frees $24M and leaves a $6M charge. Bad contracts have to be lived with or paid off.

### Player lifecycle

**Roster → Waivers → Free Agency → Retirement**

A waived player enters a short waiver period where another team can claim the existing contract. Unclaimed, he enters free agency, and his asking price falls each day. Unsigned after ~30 days, he retires. This is a waiting game: hold out for a lower price and someone else may sign him first.

Cards therefore outlive their creators' rosters, which is why a card carries a stable id and a recorded creator from the moment it is built.

### Career history

Original creator, date, the NBA players used, original contract, every team played for, free-agency spells, simulation stats, awards, retirement. A card created by one user can end up playing for several teams — persistent league history.

### Tradeable assets

1. **Created players**, with their contracts.
2. **Future build picks** — the right to create a player on a given future NBA game day. Nights with more games are worth more, so this is a draft-pick economy without a draft.
3. **Cap space** — temporary (+$10M for 15 days) or permanent (+$2M). Permanent must stay rare or the economy inflates.

> **Team A gets:** 94 OVR player
> **Team B gets:** 90 OVR player + Saturday build pick + $10M cap space for 15 days

### Simulation *(last)*

Possession-by-possession resolution using created players' attributes, with Monte Carlo runs behind a single official result. Then fit and chemistry — five high-usage scorers should underperform a balanced roster.

This is deliberately last. It needs full rosters to mean anything, and a bad simulator would discredit good attribute work.

---

## Data

| Tier | Price | Coverage |
|---|---|---|
| free | $0 | teams, players, games — **no player stats** |
| ALL-STAR | $9.99/mo | + box scores, injuries |
| GOAT | $39.99/mo | + advanced/tracking, matchups, play-by-play, odds, contracts |

**GOAT is required.** Four of six attributes depend on fields that exist only there. A 48-hour GOAT trial exists — one afternoon validates every attribute against a real slate before subscribing.

Nothing is paid for yet. Everything runs on a committed fixture with deliberately awkward rows.

---

## Open questions

- Is OVR a flat mean, or weighted by position once rosters exist?
- Do build picks need an expiry, or can a hoarder bank a season of them?
- Trades: player-for-player only, or is there a currency? A currency turns good predictors into farmers running a secondary market.
- League-average constants (`LEAGUE_3P`, `LEAGUE_RIM`, …) are guesses until a real season is loaded.
- Does one build per night per user hold, or do build picks make that variable?
