"""firestore.rules, exercised against the emulator. Stdlib only.

    firebase emulators:exec --only firestore --project demo-slate \
        "python3 tests/rules_check.py"

Not collected by pytest (no test_ prefix): it needs Java and the emulator, and
the suite is meant to run offline. The emulator accepts unsigned tokens, and
the literal token "owner" bypasses rules, which is how fixtures get seeded.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT = "demo-slate"
HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
DOCS = f"projects/{PROJECT}/databases/(default)/documents"
BASE = f"http://{HOST}/v1/{DOCS}"


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def token(uid: str | None) -> str | None:
    if uid is None or uid == "owner":
        return uid
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({'sub': uid, 'user_id': uid})}."


def call(method: str, url: str, uid: str | None, body: dict | None = None) -> int:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token(uid):
        req.add_header("Authorization", f"Bearer {token(uid)}")
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as exc:
        return exc.code


def _value(v):
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_value(x) for x in v]}}
    if isinstance(v, dict) and "timestampValue" in v:
        return v
    return {"mapValue": {"fields": {k: _value(x) for k, x in v.items()}}}


def write(uid: str | None, path: str, data: dict, server_time: tuple[str, ...] = ()) -> int:
    """A full-document set, with `server_time` fields stamped by the server."""
    one = {"update": {"name": f"{DOCS}/{path}", "fields": {k: _value(v) for k, v in data.items()}}}
    if server_time:
        one["updateTransforms"] = [
            {"fieldPath": f, "setToServerValue": "REQUEST_TIME"} for f in server_time
        ]
    return call("POST", f"{BASE}:commit", uid, {"writes": [one]})


def read(uid: str | None, path: str) -> int:
    return call("GET", f"{BASE}/{path}", uid)


CONV = "conversations/alice__bob"
PREVIEW = {
    "participants": ["alice", "bob"],
    "names": {"alice": "Alice", "bob": "Bob"},
    "lastMessage": "hi",
    "lastSenderId": "alice",
}


def preview(**changes) -> dict:
    return {**PREVIEW, **changes}


def main() -> int:
    failures = []

    def check(label: str, got: int, allowed: bool) -> None:
        ok = (got == 200) == allowed
        print(f"{'ok  ' if ok else 'FAIL'} {label}: HTTP {got}, expected {'allow' if allowed else 'deny'}")
        if not ok:
            failures.append(label)

    stamp = ("lastMessageAt",)
    assert write("owner", "users/bob", {"display_name": "Bob"}) == 200

    check("signed-in user reads the directory", read("alice", "users/bob"), True)
    check("anonymous cannot read the directory", read(None, "users/bob"), False)
    check("a browser cannot write a profile", write("bob", "users/bob", {"display_name": "x"}), False)

    check("alice opens a thread with bob", write("alice", CONV, PREVIEW, stamp), True)
    check(
        "alice sends a message",
        write("alice", f"{CONV}/messages/m1", {"senderId": "alice", "text": "hi"}, ("createdAt",)),
        True,
    )
    check(
        "alice cannot send as bob",
        write("alice", f"{CONV}/messages/m2", {"senderId": "bob", "text": "hi"}, ("createdAt",)),
        False,
    )
    check("bob updates the preview", write("bob", CONV, preview(lastSenderId="bob", lastMessage="yo"), stamp), True)
    check("mallory cannot read the thread", read("mallory", CONV), False)
    check(
        "mallory cannot open a thread between two other people",
        write("mallory", "conversations/alice__carol", preview(participants=["alice", "carol"], names={}, lastSenderId="mallory"), stamp),
        False,
    )

    # What this file exists for: the preview is held to the same standard as a message.
    check("preview cannot be forged as the other person", write("bob", CONV, preview(lastSenderId="alice"), stamp), False)
    check(
        "names cannot gain a third party",
        write("bob", CONV, preview(lastSenderId="bob", names={"alice": "A", "bob": "B", "mallory": "M"}), stamp),
        False,
    )
    check("no extra fields", write("bob", CONV, preview(lastSenderId="bob", junk="x" * 5000), stamp), False)
    check("preview is bounded", write("bob", CONV, preview(lastSenderId="bob", lastMessage="x" * 141), stamp), False)
    check("names are bounded", write("bob", CONV, preview(lastSenderId="bob", names={"bob": "x" * 401}), stamp), False)
    check(
        "the timestamp is the server's, not the client's",
        write("bob", CONV, preview(lastSenderId="bob", lastMessageAt={"timestampValue": "2099-01-01T00:00:00Z"})),
        False,
    )
    check("participants are frozen", write("bob", CONV, preview(lastSenderId="bob", participants=["bob", "mallory"]), stamp), False)
    check("cards are not readable from a browser", read("alice", "cards/anything"), False)

    print(f"\n{len(failures)} failed" if failures else "\nall rules checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
