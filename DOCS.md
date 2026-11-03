# Contact Sync

Keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. It checks once a day and whenever you press **Check now**, and writes nothing to any account until you review the changes and apply them yourself. Each apply makes a backup before anything is written.

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

On the **Configuration** tab you can change the daily check time, and optionally set **Daily notification** to a notify entity or service, such as `notify.mobile_app_my_phone` or an email notifier. After each daily check it sends a message when changes or decisions are waiting or an account couldn't be read, and nothing otherwise.

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

After each check, the **Review** section just below **Check now** counts what a sync would change. **Open the review** shows the details. It's there even when nothing is waiting, with a count of what you've ignored and decided, so you can always go back and change those.

- **Possible matches:** two contacts that might be the same person: the same name twice in one account, the same name with different phone numbers, emails or birthdays, the same phone number or email address under different names or with different birthdays, or a card with little on it that could be either of two same-named people. Each side shows everything that copy holds. Choose **Same person** or **Different people**, and the card moves to a collapsed **Decided** section, where you can change the answer. **Different people** holds even if the two later share a phone number.
- **Details only Google can hold:** iCloud has room for one company and job title and no location, so a person's other companies and locations can't reach every account. For each person, choose the main company, which every account will show, and choose **Move to Notes** or **Delete** for every other detail. Nothing is chosen for you except that the company every account already shows stays the main one until you pick another, and then the old one needs a choice too. Moved details join the note as "Also: Company, Job title" or "Location: Place". An exact repeat of the main company shows under **Changes** as a row to remove it, without asking you to choose. Until everything about a person is chosen, these details stay as they are; their other changes still apply. Each backup keeps the originals.
- **Different values:** a name, nickname, company, job title, birthday, note or photo that differs between accounts, or a phone number, email, address, website, related name or date written differently, such as "NY" and "New York". Any difference counts, even capitals or punctuation, so every account ends up literally the same. Stray spaces show under **Changes** as a row to remove them, without asking you to pick a wording. Two birthdays on the same day with different years count; one without a year just takes the year. Pick the value every account should have, and it moves to a collapsed **Decided** section. Until you pick, a value one account changed since the last sync is used over one left as it was; otherwise the value from the most recently changed contact. The one used is marked. A pick lasts until the accounts agree. If a value changes after you picked, it's asked about again.
- **Not in a group:** anyone who isn't in a group (an iCloud list or Google label) in any account. Someone in a group in even one account isn't listed, because that group is copied to the others. Choose a group from the dropdown, or **New group…** to create one, and applying adds them to it in every account. Nothing is written until you apply, and until then they're listed as waiting on **Contacts**, the same as a group chosen on their form. **No group** says they don't need one. Either choice moves the card to a collapsed **Decided** section, where you can change it. **No group** holds unless they join a group and later leave it, when they're asked about again. For more than one group, use **Edit**. Until you choose, they count toward the number to decide on the Contact Sync page and in the daily notification. Someone waiting on a possible match isn't listed until it's answered, and a contact you add yourself is listed only once it's been applied, since its form has its own **Groups** section.
- **Changes:** a table for each person that differs between accounts. Each account has a column showing what it has now, and the **After sync** column shows what every account will have once you apply. Only details that differ get a row: a person missing from an account; a name, nickname, company, job title, birthday, note or photo; each kind of phone number, email, address, website, related name or date, such as an anniversary (for example "Work address"); iCloud's setting for showing a card as a company, kept the same between iCloud accounts; and labels that differ, including odd ones like "PREF", "X-Personal" or "Email", with a dropdown to pick the label. A "Fax" typed as a label becomes the real fax type. The dropdown's last choice, **Custom…**, opens a box to type any label, such as "Facebook" or "Personal"; iCloud and Google both keep it as typed. Struck-through values would be replaced or removed, values marked + would be added, and the green **After sync** column is what every account ends up with.
  - **Order:** when accounts list a person's phone numbers, emails, addresses, websites, related names or dates in a different order, **Different values** asks which order to use, with nothing chosen for you. Until you choose, every account keeps its own order. Once you choose, an **Order of …** row puts every account in that order, with Google's primary marker on the first value.
  - **Preferred (iCloud):** iCloud can mark one value in a list as preferred, and it's always the first. Where either iCloud account marks one in a list of two or more, a **Preferred …** row marks the first value in both.
  - A **How this … is written** row brings a value to the wording chosen under **Different values**, in every account that writes it differently or lists it more than once. It also shows, without asking you to pick a wording, any address with something else on it that has a US country, such as "US" or "United States of America", as a change to remove the country, and any US phone number written another way as a change to (555) 555-0123. You can untick the row, and nothing is written until you apply. Other countries' addresses and numbers stay as they are, and so do short numbers. If an account adds a US country or another format back later, the next review shows it again.
  - Untick a row to leave every account as it is for that row. It moves to a collapsed **Ignored** section at the bottom, where ticking it again brings it back. If what the row compares changes later, such as a new number under the same label, it comes back ticked. A **Contact** row and a group that an account lacks stay unticked until you tick them.
  - In a list, such as two different work addresses, untick a value in **After sync** to leave it out of every account; it's removed from any account that has it.
  - Groups get a table of their own, with each account's member count. Google labels count as groups.
  - **My Contacts (Google):** Google Contacts lists, and counts, only the contacts in its *My Contacts* group. A contact can end up only in a label instead, which some other sync tools do: it's in the account and Contact Sync reads it, but Google Contacts leaves it out of its main list and its count. That's why Google can show fewer contacts than Contact Sync. This row lists any such contacts in each Google account, and applying adds them to My Contacts.
  - A person waiting on a possible match has a note under their table instead of an **Apply just** button.
