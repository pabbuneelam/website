"""Header parsing. Token verification itself is Google's code talking to
Google's signing keys -- there is nothing here worth mocking, and a test that
minted fake tokens would only assert that firebase-admin rejects them."""
from __future__ import annotations

import pytest

from slate.auth import AuthError, bearer_token


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
