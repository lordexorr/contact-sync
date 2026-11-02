# Changelog

## 0.4.1

- **Label dropdowns on the contact form:** each label is a dropdown of the ones iCloud and Google both have, ending in **Custom…** to type your own, like the review. New rows start on a likely label, such as mobile for a phone.
- **Edit a new contact before applying it:** its Apply page and card have an **Edit** button that reopens the form with what you typed.
- **Waiting to be applied:** anything entered and not applied is listed at the top of **Contacts**, with **Apply**, **Edit** and **Discard**. Leaving a page doesn't lose it or apply it.
- **Duplicate warning:** a contact you entered earlier and haven't applied is called that, with **Edit** and **Discard**, instead of looking like one already in your accounts.
- **The Contacts list and cards show what the accounts hold today**, exactly as written, not how it'll look after the next apply. Every number and email has its own line, and a value only some accounts have says which. Where something's going to change, the card shows that separately.
- The review's dropdown for related names now offers the labels iCloud and Google both have.

## 0.4.0

You can now find, edit, add and delete contacts on the Contact Sync page, once, for every account. Nothing is written until you press **Apply now**, which makes the same checks and backup as any apply.

- **Contacts:** a list of everyone, searchable by name, company, phone number or email. Open someone to see everything every account will have after the next apply.
- **Edit:** change a name, nickname, company, job title, birthday, notes, phone numbers, emails, addresses, websites, related names or dates, with their labels and order. **Save** goes straight to that person's Apply page, which shows what changes in each account. **Discard** forgets the edit. The usual rules apply to what you type, including the phone format and leaving off a US country. If an account changes the same detail before you apply, the review asks which to keep.
- **New contact:** creates someone in every account. If the name, phone number or email is already in your contacts, the form lists who has it, and **Add anyway** adds them regardless.
- **Delete everywhere:** deletes someone from every account, after you confirm on their card and again with **Apply now**.
- A contact waiting on a possible match can't be edited or deleted until you answer it, so a change can't land on the wrong person.
- A person's Apply page now shows the table of what changes for them.
- When a company changes on an iCloud card with no person's name, the card's displayed name changes with it.

## 0.3.18

- **US phone numbers** now use one format in every account: (555) 555-0123. Any US number written another way, such as with +1 or 1 in front or as ten digits with no spacing, shows up in the review as a change to that format. You don't have to pick a wording, you can untick the row, and nothing is written until you apply. Numbers with another country's code and short numbers stay as they are. An extension stays on the end, like (555) 555-0123 x12. Matching contacts isn't affected.
- The Contact Sync pages fill the window instead of stopping at a fixed width, so the review's tables have room for every account.

## 0.3.17

More of what's on each card now syncs, so every account can match more closely.

- **Order of lists:** when accounts list a person's phone numbers, emails, addresses, websites, related names or dates in a different order, **Different values** asks which order to use, with nothing chosen for you. Until you choose, every account keeps its own order. Accounts that hold different values but don't disagree on order aren't asked about.
- **Preferred values:** iCloud's preferred marker, which is always on the first value in a list, now goes on the first value in both iCloud accounts wherever either has one in a list of two or more. Putting a list in order also moves Google's primary marker to its first value.
- **US country removed:** "US", "USA", "United States" and "United States of America" on any address with something else on it now show up in the review as a change to remove them. You don't have to pick a wording, you can untick the row, and nothing is written until you apply. Other countries stay. If an account adds one back, the next review shows it again.
- **Dates:** anniversaries and other dates now sync as a list, with labels and deletions carried across like phone numbers. A date without a year takes the year from one that has it, and two different years are a choice.
- **Details only Google can hold:** a new review section for other companies and locations, which iCloud has no room for. For each person, choose the main company, which every account will show, and choose **Move to Notes** or **Delete** for every other detail, with nothing chosen for you. Until everything about a person is chosen, those details stay as they are. An exact repeat of the main company shows under **Changes** as a row to remove it, without asking you to choose.
- **Company cards:** iCloud's setting for showing a card as a company is now kept the same between iCloud accounts. A change in one account since the last apply carries over, including turning it off.
- **Labels:** "X-Personal" and "Email" now count as leftovers, like "PREF", and start on "other" with a dropdown to pick the real label. "Fax" typed as a label becomes the real fax type.
- The label rows show the odd label as the account has it, not always "PREF".

