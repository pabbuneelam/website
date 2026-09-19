"""AI visual review of the screenshots captured by capture.spec.ts.

Usage:
    .venv/bin/python -m pip install -e ".[e2e]"   # once
    cd frontend && npm run dev                      # terminal 1
    .venv/bin/uvicorn slate.api:app --port 8000      # terminal 2
    cd tests/e2e && npm install && npx playwright install --with-deps chromium
    npx playwright test                              # terminal 3, writes screenshots/
    ../../.venv/bin/python review.py                 # reads ANTHROPIC_API_KEY, reviews them

Reads every PNG in tests/e2e/screenshots/, sends them to Claude in one
request, and asks for aesthetic/layout defects only -- not "does this
element exist" (Playwright's own assertions already cover that). Prints a
pass/fail line per screenshot and exits 1 if anything failed, so it can gate
CI if wired in later. If ANTHROPIC_API_KEY is unset, prints a clear skip
message and exits 0 -- screenshot capture must work standalone without an
API key.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# The motivating bug: an open dropdown rendered UNDERNEATH the slots below
# it. Every element was present in the DOM, so every existence assertion
# passed -- only the rendered pixels showed the menu buried behind other
# content. The prompt below is written to catch that whole class of defect,
# not just that one instance.
REVIEW_PROMPT = """\
You are reviewing screenshots of a web app called Slate for AESTHETIC and \
LAYOUT defects only. These screenshots were captured mid-flow by an \
automated test that already confirmed every element exists in the DOM and \
every expected interaction succeeded -- so do NOT report "element X is \
missing" or "button Y doesn't say the right text". That is already covered. \
Your job is to look at the rendered pixels and find defects that only show \
up visually.

Specifically look for:
- Overlapping elements (text over text, controls over other controls)
- Clipped, cut-off, or truncated text or content
- Contrast failures (text hard to read against its background)
- Misalignment (things that should line up but don't, ragged edges, \
  inconsistent spacing)
- Z-index / stacking bugs -- an overlay, dropdown, menu, or modal that \
  appears to render BEHIND or interleaved with content that should be below \
  it, instead of floating cleanly on top. This is a real bug we've hit \
  before: an open dropdown painted underneath the form fields below it \
  while everything was still technically present in the DOM. Look hard at \
  any screenshot with an open menu/dropdown for exactly this.
- Broken responsive behavior -- compare the desktop and mobile screenshots \
  of the same step (they share the same step number/name) and flag if \
  mobile content overflows its container, wraps badly, or elements collide \
  that don't on desktop.

The screenshots are named "<viewport>-<step-number>-<step-name>.png" where \
viewport is "desktop" or "mobile". Screenshots with the same step name are \
the same app state at different widths -- compare them to each other.

For EACH screenshot, output one entry. Respond with ONLY a JSON array \
(no prose before or after), where each entry is:
{
  "screenshot": "<filename>",
  "verdict": "PASS" or "FAIL",
  "issues": ["<short description of each defect found, empty if PASS>"]
}
"""


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "review.py: ANTHROPIC_API_KEY is not set -- skipping AI review.\n"
            "Screenshot capture still ran fine; set ANTHROPIC_API_KEY and "
            "rerun `python review.py` to get the AI defect review."
        )
        return 0

    if not SCREENSHOT_DIR.is_dir():
        print(f"review.py: no screenshots dir at {SCREENSHOT_DIR} -- run the "
              "Playwright test first (`npx playwright test` in tests/e2e/).")
        return 0

    images = sorted(SCREENSHOT_DIR.glob("*.png"))
    if not images:
        print(f"review.py: no .png files in {SCREENSHOT_DIR} -- run the "
              "Playwright test first (`npx playwright test` in tests/e2e/).")
        return 0

    try:
        import anthropic
    except ImportError:
        print(
            "review.py: the `anthropic` package is not installed.\n"
            'Install it with: .venv/bin/pip install -e ".[e2e]"'
        )
        return 0

    client = anthropic.Anthropic(api_key=api_key)

    content: list[dict] = []
    for image_path in images:
        content.append({"type": "text", "text": image_path.name})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(image_path.read_bytes()).decode("utf-8"),
                },
            }
        )
    content.append({"type": "text", "text": REVIEW_PROMPT})

    print(f"review.py: sending {len(images)} screenshots to Claude for review...")
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")

    try:
        # Model may still wrap the array in a fence despite instructions.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        results = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        print("review.py: could not parse a JSON verdict list -- raw response:\n")
        print(text)
        return 1

    failed = 0
    print(f"\n{'SCREENSHOT':45} VERDICT")
    print("-" * 60)
    for entry in results:
        verdict = entry.get("verdict", "?")
        name = entry.get("screenshot", "?")
        print(f"{name:45} {verdict}")
        for issue in entry.get("issues", []):
            print(f"    - {issue}")
        if verdict != "PASS":
            failed += 1

    print(f"\n{len(results)} screenshots reviewed, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
