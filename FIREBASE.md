# Firebase setup

Project: `questly-7f3a2` · [Console](https://console.firebase.google.com/project/questly-7f3a2)

- **Hosting** — serves repo root, `**` rewrites to `/questly.html`
- **Firestore** — one doc per user at `users/{uid}`, holds the whole game state
- **Auth** — anonymous today; Google later via `linkWithPopup` (same uid, no progress lost)

## Files

| File | Purpose |
|---|---|
| `.firebaserc` | project alias |
| `firebase.json` | hosting + rules config |
| `firestore.rules` | `users/{uid}` owner-only |
| `questly.html` | the app; Firebase config is inline in the module script |

## Deploy

```sh
firebase hosting:channel:deploy test --expires 30d   # test URL
firebase deploy --only hosting,firestore             # production
```

Test: https://questly-7f3a2--test-tll0a2r4.web.app
Prod: https://questly-7f3a2.web.app

## One-time console toggles

Not scriptable without `gcloud`:

1. [Firestore](https://console.firebase.google.com/project/questly-7f3a2/firestore) — create database, production mode, `nam5`
2. [Auth providers](https://console.firebase.google.com/project/questly-7f3a2/authentication/providers) — enable Anonymous (and Google when ready)

The `apiKey` in `questly.html` is public by design. Firestore rules are the actual guard.