## 0.3.16

Every account can now end up literally the same.

- Values that differ only in how they're written now show as differences: capitals and punctuation in a name, nickname, company, job title or note, and any different wording of a phone number, email, address, website or related name, such as "NY" and "New York", "Rd" and "Road", or a country on one copy but not another. Pick the wording under **Different values**, and a **How this … is written** row applies it to every account. People are still matched the forgiving way, so this never splits anyone in two.
- Stray spaces show up in the review as a change to remove them, on a row that says "extra space". You don't have to pick a wording, you can untick the row, and nothing is written until you apply.
- A value listed more than once on a card is reduced to one, so every account holds it the same number of times.
- An address with only a state or region now goes by it, with a US state's abbreviation counting as its name, so "NY" and "New York" are one address and "NY" and "MA" are two.

## 0.3.15

- Fixed: a value picked in the review stayed picked for good, so it could undo a later edit: pick "Bobby", change it to "Rob" on a phone, and applying wrote "Bobby" back. A pick is now forgotten once the accounts agree, and a value that changes after you picked is asked about again. Label picks work the same way.
- Fixed: a card with only a name could join two same-named people with different numbers or birthdays into one. Every pair is now asked about instead. **Different people** also holds when the two later share a number, and the same phone number or email with different birthdays is asked about.
- Fixed: applying while an account couldn't be read made Contact Sync forget what that account held, so a contact deleted meanwhile came back once the account returned. It now keeps that record, and the Contact Sync page, the review and the Apply page say the account is left out.
- Fixed: when more than 10 contacts had gone from an account and you applied without ticking them, the next review offered to copy them all back, already ticked. They now stay as they are, under **Ignored**, where ticking one copies it back, and the results page says how many.
- Fixed: unticking a row also hid later changes to it, such as a new number under the same label. The row now comes back ticked when what it compares changes.
- Fixed: applying one person ten times could push out every full backup. The last 10 of each kind are now kept.
- Fixed: two birthdays on the same day with different years were treated as the same, and one was used without asking. They're now a value to choose. A birthday without a year still takes the year from one that has it.
- Fixed: the Apple ID was sent to whatever address a card's photo line held. Photos are now read only from iCloud's own addresses.
- Google's internal errors are tried again, except when creating something, where a retry could make a second copy. Deleting a Google contact that's already gone counts as done.
- iCloud cards record when Contact Sync created or changed them, so "Last changed" and the most-recently-changed rule work for them.
- Values that are nothing but symbols, such as an emoji nickname, now sync.
- Two accounts with the same label each get their own column in the review.
- Google addresses typed as free text no longer count as one address, and they copy to other accounts.
- Numbers with another country code no longer pass for a US number ending in the same digits, and an extension stays part of the number.
- In a backup, Google's `.vcf` now includes dates and further companies, and iCloud's leaves out group cards, which would import as contacts. The `.json` files still hold everything.
- **Forget my decisions** asks first, and says what it undoes.
- A one-person apply no longer loses the groups if a snapshot file was deleted by hand.
- Error messages point to **Manage accounts**, not the Configuration tab.

The first check after updating forgets picks and unticked rows for anything the accounts no longer differ on.

## 0.3.14

- **Open the review** is always on the Contact Sync page, even when nothing is waiting, so ignored rows and past answers can still be changed. With nothing waiting, the page says how many are ignored and decided.

## 0.3.13

- Google contacts that are only in a label, not in *My Contacts*, are listed in a **My Contacts (Google)** row in the review's Groups table, and applying adds them. Google Contacts lists and counts only My Contacts, so those contacts were missing from its list and count, which is why it could show fewer contacts than Contact Sync.

## 0.3.12

- The Google section is gone from the Configuration tab, which now holds only the daily check time and notification. The Google app is set under **Manage accounts** on the Contact Sync page. Updating from 0.3.10 or earlier, enter its client ID and secret there again.

## 0.3.11

