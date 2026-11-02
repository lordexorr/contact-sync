# Contact Sync

Keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. It checks once a day and whenever you press **Check now**, and writes nothing to any account until you review the changes and apply them yourself. Every account is backed up before anything is written.

## Setup

### 1. Apple app-specific password (each iCloud account)

1. Sign in at [account.apple.com](https://account.apple.com).
2. **Sign-In and Security → App-Specific Passwords**: create one named "Contact Sync".
3. Copy it. It looks like `abcd-efgh-ijkl-mnop`.

Changing an Apple ID's main password revokes its app-specific passwords. If that happens, create a new one and add the account again on the Contact Sync page with it.

### 2. Google app (an OAuth client, set up once for every Google account)

1. Create a project for Contact Sync:
   1. Open the [Google Cloud console](https://console.cloud.google.com) and sign in.
   2. Click the project picker at the top of the page (it shows the current project's name), then **New project**.
   3. Name it "Contact Sync" and click **Create**.
   4. Select the new project in the project picker. Every step below applies to whichever project is selected, so check that its name shows at the top before continuing.
2. **APIs & Services → Library**: find **Google People API** and enable it.
3. **OAuth consent screen** (it opens *Google Auth Platform*) → **Get started**: app name "Contact Sync", your email for support and contact, audience **External**.
4. **Branding**: Google won't publish the app until its app domain is filled in. Set **Application home page** and **Application privacy policy link** to pages you control (your copy of this repository works, for example its README), leave the terms of service link blank, and add that site's domain (for example `github.com`) under **Authorized domains**. Leave **App logo** empty: uploading one means Google has to review the app before anyone can sign in. Save.
5. **Audience → Publish app**. Publishing status must read **In production**. In *Testing*, Google signs Contact Sync out every 7 days.
6. **Clients → Create client**: application type **Desktop app**, name "Contact Sync".
7. Copy the **Client ID** and **Client secret** before closing the dialog. Google shows the secret only once.

### 3. Start the add-on and save the Google app

On the **Info** tab, turn on **Show in sidebar**, and start the add-on. Open **Contact Sync** in the sidebar, open **Manage accounts**, and under **Google accounts** enter the client ID and secret, then press **Save the Google app**. Once saved, it folds away; open it to change it, but changing the app means connecting each Google account again.

On the **Configuration** tab you can change the daily check time, and optionally set **Daily notification** to a notify entity or service, such as `notify.mobile_app_my_phone` or an email notifier. After each daily check it sends a message when changes are waiting or an account couldn't be read, and nothing otherwise.

### 4. Add each iCloud account

Open **Contact Sync** in the sidebar and open **Manage accounts**. Under **iCloud accounts**, enter a label of your choice (shown on the page), the Apple ID, and its app-specific password, then press **Add an iCloud account**. Contact Sync signs in straight away, so a wrong Apple ID or password shows up at once. Repeat for each iCloud account. To change an account's password, add it again with the new one; **Remove** forgets an account and deletes what was saved from it.

### 5. Connect each Google account

Use a computer for this. The copy-and-paste step is awkward on a phone.

1. Open **Contact Sync** in the sidebar, open **Manage accounts**, and press **Connect a Google account**.
2. Open the sign-in link and choose the account. Google warns that it hasn't verified the app: choose **Advanced**, then **Go to Contact Sync**. The warning is normal for an app you made yourself.
3. Allow access to contacts. If Google shows a checkbox for contacts, make sure it's ticked.
4. The browser ends on a "This site can't be reached" page. That's expected. Copy the whole address from the address bar, paste it into Contact Sync, and press **Connect**.
5. Repeat for each Google account.

**Disconnect** forgets a Google account, deletes what was saved from it, and cancels its sign-in at Google.

Then press **Check now**. Each account should show its contact count.

## Reviewing changes

After each check, the **Review** section just below **Check now** counts what a sync would change. **Open the review** shows the details.

- **Possible matches:** two contacts that might be the same person: the same name twice in one account, the same name with different phone numbers, emails or birthdays, or the same phone number or email address under different names. Each side shows everything that copy holds. Choose **Same person** or **Different people**, and the card moves to a collapsed **Decided** section, where you can change the answer.
- **Different values:** a name, nickname, company, job title, birthday, note or photo that differs between accounts. Pick the value every account should have, and it moves to a collapsed **Decided** section. Until you pick, a value one account changed since the last sync is used over one left as it was; otherwise the value from the most recently changed contact. The one used is marked.
- **Changes:** a table for each person that differs between accounts. Each account has a column showing what it has now, and the **After sync** column shows what every account will have once you apply. Only details that differ get a row: a person missing from an account; a name, nickname, company, job title, birthday, note or photo; each kind of phone number, email, address, website or related name (for example "Work address"); and labels that differ, including odd ones like "PREF", with a dropdown to pick the label. The dropdown's last choice, **Custom…**, opens a box to type any label, such as "Facebook" or "Personal"; iCloud and Google both keep it as typed. Struck-through values would be replaced or removed, values marked + would be added, and the green **After sync** column is what every account ends up with.
  - Untick a row to leave every account as it is for that row. It moves to a collapsed **Ignored** section at the bottom, where ticking it again brings it back.
  - In a list, such as two different work addresses, untick a value in **After sync** to leave it out of every account; it's removed from any account that has it.
  - Groups get a table of their own, with each account's member count. Google labels count as groups.
  - **My Contacts (Google):** Google Contacts lists, and counts, only the contacts in its *My Contacts* group. A contact can end up only in a label instead, which some other sync tools do: it's in the account and Contact Sync reads it, but Google Contacts leaves it out of its main list and its count. That's why Google can show fewer contacts than Contact Sync. This row lists any such contacts in each Google account, and applying adds them to My Contacts.
  - A person waiting on a possible match has a note under their table instead of an **Apply just** button.
- **Duplicates within one account:** the same person more than once in one account, with every card shown side by side. **Merge into one** keeps the card with the most details, moves everything from the other cards onto it (including details Contact Sync doesn't otherwise use, such as dates, social profiles and messaging handles), and deletes the others when you apply. The person's table then has a **Duplicate cards** row, which you can untick. **Keep both** leaves them as they are. Either choice moves the card to a collapsed **Decided** section, where you can switch. Until you choose, applying leaves the extra cards alone. A same-name pair in one account first appears under **Possible matches**; answering **Same person** brings it here.
- **Start over** forgets every match, choice and skip.

Contacts are matched automatically when they share a phone number or email address and their names agree, or when they have the same name in different accounts and nothing contradicts it. A first or last name on its own counts, and a card with no name goes by its company, so a business entered as a first name in one account and as the company in another still matches. Contacts that were one person at the last apply stay matched, even after a name or number changes in one account. Being matched only means the copies are the same person: every difference between them still appears under **Changes**. Everything you choose is saved the moment you click it, and kept for later checks.

## Applying changes

Press **Apply changes…** at the bottom of the review to apply every ticked change, or **Apply just *name*…** under a person's table to apply only theirs, including their group changes. A page then shows, for each account, how many contacts it gains, has updated or deleted, and which groups it creates, deletes, joins or leaves. Pressing **Apply now** does this:

1. Checks every account again. If anything changed since that page opened, in an account or in the review, it stops without writing anything. If an account can't be read, it stops and says which and why.
2. Backs up every account (see below).
3. Makes the changes, touching only the details shown in the review. Everything else on each contact stays as it is, including details only one service has. Photos are copied at full size.
4. Checks again and records what every account now holds.

Applying one person is quicker: it reads, backs up and rechecks only that person's cards, plus the groups, instead of every contact. It stops only if something about that person changed. Everyone else in the review stays as the latest check found them.

The results page lists every change made and every one that wasn't, with the reason. A person with a failed change stays in the review, so applying again retries it. A change that was made but has something to check is flagged in a **Check** column: for example, an iCloud card saved with its photo left as it was, because the photo couldn't be downloaded. The Contact Sync page shows when changes were last applied, with a link back to these results.

- People in an unanswered possible match are left out until you answer it, so a sync can't create a second copy of someone.
- A duplicate card being merged is deleted only after everything on it has been added to the card kept. If that fails, it's left as it is.
- A value between accounts that you haven't picked uses the one marked in the review.

### Deletions

The record made after each apply is what lets later reviews tell a deletion from a detail that was never synced. When something an account held at the last apply is gone from it, the review proposes deleting it from the other accounts too, instead of copying it back:

- A deleted contact shows as a **Contact** row that deletes it from every account. Untick it to leave every account as it is.
- A deleted phone number, email, address, website or related name starts unticked in **After sync**, with a note saying where it was deleted. Tick it to keep it in every account instead.
- A cleared nickname, company, job title, birthday, note or photo shows as removed from every account. A name is never removed.
- A group deleted from one account, or a person taken out of a group, is deleted from or taken out of the group in the other accounts.

Until the first apply, nothing counts as deleted.

When more than 10 contacts have gone from one account since the last apply, that looks more like a glitch or a mistake than tidying up. The review shows a warning, and deleting those contacts from the other accounts starts unticked, so nothing goes until you tick each one.

### Backups

Before writing, Contact Sync saves a backup to `addon_configs/local_contact_sync/backups`. The last 10 backups are kept. Each is a folder named for the date and time it was made, such as `2026-11-01_14-05-12`. Applying everyone backs up every account. Applying one person backs up only their cards, and the folder name ends with theirs, such as `2026-11-01_14-05-12 Jane Smith`.

Each folder holds:

- `What changed.txt`, listing every change that apply made and every one it didn't, by contact and account. It's the way to find the backup from just before a change you want to undo.
- For each account, a `.vcf` file, which iCloud.com, Google Contacts and the Contacts apps can import, and a `.json` file with everything as the service sent it.
- Under `photos`, the full-size photo of every contact the apply changed or deleted, named after the person.

Importing a `.vcf` file adds its contacts as new ones, next to any already there.

## Where things are kept

| What | Where |
|---|---|
| Daily check time and notification | The add-on's Configuration tab |
| iCloud accounts and their app-specific passwords, the Google app's client ID and secret, Google sign-ins, last check results, your review decisions, the record of the last apply | The add-on's private storage |
| Raw contact snapshots from the latest check | `addon_configs/local_contact_sync/snapshots` on the Samba share |
| Backups made before each apply | `addon_configs/local_contact_sync/backups` on the Samba share |

The snapshots and backups are kept under `addon_configs`, outside the add-on's own folder, so contact data can never end up in the add-on's code or on GitHub. Home Assistant gives every add-on a folder there for files you can open.
