# Contact Sync

A Home Assistant integration that keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. Every change is shown for review on its page in the sidebar first, and nothing is written to any account until you apply it.

- Checks every account once a day and whenever you ask, matches the same person across accounts, and lists every change a sync would make.
- You decide: skip any change, pick between values that differ, merge duplicates, and put people in groups.
- Applying backs up every account first, then makes only the changes you reviewed.
- Find, edit, add and delete a contact once, for every account.
- Entities for automations and dashboards: how many changes are waiting, when the accounts were last checked, and a button to check now.

iCloud is read and written over CardDAV, with an app-specific password for each Apple ID. Google is read and written through the Google People API, with an OAuth client you register in your own Google Cloud project, and each Google account signs in on Google's own page. Everything runs on your Home Assistant machine, and only administrators see Contact Sync's page.

## Install

Contact Sync needs Home Assistant 2026.11 or later.

1. In HACS, open the **⋮** menu, choose **Custom repositories**, and add `https://github.com/lordexorr/contact-sync` as an **Integration**.
2. Open **Contact Sync** in HACS and download it. While Contact Sync is in testing its releases are betas, which HACS lists once beta versions are shown for the repository.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and choose **Contact Sync**.

## Setup

### 1. An app-specific password for each iCloud account

1. Sign in at [account.apple.com](https://account.apple.com).
2. **Sign-In and Security → App-Specific Passwords**: create one named "Contact Sync".
3. Copy it. It looks like `abcd-efgh-ijkl-mnop`.

Changing an Apple ID's main password revokes its app-specific passwords. If that happens, create a new one and enter it with **Change label or password** on that account.

### 2. A Google app, once for every Google account

1. Create a project for Contact Sync:
   1. Open the [Google Cloud console](https://console.cloud.google.com) and sign in.
   2. Click the project picker at the top of the page (it shows the current project's name), then **New project**.
   3. Name it "Contact Sync" and click **Create**.
   4. Select the new project in the project picker. Every step below applies to whichever project is selected, so check that its name shows at the top before continuing.
2. **APIs & Services → Library**: find **Google People API** and enable it.
3. **OAuth consent screen** (it opens *Google Auth Platform*) → **Get started**: app name "Contact Sync", your email for support and contact, audience **External**.
4. **Branding**: Google won't publish the app until its app domain is filled in. Set **Application home page** and **Application privacy policy link** to pages you control (this repository's README works), leave the terms of service link blank, and add that site's domain (for example `github.com`) under **Authorized domains**. Leave **App logo** empty: uploading one means Google has to review the app before anyone can sign in. Save.
5. **Audience → Publish app**. Publishing status must read **In production**. In *Testing*, Google signs Contact Sync out every 7 days.
6. **Clients → Create client**: application type **Desktop app**, name "Contact Sync".
7. Copy the **Client ID** and **Client secret** before closing the dialog. Google shows the secret only once.

### 3. Add each account

Go to **Settings → Devices & services → Contact Sync**.

- **Add iCloud account:** a label of your choice (shown on Contact Sync's page), the Apple ID, and its app-specific password. Contact Sync signs in straight away, so a wrong Apple ID or password shows up at once.
- **Add Google account:** use a computer, since the copy-and-paste step is awkward on a phone. The first time, enter the Google app's client ID and secret. Then open the sign-in link and choose the account. Google warns that it hasn't verified the app: choose **Advanced**, then **Go to Contact Sync**, which is normal for an app you made yourself. Allow access to contacts, and if Google shows a checkbox for contacts, tick it. The browser ends on a "This site can't be reached" page. That's expected: copy the whole address from the address bar and paste it in.

Deleting an account deletes what was saved from it, and for a Google account cancels its sign-in at Google. To use a different Google app, choose **Reconfigure** on Contact Sync's entry; each Google account then needs adding again, because its sign-in belongs to the app.

### 4. Options

**Configure** on Contact Sync's entry sets the time of the daily check, and optionally a **Daily notification**: a notify entity or action, such as `notify.mobile_app_my_phone`. After each daily check it sends a message when changes or decisions are waiting or an account couldn't be read, and nothing otherwise.

Then open **Contact Sync** in the sidebar and press **Check now**. Each account should show its contact count.

## Using it

[DOCS.md](DOCS.md) covers the review, applying, backups and undoing a change, the Contacts pages, and what isn't synced.

## Entities

| Entity | |
|---|---|
| `sensor.contact_sync_changes_waiting` | The changes a sync would make. Its attributes count what's still to decide in the review: possible matches, values to choose, duplicates, extra details and contacts without a group. |
| `sensor.contact_sync_last_check` | When every account was last read. `accounts_not_read` lists any that couldn't be. |
| `button.contact_sync_check_now` | Checks every account now. |

## Changes

See [CHANGELOG.md](CHANGELOG.md).
