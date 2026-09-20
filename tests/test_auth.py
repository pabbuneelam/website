"""Header parsing. Token verification itself is Google's code talking to
Google's signing keys -- there is nothing here worth mocking, and a test that
minted fake tokens would only assert that firebase-admin rejects them."""
from __future__ import annotations

import pytest

import jwt

from slate.auth import AuthError, bearer_token, dev_auth_enabled, verify


def test_a_bearer_header_yields_the_token():
    assert bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"


def test_the_scheme_is_case_insensitive():
    """Some clients send `bearer`; the RFC says the scheme is case-insensitive."""
    assert bearer_token("bearer abc") == "abc"


def test_surrounding_whitespace_is_ignored():
    assert bearer_token("Bearer   abc  ") == "abc"


@pytest.mark.parametrize("header", [None, "", "abc.def.ghi", "Basic abc", "Bearer", "Bearer   "])
def test_anything_that_is_not_a_bearer_token_is_refused(header):
    """Refusing loudly beats treating an unparseable header as anonymous --
    an endpoint that needs a uid has nothing to fall back to."""
    with pytest.raises(AuthError):
        bearer_token(header)


KEY = "k" * 32  # never verified; long enough to keep PyJWT quiet


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("SLATE_DEV_AUTH", "SLATE_FIREBASE_PROJECT", "VERCEL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_dev_auth_is_off_unless_asked_for(clean_env):
    assert dev_auth_enabled() is False


@pytest.mark.parametrize("real", ["SLATE_FIREBASE_PROJECT", "VERCEL"])
def test_dev_auth_refuses_to_run_next_to_a_real_deployment(clean_env, real):
    """The flag accepts unsigned tokens, so it must fail closed -- loudly --
    rather than be honoured or silently ignored on a real project."""
    clean_env.setenv("SLATE_DEV_AUTH", "1")
    clean_env.setenv(real, "1")
    with pytest.raises(RuntimeError):
        verify("anything")


def test_dev_auth_reads_the_identity_out_of_the_token(clean_env):
    clean_env.setenv("SLATE_DEV_AUTH", "1")
    token = jwt.encode({"user_id": "u1", "name": "Ada", "email": "a@x.io"}, KEY, algorithm="HS256")
    user = verify(token)
    assert (user.uid, user.display_name, user.email) == ("u1", "Ada", "a@x.io")


def test_dev_auth_still_rejects_a_token_that_is_not_a_jwt(clean_env):
    clean_env.setenv("SLATE_DEV_AUTH", "1")
    with pytest.raises(AuthError):
        verify("not-a-jwt")


def test_without_dev_auth_a_forged_token_is_refused(clean_env, monkeypatch):
    """The unsigned path must be unreachable by default. Firebase's own check
    is stubbed to reject, which also spares the test a credential lookup."""
    from firebase_admin import auth as fb_auth

    from slate import auth

    def reject(token, app=None):
        raise ValueError("signature check failed")

    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    monkeypatch.setattr(fb_auth, "verify_id_token", reject)
    forged = jwt.encode({"user_id": "attacker"}, KEY, algorithm="HS256")
    with pytest.raises(AuthError):
        verify(forged)
