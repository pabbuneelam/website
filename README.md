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

.venv/bin/python -m pytest                     # 114 tests
.venv/bin/python -m slate build 2025-11-14     # build a card from the fixture
.venv/bin/uvicorn slate.api:app --reload       # http://127.0.0.1:8000/docs
```

With the API running, in another shell:

```sh
cd frontend
npm install
npm run dev                                    # http://localhost:5173
```

The dev server proxies `/attributes`, `/slates`, `/cards`, `/users`, `/leagues`,
`/health`
straight to `127.0.0.1:8000` (see `frontend/vite.config.ts`) — no env vars
needed locally. For a production build against a deployed backend, set
`VITE_API_BASE` (see `frontend/.env.example`).

Building a card requires signing in — see **Accounts**, below.

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
| `slate/auth.py` | Firebase ID token in, verified uid out. |
| `slate/api.py` | The HTTP surface. Public reads, authenticated writes. |
| `tools/make_fixture.py` | Regenerates the committed fixture. Seeded. |

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
cards/{card_id}       one created player, id "{date}:{uid}"
users/{uid}           one signed-in person
leagues/{league_id}   one league, carrying its invite code
memberships/{uid}     which league that user is in
```

A card carries a stable id and its creator from the moment it exists, because
it outlives the roster it was made for — waived, claimed, signed, retired.

## Accounts

Sign-in is Google, through Firebase Auth on the same `questly-7f3a2` project.
The browser gets an ID token, sends it as `Authorization: Bearer <token>`, and
`slate/auth.py` verifies it server-side. **The uid is the only identity
anything is keyed on** — `creator` used to be a free-text box, so two people
typing `demo` were one user with one colliding `card_id`. A display name still
rides along on each card, but purely so the UI can say who made it.

| | |
|---|---|
| public | `/attributes`, `/slates/{date}`, `/cards/{uid}`, `/health` |
| needs a token | `POST /slates/{date}/builds`, `/cards/me`, `/users/me`, every `/leagues` route |

## Leagues

**A user belongs to exactly one league at a time.** No switcher, no team
layer: `uid` keys a membership exactly as it keys a card, so the rule is the
data shape rather than a check — `memberships/{uid}` has nowhere to put a
second one. Cards stay owned by the user; since a user is only ever in one
league, global and per-league ownership collapse into the same thing.

Joining is by **invite code** and nothing else — no public browse, no
discovery, no moderation surface. Codes are six characters drawn from
`23456789ABCDEFGHJKMNPQRSTUVWXYZ`: no `0`/`O` and no `1`/`I`/`L`, because a
code gets read off one screen and typed into another, and a mistyped one is a
404 that names no culprit. Generation asks the store whether a code is taken
and retries, so collisions cannot ship.

| | |
|---|---|
| `POST /leagues` | `{name}` → the league, its code, and you on the roster |
| `POST /leagues/join` | `{code}` → 404 on an unknown code, 409 if already in a league |
| `POST /leagues/leave` | 409 if there was nothing to leave |
| `GET /leagues/me` | your league and its members; `{"league": null}` when you are in none |

Joining while already in a league **fails with 409 rather than switching** —
a silent switch would strand whatever the old league knew about that user.
Not being in a league is an ordinary state, not an error, so `/leagues/me`
returns a null league instead of a 404 the frontend would have to tell apart
from real failures.

The web config in `frontend/src/firebase.ts` is public by design — a Firebase
web config identifies a project, it does not authorise anything. Verification
uses the service-account credentials the store already loads, so no new
secret is introduced.

**Manual step, once per project:** Firebase console → `questly-7f3a2` →
Build → Authentication → Sign-in method → Add new provider → **Google** →
enable, set a support email, Save. Then Authentication → Settings →
Authorized domains, and add any deploy domain (`localhost` is there by
default).

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
