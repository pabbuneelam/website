# Slate

*Working title. The name lives in `slate/name.py` and nowhere else.*

Build a custom basketball player out of tonight's real NBA performances, then
use the players you create to build and manage a roster.

You don't draft a player — you pick a different NBA player for each **quality**
of one created player. Curry for Outside Shooting, someone else for Rebounding.
What you get depends entirely on how each of them plays *that night*. Your
card's contract is the **average of their six real salaries**, so a 94 OVR at
$14M is a better asset than a 96 at $50M.

See [SLATE.md](SLATE.md) for the full design. This repo holds the daily loop
— attribute engine → player card — plus a React frontend for it in
`frontend/`.

## Run it

```sh
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/python -m pytest                     # 79 tests
.venv/bin/python -m slate build 2025-11-14     # build a card from the fixture
.venv/bin/uvicorn slate.api:app --reload       # http://127.0.0.1:8000/docs
```

With the API running, in another shell:

```sh
cd frontend
npm install
npm run dev                                    # http://localhost:5173
```

The dev server proxies `/attributes`, `/slates`, `/cards`, `/health` straight
to `127.0.0.1:8000` (see `frontend/vite.config.ts`) — no env vars needed
locally. For a production build against a deployed backend, set
`VITE_API_BASE` (see `frontend/.env.example`).

```
  Slate — created 2025-11-14
  ──────────────────────────────────────────────
  OVR 96                       $27.8M/yr

  Outside Shooting     95   NYK Player 5       $3.5M
  Finishing            97   BOS Player 5       $3.5M
  Playmaking           97   BOS Player 1      $55.0M
  Rebounding           97   NYK Player 2      $38.0M
  Perimeter Defense    97   DEN Player 4      $12.0M
  Interior Defense     93   NYK Player 1      $55.0M
  ──────────────────────────────────────────────
  value: 3.45 OVR per $M/yr
```

## How a rating happens

Every attribute has the same shape — **one idea, six instances**:

```
value  = what he produced
       − what a league-average player produces on the same opportunities
       × how hard those opportunities were   (contested share)

rating = percentile of value among everyone who qualified tonight  ×  99
```

There is **no prediction model anywhere**. Ratings are absolute quality
tonight, not "did he beat his own average" — because a card joins a roster and
eventually a simulator, so a 97 has to mean the performance was genuinely
elite, not merely surprising. Stars rate well more often; the salary
denominator is what balances that.

Two consequences worth knowing:

- **Rebounding is conversion, not volume.** 8 boards from 12 chances rates
  above 12 from 30. Volume stats reward opportunity; this rewards the player.
- A metric returning `None` — guardrail failed, or the data tier lacks the
  field — drops the player from that attribute's pool *and* scores the pick 0.
  That's what stops a 3-for-3 night from buying a 99.

## Layout

| Path | What it is |
|---|---|
| `slate/attributes.py` | The six attributes and their metrics. Add one here. |
| `slate/score.py` | Pools, percentiles, ratings. |
| `slate/card.py` | Six selections → OVR, contract, card. |
| `slate/store.py` | `MemoryStore` (default) and `FirestoreStore`. |
| `slate/sources/` | `FixtureSource` today, `BallDontLieSource` stubbed. |
| `slate/api.py` | Five endpoints. |
| `tools/make_fixture.py` | Regenerates the committed fixture. Seeded. |
| `tools/ingest_nba.py` | Pulls one real slate from stats.nba.com. Free, offline. |
| `tools/attach_salaries.py` | Joins a salary table onto a slate by NBA person id. |

## Salaries

A card's contract is the average of six real salaries, so this field matters.
stats.nba.com does not publish it, and **no free source exists whose terms
permit building on it** — Basketball-Reference's data-use page says in so many
words not to build tools on scraped SR data, Spotrac and RealGM 403 every
non-browser client, HoopsHype no longer publishes past seasons, the NBA
publishes cap thresholds but not player pay, Wikidata has two salary statements
in total, and the open-licensed datasets that do have coverage are relabelled
scrapes of those same sites.

So `tools/attach_salaries.py` bundles no scraper. It takes a salary table you
supply and does the hard part — joining a name string onto an NBA person id via
the roster bundled inside `nba_api`, with two exact passes and no fuzzy
matching. Unmatched players stay `null`, never `0`, because `slate/card.py`
excludes nulls from the contract average so missing data cannot masquerade as a
bargain.

