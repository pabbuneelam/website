# Slate

*Working title. The name lives in `slate/name.py` and nowhere else.*

Nightly NBA fantasy. You get a fixed points budget and spread it across
`(player, category)` picks — points, true shooting, assists minus turnovers,
corner threes. Picks score on how far the player beat **his own projection**,
ranked against everyone who played that night.

See [SLATE.md](SLATE.md) for the product design. This repo currently holds step
one of the build order: the scoring engine and a thin HTTP layer. No UI yet.

## Run it

```sh
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/python -m pytest                        # 65 tests
.venv/bin/python -m slate replay 2025-11-14       # resolve the stored slate
.venv/bin/uvicorn slate.api:app --reload          # http://127.0.0.1:8000/docs
```

## How scoring works

```
actual − projection            = residual
residual / dispersion          = z
percentile of z among tonight  = multiplier   (0..1, always)
allocated × multiplier × boost = score
```

Percentiles are bounded by construction, so a weak projector makes the game
noisy but can never blow up the scale — and because allocation is a scoring
weight rather than a wallet, nobody can farm a mispriced category.

A metric returning `None` — guardrail failed, or the data source has no
play-by-play — drops the player from that category's pool *and* scores the pick
zero. That is what stops a 1-for-1 night from winning true shooting.

## Persistence

Defaults to an in-memory store, so tests and Replay need no credentials. Point
it at Firebase and lineups plus nightly residuals become durable:

```sh
.venv/bin/pip install -e ".[firestore]"
export SLATE_FIREBASE_PROJECT=questly-7f3a2
export GOOGLE_APPLICATION_CREDENTIALS=~/.secrets/questly-sa.json
.venv/bin/uvicorn slate.api:app
```

`GET /health` reports which store is live, because a deploy that quietly fell
back to memory loses every lineup on restart.

```
slates/{date}/lineups/{entrant}   one submitted lineup
nights/{date}                     {residuals: {category_id: [z, ...]}}
```

That second collection is the point. The boost tuner holds its seed values
until 20 nights of residual history exist, and nothing accumulates across a
restart without it. Boosts for a night are computed from history *before* that
night — a slate never tunes the multipliers it is itself scored under.

Auth is a service account, so security rules are bypassed. Rules only start
mattering when a browser reads these collections directly.

## Layout

| Path | What it is |
|---|---|
| `slate/catalog.py` | Categories as data. Adding one is a row plus a metric. |
| `slate/metrics.py` | One pure function per metric, guardrails included. |
| `slate/project.py` | `Projector` protocol + `BaselineProjector`. **The ML seam.** |
| `slate/score.py` | Pools, residuals, percentiles, backups, validation. |
| `slate/tune.py` | Self-tuning niche boosts, clamped and seeded. |
| `slate/sources/` | `FixtureSource` today, `BallDontLieSource` stubbed. |
| `slate/store.py` | `MemoryStore` (default) and `FirestoreStore`. |
| `slate/api.py` | Five endpoints. |
| `tools/make_fixture.py` | Regenerates the committed fixture. Seeded. |

## Data tiers

Verified against the balldontlie docs:

| Tier | Price | Coverage |
|---|---|---|
| free | $0 | teams, players, games — **no player stats** |
| ALL-STAR | $9.99/mo | + box scores, injuries |
| GOAT | $39.99/mo | + play-by-play `coordinate_x/y`, advanced, odds, contracts |

Every location category (corner, wing, left side, lobs) needs GOAT, so they ship
declared but `enabled=False`. Play-by-play exists only from the 2025 season
forward — points have years of history, corner threes have one.

Nothing is paid for yet; everything runs on `slate/fixtures/2025-11-14.json`.

## Next

The ML projector, live ingestion, draft/reveal screens, groups and ladders, and
persistence. Each is its own milestone; none of them change `score.py`.
