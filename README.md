# Contact Sync

A Home Assistant integration that keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. Every change is shown for review on its page in the sidebar first, and nothing is written to any account until you apply it.

- Checks every account once a day and whenever you ask, matches the same person across accounts, and lists every change a sync would make.
- You decide: skip any change, pick between values that differ, merge duplicates, and put people in groups.
- Applying backs up every account first, then makes only the changes you reviewed.
- Find, edit, add and delete a contact once, for every account.
- Entities for automations and dashboards: how many changes are waiting, when the accounts were last checked, and a button to check now.

iCloud is read and written over CardDAV, with an app-specific password for each Apple ID. Google is read and written through the Google People API, with an OAuth client you register in your own Google Cloud project, and each Google account signs in on Google's own page. Everything runs on your Home Assistant machine, and only administrators see Contact Sync's page.

## What it syncs

Every account ends up with exactly the same text. Capitals and punctuation count, so when two accounts write something differently, the review asks which way every account should write it. Stray spaces are removed without asking.

| Detail | How every account ends up |
|---|---|
| Name | The same name, in its parts: prefix, first, middle, last and suffix. A sync changes a name but never removes one. |
| Nickname, company, job title | One of each, written the same everywhere. Further companies and locations that only Google can hold are decided in the review. |
| Birthday | The same day. A birthday with a year and one without count as the same, and the year is kept. Two different years on the same day are asked about. |
| Notes | In full, with their line breaks. |
| Photo | The same picture. Photos are compared by what they show, so the same picture saved at another size or quality still counts as the same. It's copied at full size. |
| Phone numbers | US numbers as **(555) 555-0123**, whether they came with +1 or a leading 1, with dots or dashes, or as ten digits with no spacing. An extension stays on the end, as "(555) 555-0123 x12". Other countries' numbers, short numbers and numbers with letters in them stay as they are. |
| Email addresses | Compared without capitals, and written the same everywhere. |
| Addresses | **A US country is removed**: US, USA, U.S.A., United States or United States of America. An address with nothing else on it keeps it, and other countries stay. The same street and ZIP count as one address however they're written, so "Street" and "St", "North" and "N", "Apartment" and "Apt", or "NY" and "New York" are one address written two ways, and the review asks which wording to keep. |
| Websites | Compared without `http://` or `https://`, `www.`, capitals or a trailing slash. |
| Related names | Compared without capitals or punctuation. |
| Dates, such as an anniversary | Compared by day and month, so one with a year and one without are the same date. |
| Labels | Each phone number, email, address, website, related name and date keeps the label most accounts give it, such as mobile or work, preferring one changed since the last sync. The labels offered are the ones iCloud and Google both have, and **Custom…** types any other, which both keep as typed. Labels other sync tools leave behind, such as "PREF", "X-Personal" or "Email", count as no label, and one typed as "Fax" becomes other fax. |
| Order | A contact's phone numbers are listed in the same order in every account, and so are their emails, addresses, websites, related names and dates. The first in each list is the main one: Google marks it as primary and iCloud as preferred. |
| Groups | iCloud lists and Google labels, matched by name. A group is created in any account that lacks it, and someone taken out of a group in one account is taken out everywhere. Contacts that are only in a label are added to Google's **My Contacts**, so Google Contacts lists and counts them. |
| Show as company | iCloud's setting for showing a card as a company, kept the same between iCloud accounts. |

Delete a contact, or a detail such as a phone number, in any one account, for example on your iPhone, and the review offers to delete it from the other accounts too. Social profiles, messaging handles and details only one service has stay in each account as they are. [DOCS.md](DOCS.md) covers how contacts are matched, the review, and everything that isn't synced.

## Install

Contact Sync needs Home Assistant 2026.11 or later, and is installed through its Marketplace.

1. In the **Marketplace**, choose **Add from a GitHub link** and enter `https://github.com/lordexorr/contact-sync`, as an **Integration** if it asks.
2. Open **Contact Sync** in the Marketplace and download it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and choose **Contact Sync**.

The Marketplace offers each new version as an update. It looks for new versions of what was added from a GitHub link only every day or two, so to see one straight away, choose **⋮ → Refresh information** on Contact Sync's page there.

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

If Google stops accepting an account's sign-in, choose **Sign in again** on that account; everything saved from it stays. Deleting an account deletes what was saved from it, and for a Google account cancels its sign-in at Google. To use a different Google app, choose **Reconfigure** on Contact Sync's entry, then **Sign in again** on each Google account, because its sign-in belongs to the app.

When a check can't read an account, **Settings → Repairs** says which and why, until a check reads it again.

### 4. Options

**Configure** on Contact Sync's entry sets the time of the daily check, and optionally a **Daily notification**: a notify entity or action, such as `notify.mobile_app_my_phone`. After each daily check it sends a message when changes or decisions are waiting or an account couldn't be read, and nothing otherwise.

Then open **Contact Sync** in the sidebar and press **Check now**. Each account should show its contact count.

## Using it

Contact Sync's page in the sidebar shows each account's contact count and the review in brief, with **Check now**. **Open the review** lists every change a sync would make and everything there is to decide, such as possible matches and values that differ between accounts. **Apply changes…** then shows what changes in each account, and makes the changes after backing every account up. **Contacts** finds anyone, and edits, adds or deletes a contact for every account through the same Apply page.

[DOCS.md](DOCS.md) covers what syncs and how it's written, how contacts are matched, the review, applying, backups and undoing a change, the Contacts pages, and what isn't synced.

## Entities

On the Contact Sync device. Home Assistant chooses their entity IDs from the device's name, and sometimes its area.

| Entity | |
|---|---|
| **Changes Waiting** (sensor) | The changes a sync would make. Its attributes count what's still to decide in the review: possible matches, values to choose, duplicates, extra details and contacts without a group. |
| **Last Check** (sensor) | When every account was last read. `accounts_not_read` lists any that couldn't be. |
| **Check Now** (button) | Checks every account now. |

## Removing

Delete Contact Sync under **Settings → Devices & services**. That deletes what it keeps about everyone's contacts, in `.storage/contact_sync` and `contact_sync/snapshots` in the config folder, and cancels each Google account's sign-in at Google. The backups made before each apply stay in `contact_sync/backups`: delete that folder too once you no longer want them. Then remove Contact Sync in the Marketplace and restart Home Assistant. The Google app in your Google Cloud project and the app-specific passwords at account.apple.com stay until you delete them there.

## Changes

See [CHANGELOG.md](CHANGELOG.md).
