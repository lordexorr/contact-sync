# Contact Sync

A Home Assistant add-on that keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. Every change is shown for review first, and nothing is written to any account until you apply it.

## Status

**0.2.x — review.** It matches the same person across every account and shows every change a sync would make. It doesn't change any contacts yet.

| Stage | What it adds | Status |
|---|---|---|
| 1. Connection check | Reads every account and shows contact counts and errors | Done (0.1.x) |
| 2. Review page | Matches the same person across accounts and lists every change a sync would make; skip any change or pick between conflicting values | Done (0.2.x) |
| 3. Apply | Backs up every account, then makes the reviewed changes; a daily notification when changes are waiting | Next |

## Install

1. Copy this repository into a folder named `contact_sync` inside Home Assistant's `/addons` folder (for example over the Samba share add-on).
2. In Home Assistant, go to **Settings → Apps**, open the store, and choose **⋮ → Check for updates**. Contact Sync appears under **Local apps**; install it. (Older versions call apps "add-ons".)
3. Follow the setup steps on the add-on's **Documentation** tab — the same steps as [DOCS.md](DOCS.md).

## How it works

- **iCloud:** reads contacts over CardDAV, using an app-specific password for each Apple ID.
- **Google:** reads contacts through the Google People API, using an OAuth client you register in your own Google Cloud project. Each Google account signs in on Google's own page.
- Everything runs on your Home Assistant machine. Passwords and Google sign-ins stay in the add-on's configuration and private storage.

## Changes

See [CHANGELOG.md](CHANGELOG.md).
