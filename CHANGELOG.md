# Changelog

## 0.3.0

Apply. Contact Sync now writes the changes you review.

- **Apply changes…** at the top of the review applies every ticked change; **Apply just *name*…** under a person's table applies only theirs, with their group changes. A page shows what changes in each account before you press **Apply now**.
- Before writing, it checks every account again and stops without writing anything if something changed since that page opened. It then backs up every account to `addon_configs/local_contact_sync/backups`, as `.vcf` and `.json` files plus the full-size photos of the contacts it changes, and keeps the last 10 backups.
- Only the details shown in the review are written. Everything else on each contact stays as it is, including details only one service has. Photos are copied at full size.
- A results page lists every change made and every one that wasn't, with the reason. People with a failed change stay in the review to try again.
- After each apply, a record of what every account holds lets later reviews carry deletions across: a contact, detail, photo, group or group membership deleted from one account is deleted from the others instead of being copied back. A deleted list value starts unticked; tick it to keep it everywhere.
- Where accounts disagree on a value, the one changed since the last apply is preselected over one left as it was.
- Contacts that were the same person at the last apply stay matched, even after a name or number changes in one account.
- People in an unanswered possible match are left out of Apply until you answer it.
- New **Daily notification** option: a notify entity or service told after the daily check when changes are waiting or an account couldn't be read. The add-on now has Home Assistant API access for this.

## 0.2.9

- An account cell that would change now shows its new value below the old one, the way lists do: the old label, name, birthday or other value struck through, and the new one marked + in green. A replaced photo shows the new one, outlined in green, next to the faded old one.

## 0.2.8

- Label dropdowns in the **After sync** column show its green, like the other values there, instead of a plain background.

## 0.2.7

- Clearer colors in the comparison tables: the **After sync** column is green, values that would be replaced or removed are struck through, values an account would gain are marked + in green, and an empty cell the sync would fill says "will be added". Account cells are no longer shaded.

## 0.2.6

- Fixed: after unticking a row, the row that moved into its place could look unticked too. The browser was restoring tick boxes, dropdowns and choices by position when the page reloaded; the review now always shows what's actually saved.

## 0.2.5

- Changes are shown as a comparison table for each person: a column per account with what it has now, and an **After sync** column with what every account will have once you apply. Only details that differ get a row, and the cells that would change are shaded.
- Lists are grouped by label, such as "Work address", so different values sit side by side. Untick a value in **After sync** to leave it out of every account, which removes it from any account that has it.
- Label differences show every account's label next to each other, with the dropdown in **After sync**.
- Groups have their own table, with each account's member count.
- Rows unticked in an earlier version show ticked once more, except label fixes.

## 0.2.4

- The review saves every click straight away: ticking or unticking a change, choosing a label, picking a value, or answering a possible match. There are no Save buttons any more; a short "Saved" note confirms each one, and the page keeps your place.
- Handled items move out of the way: answered matches disappear, picked values move to a collapsed **Decided** section, and unticked changes to **Ignored**.
- Values still to decide show nothing selected, with the value that will be used marked, so any pick counts as a decision.

## 0.2.3

- Label fixes have a dropdown: pick the label for a phone number, email, address or website instead of only accepting "other". It offers the labels iCloud and Google both have, plus any label already on that value, and starts on the label another account already uses, or "other" when the only label is an odd one like "PREF".
- Each label fix is one line for every account that needs it, instead of one line per account. Label fixes unticked in an earlier version show ticked once more.

## 0.2.2

- Unticked changes move to a collapsed **Ignored** section at the bottom of the review, so the changes still waiting stay on top. Tick one there and press **Save choices** to bring it back.

## 0.2.1

- Contacts with the same full name in different accounts are matched automatically, unless something contradicts it: both copies have phone numbers or emails but none in common, or both have birthdays on different days. A detail only one copy has, such as a birthday, isn't a contradiction; it shows up as a change instead. The same name twice in one account is still asked about.
- Possible-match cards show everything each copy holds: company and job title, phone numbers, emails, addresses, websites, related names, birthday, groups, the start of any note, the photo, and when it was last changed. A copy with nothing else says "Name only".

## 0.2.0

Review page. Still read-only: nothing is written to any account.

- Matches the same person across every account: automatically when they share a phone number or email address and their names agree; otherwise, when the names differ or only the name matches, as a possible match for you to confirm or reject.
- Lists every change a sync would make, for each account: new contacts, missing phone numbers, emails, addresses, websites and related names, birthdays, and photos. Untick any change to skip it.
- Where accounts disagree on a name, nickname, company, job title, birthday, note or photo, you pick which value wins; the most recently changed one is preselected.
- Labels left behind by other sync tools, such as "PREF", are replaced with real ones.
- Google labels and iCloud groups are kept in step: groups an account lacks are created there, and contacts are added to the groups they belong to.
- Photos are compared by what they show, so the same picture in two accounts counts as the same even after re-compression.
- Matches, choices and skips are kept between checks. **Start over** forgets them.

## 0.1.2

- Contact Sync page: new iCloud accounts section listing each configured iCloud account, and where to add or change them.
- Setup guide: step-by-step instructions for creating the Google Cloud project, the OAuth consent screen's correct place in the console's left menu, and a new Branding step (home page, privacy policy link and authorized domain, no logo) that Google requires before the app can be published.
- Added this changelog and a README.

## 0.1.1

- The Configuration tab has a separate Google section for the client ID and secret, and every field has a name and help text.
- Setup guide updated to match.

## 0.1.0

First version. Read-only: it connects to every configured account and reports what it finds, and never changes any contacts.

- Connects any number of iCloud accounts (Apple ID and app-specific password) and Google accounts (Google sign-in).
- Daily check at a set time, plus a **Check now** button.
- Contact Sync page in the Home Assistant sidebar: contact and group counts for each account, errors, and the last and next check times.
- Saves a copy of each account's contacts from the latest check, for inspection.