**[docs/salary-sources.md](docs/salary-sources.md)** has the full source-by-source
comparison, the terms quoted verbatim, and the measured match rate.

## Data tiers

Verified against the balldontlie docs:

| Tier | Price | Coverage |
|---|---|---|
| free | $0 | teams, players, games — **no player stats** |
| ALL-STAR | $9.99/mo | + box scores, injuries |
| GOAT | $39.99/mo | + advanced/tracking, matchups, play-by-play, odds, contracts |

**GOAT is required.** Four of the six attributes need fields that exist only
there: `rebound_chances_total`, `matchup_fg_pct`, `defended_at_rim_fg_pct`,
`contested_fga`/`uncontested_fga`, `secondary_assists`.

Not available at any price, and deliberately designed around: shot difficulty
ratings, expected FG%, closest-defender distance, pull-up vs catch-and-shoot,
potential assists, on/off. Contested share is the difficulty proxy that
replaces them.

There is a **48-hour GOAT trial** (5 req/min) — enough to pull one real slate
and validate every attribute before subscribing.

Nothing is paid for yet; everything runs on `slate/fixtures/2025-11-14.json`.

## Deployed

**https://slate-theta-two.vercel.app** — `/docs` for the OpenAPI UI.

Vercel resolves the entrypoint from `[tool.vercel] entrypoint = "slate.api:app"`
in `pyproject.toml`. `vercel.json` trims tests and tooling but **must not
exclude `slate/fixtures/`** — that JSON is runtime data.

Writes 503 without a durable store, deliberately: serverless instances are
stateless, so a card written by one is invisible to the next. Failing loudly
beats behaving randomly.

```sh
vercel env add SLATE_FIREBASE_PROJECT production
vercel env add GOOGLE_APPLICATION_CREDENTIALS_JSON production   # MINIFIED to one line
vercel deploy --prod
```

The credentials JSON **must be single-line**. A pretty-printed multi-line value
breaks the build environment.

## Persistence

```sh
export SLATE_FIREBASE_PROJECT=questly-7f3a2
export GOOGLE_APPLICATION_CREDENTIALS=~/.secrets/questly-sa.json
```

```
cards/{card_id}     one created player, id "{date}:{creator}"
```

A card carries a stable id and its creator from the moment it exists, because
it outlives the roster it was made for — waived, claimed, signed, retired.

## Visual QA (Playwright + AI review)

`tests/e2e/` drives the real UI in a browser and screenshots it, because DOM
existence assertions miss purely visual defects. This caught a real bug: an
open dropdown once rendered *underneath* the form slots below it, while every
element was still present in the DOM and every existence assertion passed —
only the rendered pixels showed it.

What it does:

1. `capture.spec.ts` loads the app, opens each of the six slot dropdowns and
   picks a player, enters a creator name, submits, waits for the card, and
   switches to the "My Collection" tab — at both a desktop (1440×900) and a
   mobile (390×844) viewport. It screenshots every meaningful state,
   including one dropdown left **open** (the state that caught the real bug),
   into `tests/e2e/screenshots/`.
2. `review.py` sends those screenshots to Claude and asks specifically for
   aesthetic/layout defects — overlap, clipping, contrast, misalignment,
   z-index/stacking bugs, broken responsive behavior — not existence checks.
   It prints a pass/fail verdict per screenshot with the specific issues
   found, and exits non-zero if anything failed.

Run it:

```sh
# once
.venv/bin/pip install -e ".[e2e]"
cd tests/e2e && npm install && npx playwright install --with-deps chromium

# terminal 1
.venv/bin/uvicorn slate.api:app --port 8000

# terminal 2
cd frontend && npm run dev

# terminal 3
cd tests/e2e
npx playwright test                # writes screenshots/
ANTHROPIC_API_KEY=sk-... ../../.venv/bin/python review.py
```

`review.py` reads its key from `ANTHROPIC_API_KEY`. If it's unset, it prints
a message and exits 0 — screenshot capture works standalone without an API
key; only the AI review step is skipped.

## Next

Collection → roster + payroll cap → waivers and free agency → trades (players,
build picks, cap space) → simulation. The economy layer is specced in SLATE.md.