- **Duplicates within one account:** the same person more than once in one account, with every card shown side by side. **Merge into one** keeps the card with the most details, moves everything from the other cards onto it (including details Contact Sync doesn't otherwise use, such as social profiles and messaging handles), and deletes the others when you apply. The person's table then has a **Duplicate cards** row, which you can untick. **Keep both** leaves them as they are. Either choice moves the card to a collapsed **Decided** section, where you can switch. Until you choose, applying leaves the extra cards alone. A same-name pair in one account first appears under **Possible matches**; answering **Same person** brings it here.
- **Start over** forgets every match, choice and skip, once you confirm it.

Contacts are matched automatically when they share a phone number or email address, their names agree and their birthdays don't differ, or when they have the same name in different accounts and nothing contradicts it. A first or last name on its own counts, and a card with no name goes by its company, so a business entered as a first name in one account and as the company in another still matches. Contacts that were one person at the last apply stay matched, even after a name or number changes in one account. Matching ignores capitals, punctuation and how a number or address is written, so those differences never split a person in two. Being matched only means the copies are the same person: every difference between them still appears under **Changes**. Everything you choose is saved the moment you click it, and kept for later checks until the accounts no longer differ on it, when it's forgotten so it can't undo a later edit.

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
- An account that couldn't be read at the latest check is left out, and the Contact Sync page, the review and the Apply page say so. Applying changes only the other accounts. Once the account can be read again it catches up, including deleting from it anything deleted meanwhile.

### Deletions

The record made after each apply is what lets later reviews tell a deletion from a detail that was never synced. When something an account held at the last apply is gone from it, the review proposes deleting it from the other accounts too, instead of copying it back:

- A deleted contact shows as a **Contact** row that deletes it from every account. Untick it to leave every account as it is. After you next apply, it stays under **Ignored**, where ticking it copies the contact back instead.
- A deleted phone number, email, address, website, related name or date starts unticked in **After sync**, with a note saying where it was deleted. Tick it to keep it in every account instead.
- A cleared nickname, company, job title, birthday, note or photo shows as removed from every account. A name is never removed.
- A group deleted from one account, or a person taken out of a group, is deleted from or taken out of the group in the other accounts.

Until the first apply, nothing counts as deleted.

When more than 10 contacts have gone from one account since the last apply, that looks more like a glitch or a mistake than tidying up. The review shows a warning, and deleting those contacts from the other accounts starts unticked, so nothing goes until you tick each one. Applying without ticking them leaves them as they are, the same as unticking a **Contact** row above, and the results page says how many.

### Backups

Before writing, Contact Sync saves a backup to `addon_configs/local_contact_sync/backups`. Each is a folder named for the date and time it was made, such as `2026-11-01_14-05-12`. Applying everyone backs up every account. Applying one person backs up only their cards, and the folder name ends with theirs, such as `2026-11-01_14-05-12 Jane Smith`. The last 10 of each kind are kept, so one-person backups never push out a backup of every account.

Each folder holds:

- `What changed.txt`, listing every change that apply made and every one it didn't, by contact and account. It's the way to find the backup from just before a change you want to undo.
- For each account, a `.vcf` file of its contacts, which iCloud.com, Google Contacts and the Contacts apps can import, and a `.json` file with everything as the service sent it, including its groups.
- Under `photos`, the full-size photo of every contact the apply changed or deleted, named after the person.

### Undoing a change

There's no restore button, so how you undo something depends on what happened. `What changed.txt` in each backup folder lists what that apply did, which shows you the right backup.

- **A detail changed or removed:** press **Contacts**, open the person, press **Edit**, type back the old value from `What changed.txt`, and press **Apply now**.
- **Someone deleted from every account:** the backup folder ending with their name has a `.vcf` file for each account. Import one into that account on iCloud.com or in Google Contacts, then press **Check now**, and the review offers to copy them to the other accounts. An iCloud file is best, because it holds the card exactly as Apple had it. A `.vcf` file doesn't hold groups, so add those back with **Edit**. If their photo doesn't come back, it's under `photos` in the same folder.
- **Someone deleted while applying everyone:** that backup's `.vcf` file holds every contact. Open a copy in a text editor, keep only that person's card, from `BEGIN:VCARD` to `END:VCARD`, and import that.
- **Contacts gone from one account:** if the other accounts still have them, you don't need a backup. Untick their **Contact** rows so they aren't deleted from the other accounts, then apply. They move to **Ignored**, where ticking them and applying again copies them back.

Importing a whole `.vcf` file adds everyone as new contacts, next to any already there, so a whole backup can't be put back in one step. Only import a whole file into an empty account.

## Contacts

Press **Contacts** on the Contact Sync page to find anyone in your accounts, by name, company, phone number or email. The list and each contact's card show what the accounts hold today, exactly as written, with every number and email. A value only some accounts have says which. Where the accounts differ or something's waiting, the card shows what changes at the next apply separately.

Nothing here writes to an account. Whatever you enter waits until you press **Apply now** on the page that follows, which shows what changes in each account and makes the same checks and backup as any apply. Leaving that page doesn't lose or apply it: it stays under **Waiting to be applied** at the top of **Contacts**, and on the Review page, with **Edit** to change it and **Discard** to forget it.

- **Edit** changes a name, nickname, company, job title, birthday, notes, phone numbers, emails, addresses, websites, related names or dates, with their labels, for every account. Each label has a dropdown of the ones iCloud and Google both have, ending in **Custom…** to type your own. Only what you change is kept as your edit. The first value in each list is the main one, and the arrows change the order. The usual rules apply to what you type: US phone numbers are written as (555) 555-0123, and a US country is left off. An edit that's waiting can be opened and changed again, and putting everything back cancels it. If an account changes the same detail before you apply, **Different values** asks which to keep, and your edit waits until you answer.
- **Groups** on the same form add someone to any of your groups, or to a **New group…** created in every account, and take them out of one. Removing someone never deletes the group, even if they were its last member. The **Apply** page names the groups they join and leave in each account.
- **New contact** creates someone in every account. If the name, phone number or email is already here, the form lists who has it, and **Add anyway** adds them regardless. That includes a contact you entered earlier and haven't applied, which you can then edit or discard.
- **Delete everywhere** deletes someone from every account, after you confirm it twice: once on their card, and again with **Apply now**.
- A contact waiting on a possible match can't be edited or deleted until you answer it in the review, so a change can't land on the wrong person.
- Photos aren't changed here. Change one in any account, such as on an iPhone, and the sync offers it to the others. Other companies and locations are decided under **Details only Google can hold**.

## What isn't synced

Contact Sync syncs names, nicknames, companies, job titles, birthdays, notes, photos, phone numbers, emails, addresses, websites, related names, dates and groups. Anything else stays in each account as it is, and updating a contact leaves it alone:

- **Social profiles and messaging handles.** They aren't compared between accounts, though **Merge into one** keeps them when it combines duplicate cards.
- **Details only one service has,** such as Google's interests and custom fields, or Apple's settings for gender and how a shared photo displays.
- **Google's Other contacts,** the people Google saves by itself from your email. Contact Sync doesn't read them.
- **Details from someone's own Google profile,** which Google can show on your contact. Only what's saved on the contact itself is read.
- **Apple's hidden country code on an address.** Removing a US country takes it out of the address, but an iPhone's edit screen can still show the country. It doesn't show when you're just viewing the contact.

## Where things are kept

| What | Where |
|---|---|
| Daily check time and notification | The add-on's Configuration tab |
| iCloud accounts and their app-specific passwords, the Google app's client ID and secret, Google sign-ins, last check results, your review decisions, the record of the last apply | The add-on's private storage |
| Raw contact snapshots from the latest check | `addon_configs/local_contact_sync/snapshots` on the Samba share |
| Backups made before each apply | `addon_configs/local_contact_sync/backups` on the Samba share |

The snapshots and backups are kept under `addon_configs`, outside the add-on's own folder, so contact data can never end up in the add-on's code or on GitHub. Home Assistant gives every add-on a folder there for files you can open.
