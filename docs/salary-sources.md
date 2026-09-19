# Where salary data can and cannot come from

`tools/ingest_nba.py` gets box scores, tracking and hustle from stats.nba.com
for nothing. Salary is the one field it cannot get, and a card's contract is the
average of six real salaries, so this is load-bearing rather than cosmetic.

balldontlie has contracts but only on GOAT, $39.99/mo. This project stays at $0,
so the question is whether any **free** source exists whose **terms** allow a
web app to be built on it.

Everything below was checked by fetching it, on 2026-09-19, not by reading a
search result.

---

## The answer, short

**No free, general-purpose NBA salary feed exists that we may build on.** Every
site that publishes complete salaries either forbids exactly this use in its
terms or blocks automated requests outright. `tools/attach_salaries.py`
therefore takes a salary table as **input** rather than fetching one, and does
the part that is genuinely ours: joining a name string onto an NBA person id
without ever guessing.

---

## Ranked, by what was actually verified

### 1. Basketball-Reference — free and complete. **Terms forbid it, and it no longer carries 2025-26.**

Salary pages are public and `/contracts/` is not disallowed in
[robots.txt](https://www.basketball-reference.com/robots.txt) (crawl-delay 3).
robots.txt is not the whole story, though, and the Terms are unusually explicit.

Sports Reference's [Terms of Use](https://www.sports-reference.com/termsofuse.html)
§5 is generous in principle — "sharing, using, modifying, repackaging, or
publishing data found on individual SRL webpages is welcomed, whether for
commercial or non-commercial purposes", subject to credit. But their
[Data Use page](https://www.sports-reference.com/data_use.html) states the
conclusion in one sentence:

> This means that you should not create websites or tools based on data you
> scrape from Sports Reference or any of our sites.

That is this project, described exactly. Two further points close the door:

- "For some of our datasets, our licenses completely preclude any
  redistribution of the data." Salary data is licensed in, not produced by SR.
- Their [bot traffic page](https://www.sports-reference.com/bot-traffic.html)
  explains there is no API because "most of our data comes from third parties
  who sell the data to us. As part of our agreements with them we can not
  provide the data available as a download on our site."

Custom data requests start at $5,000. **Ruled out.** Note that SR themselves
point out that facts are not copyrightable — the barrier here is contract, not
copyright, and a contract we would be accepting by using the site.

Separately, and easy to miss:
`https://www.basketball-reference.com/contracts/players.html` is a
*forward-looking* page. It currently serves **2026-27** (518 rows, Curry
$62,587,158). It does not carry the 2025-26 figures our slates need at all.

### 2. Spotrac — the most complete contract data anywhere. **Blocked outright.**

`https://www.spotrac.com/robots.txt` returns **HTTP 403** from CloudFront
("Request blocked") to a plain scripted request, as does their terms page. The
site actively refuses non-browser traffic. Defeating that is both a terms
problem and the kind of "access data not intended for you" clause every site
has. **Ruled out**, and not a close call.

### 3. RealGM — free salary pages. **Blocked, and disallows AI agents by name.**

`https://basketball.realgm.com/nba/team-salaries/2026` returns **HTTP 403** to a
scripted request. Their [robots.txt](https://basketball.realgm.com/robots.txt)
has no blanket `Disallow: /` and a `crawl-delay: 2`, but explicitly disallows
`CCBot`, `anthropic-ai`, `Claude-Web`, `Bytespider` and friends. The intent is
not ambiguous. **Ruled out.**

### 4. HoopsHype — allowed by robots.txt, but the data is not there any more.

`https://www.hoopshype.com/robots.txt` has a permissive `User-agent: *` group
that does **not** disallow `/salaries/` (it disallows ~284 named AI crawlers
with `Disallow: /`, plus admin paths). So this one is not closed by robots.

It fails on the data instead:

- `https://www.hoopshype.com/salaries/players/` renders only the top ~20
  earners, and the columns are **2026-27 through 2029-30** — forward-looking
  contract years, not the 2025-26 season our slates are from.
- Per-season archive URLs are gone: `/salaries/players/2025-2026/` and
  `/salaries/2025-2026/` both **404**.
- Players are keyed by HoopsHype's own internal ids
  (`/salaries/players/nikola-jokic/830650/`), which are not NBA person ids, so
  it would be a name join regardless.

Getting a full season would mean ~550 individual player-page fetches for data
the site no longer presents as a season table. **Not usable**, on completeness
grounds, before the terms question even matters.

### 5. The NBA itself — publishes cap figures, not per-player salaries.

nba.com publishes league-wide thresholds only. For 2025-26: cap $154.647M, tax
$187.895M, minimum team salary $139.182M, first apron $195.945M, second apron
$207.824M. Those are genuinely public and genuinely free, and they are the
right basis for the roster/cap half of the design — but there is not one
player row anywhere on nba.com or pr.nba.com. `nba_api` likewise has no salary
field on any of its ~150 endpoints. **Does not exist.**

### 6. Wikidata — CC0, and effectively empty.

The only salary property is **P3618 (base salary)**. Querying
`https://query.wikidata.org/sparql` for basketball players with P3618 returns
**two statements, for all players, for all time** — one dated 2024, one an
undated junk value. CC0 is worth nothing when the data is not there.
**Ruled out on coverage.**

### 7. Re-published datasets (HuggingFace, Kaggle, GitHub CSV dumps)

These are easy to find, look clean, and should not be used. The reason is worth
stating plainly: **a CC0 or Apache label applied by an uploader does not
launder data they scraped from a source that forbade redistribution.** Nobody
can grant rights they never had. The test is not "what licence does the page
claim" but "where did the numbers come from, and was that source free to give
them away". Three concrete ones, all with real 2025-26 coverage:

| Dataset | 2025-26 rows | Stated licence | Actual provenance |
|---|---|---|---|
| HF `Mr-Bridge/nba-salary-cap-contracts-2016-2026` | 640 | `other` — "research and educational use"; "underlying rights … belong to their respective owners" | its own `source` column reads *"HoopsHype salaries GraphQL endpoint"* |
| Kaggle `deocheng/nba-data-1946-2026` | 648 (`player_contracts`) | **Apache 2.0** | its own description names *Basketball-Reference (… salaries …)* and *Spotrac* |
| GitHub `gabriel1200/site_Data` (`salary.csv`) | 387 | **none** — `"license": null`, all rights reserved | its `salary_scrape.py` docstring opens *"Spotrac NBA contract scraper"* and discusses working around Cloudflare 403s |

The Kaggle one is the most dangerous of the three, because an affirmatively
stated Apache 2.0 is more misleading than no licence at all. The HuggingFace
one is the most honest — it names its source in a column and limits itself to
research use, which a public web app is not. The GitHub one is the freshest and
is openly an unauthorised scrape of a site that 403s automated clients.

Also checked and empty of salaries: `sportsdataverse/hoopR-data` (no licence,
ESPN play-by-play only), `erikgregorywebb/datasets` (no licence, stale). The
~25 top GitHub hits for "nba salary" are all stale ML coursework built on old
HoopsHype/BBR scrapes. data.world requires an account.

### 8. Paid APIs, for completeness

balldontlie's contract endpoints are confirmed **GOAT only ($39.99/mo)** — free
and ALL-STAR tiers do not include them, and the 48-hour trial needs a card.
sportsdata.io's free trial is scoped to UEFA Champions League. api-sports.io's
NBA endpoints (games, standings, statistics, players, teams) have no contract
endpoint at any tier.

---

## The one genuine counter-argument, stated fairly

Sports Reference's own terms say *"copyright law is clear that facts cannot be
copyrighted, so you are free to reuse facts found on this site in accordance
with copyright laws."* A salary figure is a fact. The restriction that bites is
**contractual** — it binds a visitor to their site — and it targets bulk
scraping and competing databases. It does not obviously follow the numbers into
a third party's hands.

So there is a real argument that a small, credited, non-competing set of salary
facts is defensible. But that is a risk judgement, not a licence, and it is not
one a tool should make silently on someone's behalf. Hence the design below.

---

## What this means for the tool

```sh
.venv/bin/python tools/ingest_nba.py 2025-11-14 > /tmp/slate.json
.venv/bin/python tools/attach_salaries.py --salaries salaries.csv /tmp/slate.json > out.json
```

The table may be CSV or JSON. Column names are sniffed from the usual spellings
(`name`/`player`/`full_name`, `salary`/`cap_hit`/`amount`); `$51,415,938`,
`51415938.0` and `51415938` all parse. A bare `{"Nikola Jokic": 51415938}` JSON
object works too. The report goes to stderr, the slate to stdout.

`tools/attach_salaries.py` fills `salary` on an ingested slate from that table.
It deliberately does **not** bundle a fetcher for any of the sites above, and no
salary figures are committed to this repo.

That is not a cop-out; it puts the sourcing decision, and its licence, in the
hands of whoever runs it — and it leaves the tool useful the day a licensed
source does appear (a balldontlie GOAT subscription, a club/press feed, a
properly-sourced open dataset). Swapping sources becomes a different input
file, not a different tool.

### The join is the real work

Slate rows key on `player_id`, the stats.nba.com person id. Salary tables key on
a name string. The bridge is `nba_api.stats.static.players` — a player list that
ships **inside the nba_api package**, offline, no network call, no terms
attached, and already a dependency of the ingest step. On a real 9-game slate it
resolved **237 of 237** person ids to full names.

From there, two exact passes:

1. **Normalised full name.** Accents folded (`Dončić` → `doncic`,
   `Bogdanović` → `bogdanovic`), suffixes dropped (`Jr.`, `III`), punctuation
   removed (`P.J.`, `Jae'Sean`, `Karl-Anthony`).
2. **First initial + surname**, *only where that key is unique on both sides.*
   This is what catches "Nic Claxton" against "Nicolas Claxton".

The uniqueness guard is not theoretical. That same 9-game slate contained five
colliding initial-keys — `j|green`, `d|powell`, `m|bridges`, `t|mann`,
`k|johnson`. Without the guard, each is a coin flip on a real person's
contract.

There is no third pass. No edit distance, no token overlap, no nearest match.

### What it measures

The join was exercised against the real 2025-11-14 slate (9 games, 237 players)
with a control table built from the canonical roster and then deliberately
mangled the way real sources mangle names — accents stripped, `Jr.`/`III`
dropped, `Nicolas` shortened to `Nic` — with 10% of players withheld entirely:

```
matched 213/237 (89.9%)  exact=212 initial=1
```

213 of 213 names present in the table matched. The 24 misses are exactly the 24
withheld rows. **Zero false positives.** Output carried 237 rows, 213 filled,
24 `null`, **0 zeros**.

**No match rate against real salary figures is reported, because no source
exists that we may take real salary figures from.** The number above measures
the join, which is the part this repo owns; it does not measure how messy a
real source's name spellings are.

### Missing stays missing

An unmatched player keeps `salary: null` and is printed by name in the report.
`slate/card.py` already excludes nulls from the contract average, precisely so
that missing data cannot masquerade as a bargain. A `0` would be a lie about a
real person's pay and would hand the user a fake bargain card; `null` is
honest. The tool also refuses to pick when one name carries two different
figures (a mid-season trade, or two people) — it reports the conflict and
leaves the field null.
