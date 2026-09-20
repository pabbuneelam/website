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

.venv/bin/python -m pytest
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
`/trades`, `/health`
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

**https://slate-demo-six.vercel.app** — `/docs` for the OpenAPI UI, `/health`
for which store is live. This is Vercel project `slate-demo`, backed by
Firestore. The SPA is a second project, `slate-ui`, built against it.

`slate-theta-two.vercel.app` is an older deploy of the same API with no
database behind it (`/health` reports `MemoryStore`), so every write there
503s. Do not point a frontend at it.

Vercel resolves the entrypoint from `[tool.vercel] entrypoint = "slate.api:app"`
in `pyproject.toml`. `vercel.json` trims tests and tooling but **must not
exclude `slate/fixtures/`** — that JSON is runtime data.

Writes 503 without a durable store, deliberately: serverless instances are
stateless, so a card written by one is invisible to the next. Failing loudly
beats behaving randomly.

```sh
vercel env add SLATE_FIREBASE_PROJECT production
base64 -i ~/.secrets/questly-sa.json | tr -d '\n' | vercel env add GOOGLE_APPLICATION_CREDENTIALS_B64 production

tools/deploy.sh api        # -> slate-demo
tools/deploy.sh ui         # -> slate-ui
```

`GOOGLE_APPLICATION_CREDENTIALS_B64` is preferred: a raw service-account JSON
carries a PEM key full of newlines and quotes, which platform env vars mangle.
`GOOGLE_APPLICATION_CREDENTIALS_JSON` also works but **must be minified to one
line**.

Deploy through `tools/deploy.sh`, not `vercel deploy` from the repo: the CLI
sees a git remote this Vercel account cannot access and the build stalls with
no logs (#10). The script stages a copy outside the repo.

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
trades/{trade_id}     one card offered for one card
```

A card carries a stable id and its creator from the moment it exists, because
it outlives the roster it was made for — waived, claimed, signed, traded,
retired. `uid` on a card is therefore its **current owner** and moves when it
is traded; the uid inside `card_id` and `creator_name` are the creator and
never move.

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
| needs a token | `POST /slates/{date}/builds`, `/cards/me`, `/users/me`, every `/leagues` and `/trades` route |

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
   picks a player — at both a desktop (1440×900) and a mobile (390×844)
   viewport. It screenshots every meaningful state, including one dropdown
   left **open** (the state that caught the real bug), into
   `tests/e2e/screenshots/`. It stops at the filled form: building a card and
   the collection need a Google sign-in, which a headless browser cannot do
   (#18).
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

## Messaging

1-on-1, plain text, real time. The browser talks to **Firestore directly**
through the client SDK — a message has to land on the other screen without
anyone pressing anything, and a poll against FastAPI is not that. The backend
is not in this path at all.

```
conversations/{a__b}                     the two participants + last-message preview
conversations/{a__b}/messages/{msgId}    one document per message
```

The conversation id is both uids **sorted and joined**, so "Alice messages Bob"
and "Bob messages Alice" are one thread rather than two half-empty ones. One
document per message, never an array on the conversation: an array is rewritten
whole on every send, races two senders against each other, and caps the thread
at the 1 MiB document limit. Ordering is `serverTimestamp()` — client clocks are
wrong by accident often, and on purpose easily. A thread opens with the latest
50 and nothing older.

Because there is no server in the path, **`firestore.rules` is the enforcement**:
only the two participants can read or write a conversation, `senderId` must
equal `request.auth.uid` on create, messages can never be updated or deleted,
and the max length is checked there rather than only in the input.

```sh
firebase deploy --only firestore:rules --project questly-7f3a2
```

Until those rules are live every listener fails with `permission-denied` — that
is the expected symptom, not a bug in the UI.

## Trades

**Card for card, between two members of the same league.** Propose, accept,
reject, cancel. No currency — a currency would let strong predictors farm cards
and sell them, which turns the game into a market rather than a prediction
contest. Build picks and cap space, the other two tradeable assets in
SLATE.md, are deliberately absent: a build is implicitly always allowed so
there is no entitlement to trade away, and with no roster and no payroll cap
there is nothing for "both sides must end cap-legal" to validate against. Both
drop in later as extra legs and one validation step.

| | |
|---|---|
| `POST /trades` | `{recipient_uid, offered_card_id, requested_card_id}` → the trade and both cards |
| `GET /trades` | `{incoming, outgoing}`, newest first, each with both cards attached |
| `POST /trades/{id}/accept` | recipient only; swaps both cards atomically |
| `POST /trades/{id}/reject` | recipient only |
| `POST /trades/{id}/cancel` | proposer only |

Four rules carry the whole feature:

- **Same league.** Both sides must hold a membership in the same league, so
  proposing to an outsider is a 409 that says so.
- **Ownership is checked twice.** At propose time for a legible error, and
  again *at accept time inside the transaction that writes the swap*. The
  second check is the one that matters: it is what stops one card being traded
  away twice by offering it to two people and having both accept.
- **The swap is all-or-nothing.** `FirestoreStore.accept_trade` reads the
  trade and both cards, decides, then writes all three documents in one
  `@firestore.transactional` — which retries if any of them moved underneath
  it. `MemoryStore` does the same under a lock, with every check and every
  replacement object computed before the first mutation, so the raising path
  writes nothing. A half-applied swap gives a card away without handing one
  back, and is the worst bug this feature could have.
- **Only the two parties act, and only once.** The recipient accepts or
  rejects, the proposer cancels, anyone else gets a 404 — a trade id is not
  something a bystander should be able to probe for. `accepted`, `rejected`
  and `cancelled` are all terminal; acting on one again is a 409.

**Leaving a league cancels your pending trades**, incoming and outgoing, with
`resolution_note` recording why. The alternative — leaving them open — would
let a trade complete between two people who are no longer leaguemates, which
is the one rule the feature exists to enforce. They are cancelled rather than
deleted so both sides can see what became of the offer.

One consequence worth naming: `card_id` is `"{date}:{uid}"` keyed on the
*creator*, and a traded card keeps its id. So rebuilding a night whose card
you have traded away is refused with a 409 rather than silently overwriting
that card in its new owner's collection.

Trades go through FastAPI on the Admin SDK, which bypasses security rules, so
`firestore.rules` needs no change — unlike messaging, no browser writes these
documents directly.

## Next

Collection → roster + payroll cap → waivers and free agency → trades (build
picks and cap space, now that card-for-card ships) → simulation. The economy
layer is specced in SLATE.md.
