"""Who is making this build.

Firebase Auth issues the identity; this module only verifies it. The frontend
signs in with Google, gets an ID token, and sends it as a bearer header. Here
that token is checked against Google's public keys and reduced to a uid.

The uid is the only identity the rest of the app trusts. A display name is
carried alongside it purely so a card can say who made it -- it is user-
controlled text and is never used as a key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .store import _credentials_json


@dataclass(frozen=True)
class AuthUser:
    """A verified Firebase identity."""

    uid: str
    display_name: str
    email: str | None = None
    photo_url: str | None = None


class AuthError(Exception):
    """The token was missing, malformed or not ours."""


# Built on first verification, never at import -- same reasoning as the store:
# the platform imports this module merely to find the ASGI app, and credential
# discovery at module scope hangs that.
_app = None


def _firebase_app():
    global _app
    if _app is None:
        import firebase_admin
        from firebase_admin import credentials

        raw = _credentials_json()
        if raw:
            import json

            cred = credentials.Certificate(json.loads(raw))
        elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
        else:
            cred = credentials.ApplicationDefault()

        # Verification needs a project id to check the token's audience. A
        # service-account file carries one; application-default credentials
        # often do not, and the failure there reads as a token problem rather
        # than a configuration one. Say it explicitly when we can.
        project = os.environ.get("SLATE_FIREBASE_PROJECT")
        options = {"projectId": project} if project else None
        try:
            _app = firebase_admin.initialize_app(cred, options, name="slate")
        except ValueError:
            # Already initialised by an earlier import in the same process.
            _app = firebase_admin.get_app("slate")
    return _app


def bearer_token(authorization: str | None) -> str:
    """The token out of an `Authorization: Bearer <token>` header."""
    if not authorization:
        raise AuthError("missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("expected 'Authorization: Bearer <idToken>'")
    return token.strip()


def dev_auth_enabled() -> bool:
    """Local-only escape hatch: `SLATE_DEV_AUTH=1` skips token verification.

    Exists so the UI can be exercised on a machine with no Firebase
    credentials. It fails *closed*: if the flag is set next to anything that
    marks a real deployment, that is a misconfiguration to surface, not a flag
    to quietly honour or quietly ignore.
    """
    if os.environ.get("SLATE_DEV_AUTH") != "1":
        return False
    if os.environ.get("SLATE_FIREBASE_PROJECT") or os.environ.get("VERCEL"):
        raise RuntimeError(
            "SLATE_DEV_AUTH=1 is set alongside SLATE_FIREBASE_PROJECT or VERCEL. "
            "Dev auth accepts unsigned tokens and must never run against a real "
            "project or deploy. Unset one of them."
        )
    return True


def _verify_unsigned(token: str) -> AuthUser:
    """Read the claims out of a token *without checking its signature*.

    Only reachable through `dev_auth_enabled()`. The browser's real Google
    sign-in still supplies the identity, so cards are attributed to the person
    at the keyboard; nothing about the token is trusted.
    """
    import jwt

    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise AuthError(f"dev auth: token is not a JWT: {exc}") from exc
    uid = claims.get("user_id") or claims.get("sub")
    if not uid:
        raise AuthError("dev auth: token carries no uid")
    return AuthUser(
        uid=uid,
        display_name=claims.get("name") or claims.get("email") or uid,
        email=claims.get("email"),
        photo_url=claims.get("picture"),
    )


def verify(token: str) -> AuthUser:
    """A Firebase ID token in, a verified identity out."""
    if dev_auth_enabled():
        return _verify_unsigned(token)

    from firebase_admin import auth as fb_auth

    try:
        claims = fb_auth.verify_id_token(token, app=_firebase_app())
    except Exception as exc:  # firebase-admin raises a family of these
        raise AuthError(f"invalid ID token: {exc}") from exc

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise AuthError("token carries no uid")
    return AuthUser(
        uid=uid,
        # Google always supplies a name, but a token from another provider
        # might not -- falling back to the email keeps cards attributable.
        display_name=claims.get("name") or claims.get("email") or uid,
        email=claims.get("email"),
        photo_url=claims.get("picture"),
    )
