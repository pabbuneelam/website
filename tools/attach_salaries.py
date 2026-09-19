"""Fill in `salary` on an ingested slate from a salary table.

    python tools/attach_salaries.py --salaries salaries.csv /tmp/slate.json > out.json

`tools/ingest_nba.py` writes every box score row with `"salary": null`, because
stats.nba.com publishes performance, not payroll. This fills that field in.

WHY THIS TOOL TAKES A FILE INSTEAD OF SCRAPING A SITE
-----------------------------------------------------
There is no free NBA salary source whose terms permit building on it. That was
researched rather than assumed -- see `docs/salary-sources.md`. Briefly:
Basketball-Reference's own data-use page says "you should not create websites
or tools based on data you scrape from Sports Reference"; Spotrac and RealGM
return 403 to any non-browser client; HoopsHype no longer publishes a past
season; the NBA publishes cap thresholds but not player salaries; Wikidata has
two salary statements in total; and every open-licensed dataset with real
coverage is a relabelled scrape of one of the above.

So this tool bundles no scraper. It takes a salary table you have obtained
yourself, under whatever terms you obtained it, and does the part that is
actually hard and actually ours: **joining a name string onto an NBA person id
without ever guessing.** The day a licensed source appears -- a balldontlie
GOAT subscription, a press feed, a properly-sourced dataset -- that is a
different input file, not a different tool.

THE JOIN
--------
Slate rows key on `player_id`, the stats.nba.com person id. Salary tables key
on a name string. The bridge is `nba_api.stats.static.players`, a player list
that ships inside the nba_api package -- offline, no network, no terms, already
a dependency of the ingest tool.

Two passes, both exact, neither fuzzy:

  1. normalised full name   -- accents folded, suffixes dropped, punctuation
                               removed. Catches Doncic/Doncic, Porter Jr.
  2. first initial + surname -- but ONLY where that key is unique on both
                               sides. Catches "Nic Claxton" vs "Nicolas
                               Claxton" without ever risking two J. Williamses.

There is deliberately no third pass. No edit distance, no token overlap, no
"closest match". These are real people's contracts: an unmatched player stays
`null` and gets named in the report, which `slate/card.py` already handles by
excluding him from the contract average. A wrong salary would silently
mis-price a card and libel a payroll. Unmatched is fine; wrong is not.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalise(name: str) -> str:
    """'Nikola Jokic' / 'Michael Porter Jr.' -> 'nikola jokic' / 'michael porter'.

    Accents are folded rather than transliterated, so the NBA's 'Jokic' and a
    table's 'Jokic' land on the same key. Suffixes go because sources disagree
    about them far more often than two players in one night differ only by one.
    """
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z ]", " ", text)  # drops . ' - and the rest
    parts = [p for p in text.split() if p and p not in SUFFIXES]
    return " ".join(parts)


def initial_key(normalised: str) -> str | None:
    """'nicolas claxton' -> 'n|claxton'. None when there is no surname to use."""
    parts = normalised.split()
    return f"{parts[0][0]}|{parts[-1]}" if len(parts) >= 2 else None


def load_table(path: str) -> dict[str, list[int]]:
    """name -> the salaries seen under it. CSV or JSON; a list of values because
    a traded player often appears once per team and that has to be visible."""
    raw: list[tuple[str, str]] = []
    if path.endswith(".json"):
        data = json.load(open(path, encoding="utf-8"))
        rows = data.values() if isinstance(data, dict) else data
        if isinstance(data, dict) and not isinstance(next(iter(rows), None), dict):
            raw = list(data.items())  # {"Nikola Jokic": 51415938}
        else:
            raw = [(pick(r, NAME_COLS), pick(r, SALARY_COLS)) for r in rows]
    else:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            raw = [(pick(r, NAME_COLS), pick(r, SALARY_COLS)) for r in csv.DictReader(fh)]

    table: dict[str, list[int]] = defaultdict(list)
    for name, salary in raw:
        amount = money(salary)
        if name and amount is not None:
            table[normalise(name)].append(amount)
    return dict(table)


NAME_COLS = ("name", "player", "player_name", "full_name", "playername")
SALARY_COLS = ("salary", "amount", "annual_salary", "cap_hit", "pay", "value")


def pick(row: dict, candidates: tuple[str, ...]):
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in candidates:
        if lowered.get(key) not in (None, ""):
            return lowered[key]
    return None


def money(value) -> int | None:
    """'$51,415,938' / '51415938.0' / 51415938 -> 51415938. Never 0-for-missing."""
    if value is None:
        return None
    digits = re.sub(r"[^0-9.]", "", str(value))
    if not digits:
        return None
    try:
        amount = int(round(float(digits)))
    except ValueError:
        return None
    return amount if amount > 0 else None


def canonical_names(player_ids) -> dict[int, str]:
    """person id -> full name, from the list bundled inside nba_api."""
    from nba_api.stats.static import players

    everyone = {int(p["id"]): p["full_name"] for p in players.get_players()}
    return {pid: everyone[pid] for pid in player_ids if pid in everyone}


def attach(slate: dict, table: dict[str, list[int]]) -> dict:
    """Fills salaries in place; returns a report. Nothing is ever guessed."""
    rows = slate.get("boxscores", [])
    ids = {int(r["player_id"]) for r in rows}
    names = canonical_names(ids)

    # Ambiguity is decided once, up front, on both sides of the join.
    slate_by_initial: dict[str, set[int]] = defaultdict(set)
    for pid, name in names.items():
        key = initial_key(normalise(name))
        if key:
            slate_by_initial[key].add(pid)

    table_by_initial: dict[str, set[str]] = defaultdict(set)
    for norm in table:
        key = initial_key(norm)
        if key:
            table_by_initial[key].add(norm)

    matched: dict[int, int] = {}
    report = {"exact": 0, "initial": 0, "no_name": [], "unmatched": [], "conflicting": []}

    for pid in sorted(ids):
        name = names.get(pid)
        if not name:
            # nba_api's bundled list is a release-time snapshot, so a player who
            # debuted after it was cut has no name here at all.
            report["no_name"].append(pid)
            continue
        norm = normalise(name)

        hit, how = table.get(norm), "exact"
        if hit is None:
            key = initial_key(norm)
            # Unique on BOTH sides or not at all. One 'j|williams' in the salary
            # table is worthless if tonight's slate has three of them.
            if key and len(slate_by_initial.get(key, ())) == 1 and len(table_by_initial.get(key, ())) == 1:
                hit, how = table[next(iter(table_by_initial[key]))], "initial"

        if hit is None:
            report["unmatched"].append((pid, name))
        elif len(set(hit)) > 1:
            # Same name, two different figures -- a trade split across teams, or
            # two people. Either way this tool is not the one to decide.
            report["conflicting"].append((pid, name, sorted(set(hit))))
        else:
            matched[pid] = hit[0]
            report[how] += 1

    for row in rows:
        row["salary"] = matched.get(int(row["player_id"]))

    report["players"] = len(ids)
    report["matched"] = len(matched)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slate", help="ingested slate JSON, or - for stdin")
    ap.add_argument("--salaries", required=True, help="CSV or JSON of name -> annual salary")
    ap.add_argument("--min-match", type=float, default=0.0,
                    help="exit non-zero if the match rate falls below this (0-1)")
    args = ap.parse_args()

    slate = json.load(sys.stdin if args.slate == "-" else open(args.slate, encoding="utf-8"))
    report = attach(slate, load_table(args.salaries))

    total = report["players"] or 1
    rate = report["matched"] / total
    say = lambda *a: print(*a, file=sys.stderr)  # noqa: E731 - stdout is the slate
    say(f"matched {report['matched']}/{report['players']} ({rate:.1%})  "
        f"exact={report['exact']} initial={report['initial']}")
    for pid, name in report["unmatched"]:
        say(f"  unmatched  {pid:>8}  {name}")
    for pid, name, amounts in report["conflicting"]:
        say(f"  ambiguous  {pid:>8}  {name}  {amounts}  -> left null")
    for pid in report["no_name"]:
        say(f"  no name in nba_api's bundled roster: {pid}  -> left null")

    print(json.dumps(slate, indent=1))
    return 1 if rate < args.min_match else 0


if __name__ == "__main__":
    raise SystemExit(main())
