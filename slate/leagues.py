"""Invite codes -- the entire join flow.

There is no public browse and no discovery, so a code is the only way into a
league. That makes two properties non-negotiable: it has to survive being read
off one screen and typed into another, and it has to be unguessable enough
that nobody walks into someone else's league by accident.
"""
from __future__ import annotations

import secrets
from typing import Callable

# No 0/O and no 1/I/L. Those are the pairs that get mistyped when a code is
# read aloud or off a screenshot, and a wrong code here is a 404 with no way
# for the user to tell which character betrayed them.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6

# 31**6 ~= 8.9e8. Collisions are vanishingly unlikely and checked for anyway.
_ATTEMPTS = 8


def new_code() -> str:
    """A fresh code. `secrets`, not `random` -- guessing one joins a league."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def unique_code(taken: Callable[[str], bool]) -> str:
    """A code no league already holds.

    `taken(code)` is asked of the store rather than assumed, because the only
    place that knows is whatever is actually persisting leagues.
    """
    for _ in range(_ATTEMPTS):
        code = new_code()
        if not taken(code):
            return code
    raise RuntimeError("could not generate an unused invite code")