- The Google app's client ID and secret are set under **Manage accounts** on the Contact Sync page, with the Google accounts, instead of on the Configuration tab. They take effect straight away, with no restart. Once saved, the app folds away; changing it later means connecting each Google account again, and the page says so.
- **Connect a Google account** is greyed out until the Google app is saved.
- The client ID and secret already on the Configuration tab are copied to the page the first time this version starts. The Configuration tab now holds only the daily check time and notification; its Google section is marked "moved" and goes in the next version.

## 0.3.10

- iCloud and Google accounts are together in a **Manage accounts** section on the Contact Sync page, folded away with a count of each. It opens by itself while there are no accounts and during a Google sign-in.
- The old iCloud accounts section is gone from the Configuration tab. Updating from 0.3.7 or earlier, add your iCloud accounts again under **Manage accounts**.

## 0.3.9

- When an iCloud card is saved with its photo left as it was, because the photo couldn't be downloaded, the results page says so on that change, in a **Check** column, and the Made heading counts how many to check. `What changed.txt` in the backup notes it too.
- On the Contact Sync page, the Review section comes right after **Check now**, so a check's results are just below the button.

## 0.3.8

- iCloud accounts are added and removed on the Contact Sync page, like Google accounts, instead of on the Configuration tab. A new account is signed in straight away, so a wrong Apple ID or password shows up at once, and no restart is needed. To change a password, add the account again with the new one.
- Accounts already on the Configuration tab move to the page by themselves the first time this version starts; they can then be deleted from the Configuration tab.
- Fixed: when the same business had its name in the First name field in one account and in the Company field in another, the two weren't recognized as the same contact, so applying would have made a duplicate in each account. They're now treated as one contact, and the review shows the name and company difference to settle.

## 0.3.7

- Fixed: a card with only a first name, or only a last name, never matched its copy in another account, so applying made a second copy of it in each. A name on its own now matches, under the same rules as a full name.
- Fixed: after Apply copied someone into another account, the choices you'd made for them in the review could be forgotten, and rows you'd unticked came back ticked. Those choices now stay with the person.
- Fixed: when saving changes to an iCloud card, such as a new phone number, its existing photo is downloaded so it survives the save. If that download failed, none of the changes were saved. They now are, with the photo left as it was.
- If more than 10 contacts disappear from one account at once, the review warns you, and none of them are deleted from your other accounts until you tick each one.
- When an account can't be read during an apply, the result names it and says why, instead of calling it an unexpected error. If the accounts can't be read again after the changes are made, the apply still counts as done.
- After applying one person, the contact and group counts on the Contact Sync page are up to date.
- A person being deleted everywhere no longer shows a duplicates card.
- A group whose only new members are waiting on a possible match isn't created until they can join it.

## 0.3.6

- Label dropdowns end with **Custom…**, which opens a box to type any label, such as "Facebook" or "Personal". iCloud and Google both keep it as typed.

## 0.3.5

- Answered possible matches move to a collapsed **Decided** section instead of disappearing, each with your answer and a button to change it, so one answer can be changed without forgetting every decision.
- Changing an answer to **Different people** separates the two contacts even after they were synced as one person.

## 0.3.4

- **Apply changes…** is at the bottom of the review, where you finish, instead of the top.

## 0.3.3

- The Apply page names the groups: which ones each account creates or deletes, and which ones the person joins or leaves (for everyone, how many people join or leave each).

## 0.3.2

- Applying one person is quicker: it reads, backs up and rechecks only that person's cards and the groups, instead of every contact, and stops only if something about that person changed.
- Every backup folder has a `What changed.txt` listing every change that apply made and every one it didn't, so you can tell which backup is from just before a change.
- A one-person backup holds just their cards, in a folder whose name ends with theirs. Backed-up photos are named after the person.

## 0.3.1

- Duplicates within one account are now a decision, like possible matches. Each shows every card side by side, with **Merge into one** and **Keep both**. Merging keeps the card with the most details, moves everything from the other cards onto it, including details Contact Sync doesn't otherwise use such as dates, social profiles and messaging handles, then deletes the others when you apply. Until you choose, the extra cards are left alone.
- Where a person has more than one card in an account, the one with the most details is the one compared and updated.
- Replacing or removing an iCloud photo also removes Apple's notes about the old one.
- Google contacts are read with every field Google keeps, so a merge can carry all of them over.

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
