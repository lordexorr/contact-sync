# Changelog

## 0.5.1

- **Improved: Its own icon.** Contact Sync has its own icon in Home Assistant, in place of the blank placeholder.

## 0.5.0

Contact Sync is now a Home Assistant integration, installed through the Marketplace, instead of an add-on. It does everything it did before, on its page in the sidebar.

- **Changed: Setup is in Home Assistant.** Add Contact Sync under Devices & services, then each account with **Add iCloud account** or **Add Google account**. **Configure** sets the daily check time and notification, and **Reconfigure** changes the Google app. Accounts don't carry over from the add-on: add each one again.
- **New: Sign in again** on a Google account, for when Google stops accepting its sign-in, keeps everything saved from the account.
- **Improved: Deletions after the move.** Once a check finds every account in sync and nothing has been recorded yet, as just after moving from the add-on, what each account holds is recorded, the same record an apply makes. A contact or detail deleted from one account after that is deleted from the others, instead of being offered back.
- **Changed: The page is a panel in Home Assistant's sidebar**, in your theme's colours, for administrators only. Choices in the review save without reloading the page.
- **New: Entities for automations and dashboards:** **Changes Waiting**, with what's still to decide in its attributes; **Last Check**, with any account that couldn't be read; and a **Check Now** button. Contact Sync's device page links to its page in the sidebar.
- **New: Repairs.** An account a check couldn't read is listed under **Settings → Repairs**, with what to do, until a check reads it.
- **New: Diagnostics** can be downloaded from Contact Sync's entry, with passwords, sign-ins, names and email addresses taken out.
- **Changed: Where files are kept.** Snapshots and backups are in `contact_sync` in Home Assistant's config folder, and everything else Contact Sync keeps is in `.storage/contact_sync`. Home Assistant's backups include both. Removing Contact Sync deletes what it keeps about everyone's contacts, apart from the backups, and cancels each Google sign-in.
- **Improved: The README and DOCS.md** say what syncs and how each detail is written, including the US phone format, taking the US country off addresses, labels, order and groups, and how contacts are matched.

## 0.4.4

- **New: Leave as they are.** A choice under **Different values**, such as which photo or nickname every account should have, can now be left as each account has it. It moves to **Decided**, stops counting as something to decide on the Contact Sync page and in the daily notification, and nothing about it is written. Unticking the value's row under **Changes** does the same. Picking a value later ticks the row again, and it's asked again only if one of the values changes.

## 0.4.3

- **New: Not in a group.** The review lists anyone who isn't in a group in any account as something to decide, and they count on the Contact Sync page and in the daily notification until you do. Choose a group from the dropdown, or **New group…**, and applying adds them to it in every account. **No group** stops asking about them unless they join a group and later leave it. Either choice moves the card to a collapsed **Decided** section, where you can change it.

## 0.4.2

- **New: Groups on the contact form.** Add someone to any of your groups from a dropdown, or to a **New group…** created in every account, and take them out of one, including when adding a new contact. Removing someone never deletes the group, even if they were its last member. The **Apply** page names the groups they join and leave in each account.

## 0.4.1

- **Improved: Label dropdowns on the contact form.** Each label is a dropdown of the ones iCloud and Google both have, ending in **Custom…** to type your own. New rows start on a likely label, such as mobile for a phone.
- **New: Edit a new contact before applying it.** Its Apply page and card have an **Edit** button that reopens the form with what you typed.
- **New: Waiting to be applied.** Anything entered and not applied is listed at the top of **Contacts**, with **Apply**, **Edit** and **Discard**. Leaving a page doesn't lose it or apply it.
- **Fix: A contact you entered earlier and haven't applied** is called that, with **Edit** and **Discard**, instead of looking like one already in your accounts.
- **Changed: The Contacts list and cards show what the accounts hold today**, exactly as written, not how it'll look after the next apply. Every number and email has its own line, and a value only some accounts have says which. Where something's going to change, the card shows that separately.
- **Improved: The review's dropdown for related names** offers the labels iCloud and Google both have.

## 0.4.0

You can now find, edit, add and delete contacts on the Contact Sync page, once, for every account. Nothing is written until you press **Apply now**, which makes the same checks and backup as any apply.

- **New: Contacts.** A list of everyone, searchable by name, company, phone number or email. Open someone to see everything every account will have after the next apply.
- **New: Edit.** Change a name, nickname, company, job title, birthday, notes, phone numbers, emails, addresses, websites, related names or dates, with their labels and order. **Save** goes straight to that person's Apply page, which shows what changes in each account; **Discard** forgets the edit. The usual rules apply to what you type. If an account changes the same detail before you apply, the review asks which to keep.
- **New: New contact** creates someone in every account. If the name, phone number or email is already in your contacts, the form lists who has it, and **Add anyway** adds them regardless.
- **New: Delete everywhere** deletes someone from every account, after you confirm on their card and again with **Apply now**.
- **Changed: A contact waiting on a possible match** can't be edited or deleted until you answer it, so a change can't land on the wrong person.
- **Improved: A person's Apply page** shows the table of what changes for them.
- **Fix: When a company changes on an iCloud card with no person's name**, the card's displayed name changes with it.

## 0.3.18

- **Changed: US phone numbers use one format** in every account: (555) 555-0123. Any US number written another way shows up in the review as a change to that format; you can untick the row, and nothing is written until you apply. Numbers with another country's code and short numbers stay as they are, and an extension stays on the end, like (555) 555-0123 x12. Matching contacts isn't affected.
- **Improved: The Contact Sync pages fill the window**, so the review's tables have room for every account.

## 0.3.17

More of what's on each card now syncs, so every account can match more closely.

- **New: Order of lists.** When accounts list a person's phone numbers, emails, addresses, websites, related names or dates in a different order, **Different values** asks which order to use. Until you choose, every account keeps its own order.
- **New: Preferred values.** iCloud's preferred marker, always on the first value in a list, now goes on the first value in both iCloud accounts. Putting a list in order also moves Google's primary marker to its first value.
- **Changed: US country removed.** "US", "USA", "United States" and "United States of America" on any address with something else on it show up in the review as a change to remove them. You can untick the row, and nothing is written until you apply. Other countries stay.
- **New: Dates sync.** Anniversaries and other dates sync as a list, with labels and deletions carried across like phone numbers. A date without a year takes the year from one that has it, and two different years are a choice.
- **New: Details only Google can hold.** A new review section for other companies and locations, which iCloud has no room for. For each person, choose the main company, which every account will show, and **Move to Notes** or **Delete** for every other detail. Until everything about a person is chosen, those details stay as they are.
- **New: Company cards.** iCloud's setting for showing a card as a company is kept the same between iCloud accounts.
- **Improved: Labels.** "X-Personal" and "Email" count as leftovers, like "PREF", and start on "other" with a dropdown to pick the real label. "Fax" typed as a label becomes the real fax type.
- **Fix: The label rows show the odd label** as the account has it, not always "PREF".

## 0.3.16

Every account can now end up literally the same.

- **New: Differences in how values are written show up.** Capitals and punctuation in a name, nickname, company, job title or note, and any different wording of a phone number, email, address, website or related name, such as "NY" and "New York" or "Rd" and "Road". Pick the wording under **Different values**, and a **How this … is written** row applies it to every account. People are still matched the forgiving way, so this never splits anyone in two.
- **New: Stray spaces** show up in the review as a change to remove them, on a row that says "extra space". You can untick the row, and nothing is written until you apply.
- **Changed: A value listed more than once on a card** is reduced to one, so every account holds it the same number of times.
- **Improved: An address with only a state or region** goes by it, with a US state's abbreviation counting as its name, so "NY" and "New York" are one address and "NY" and "MA" are two.

## 0.3.15

- **Fix: A value picked in the review stayed picked for good**, so it could undo a later edit. A pick is now forgotten once the accounts agree, and a value that changes after you picked is asked about again. Label picks work the same way.
- **Fix: A card with only a name could join two same-named people** with different numbers or birthdays into one. Every such pair is now asked about, and **Different people** holds even when the two later share a number.
- **Fix: Applying while an account couldn't be read** made Contact Sync forget what that account held, so a contact deleted meanwhile came back. It now keeps that record, and the pages say the account is left out.
- **Fix: More than 10 contacts gone from an account** were offered back, already ticked, after an apply that left them unticked. They now stay under **Ignored**, where ticking one copies it back.
- **Fix: Unticking a row also hid later changes to it**, such as a new number under the same label. The row now comes back ticked when what it compares changes.
- **Fix: Applying one person ten times could push out every full backup.** The last 10 of each kind are now kept.
- **Fix: Two birthdays on the same day with different years** were treated as the same. They're now a value to choose.
- **Fix: The Apple ID was sent to whatever address a card's photo line held.** Photos are now read only from iCloud's own addresses.
- **Improved: Google errors.** Google's internal errors are tried again, except when creating something, where a retry could make a second copy. Deleting a Google contact that's already gone counts as done.
- **Improved: iCloud cards record when Contact Sync changed them**, so "Last changed" and the most-recently-changed rule work for them.
- **Fix: Values that are nothing but symbols**, such as an emoji nickname, now sync.
- **Fix: Two accounts with the same label** each get their own column in the review.
- **Fix: Google addresses typed as free text** no longer count as one address, and they copy to other accounts.
- **Fix: Numbers with another country code** no longer pass for a US number ending in the same digits, and an extension stays part of the number.
- **Improved: Backups.** Google's `.vcf` includes dates and further companies, and iCloud's leaves out group cards, which would import as contacts. The `.json` files still hold everything.
- **Improved: Forget my decisions** asks first, and says what it undoes.
- **Fix: A one-person apply** no longer loses the groups if a snapshot file was deleted by hand.
- **Fix: Error messages point to Manage accounts**, not the Configuration tab.

The first check after updating forgets picks and unticked rows for anything the accounts no longer differ on.

## 0.3.14

- **Changed: Open the review is always on the Contact Sync page**, even when nothing is waiting, so ignored rows and past answers can still be changed. With nothing waiting, the page says how many are ignored and decided.

## 0.3.13

- **Fix: Google contacts only in a label** were missing from Google Contacts' list and count, which only covers *My Contacts*. They're listed in a **My Contacts (Google)** row in the review's Groups table, and applying adds them.

## 0.3.12

- **Changed: The Google section is gone from the Configuration tab**, which now holds only the daily check time and notification. The Google app is set under **Manage accounts** on the Contact Sync page. Updating from 0.3.10 or earlier, enter its client ID and secret there again.

## 0.3.11

- **Changed: The Google app is set on the Contact Sync page**, under **Manage accounts** with the Google accounts, instead of on the Configuration tab. It takes effect straight away, with no restart. Changing it later means connecting each Google account again, and the page says so.
- **Improved: Connect a Google account** is greyed out until the Google app is saved.
- **Behind the scenes: Moving the Google app.** The client ID and secret on the Configuration tab are copied to the page the first time this version starts. The tab's Google section is marked "moved" and goes in the next version.

## 0.3.10

- **Changed: Manage accounts.** iCloud and Google accounts are together in a **Manage accounts** section on the Contact Sync page, folded away with a count of each. It opens by itself while there are no accounts and during a Google sign-in.
- **Changed: The iCloud accounts section is gone from the Configuration tab.** Updating from 0.3.7 or earlier, add your iCloud accounts again under **Manage accounts**.

## 0.3.9

- **Improved: Photos that couldn't be downloaded.** When an iCloud card is saved with its photo left as it was, the results page says so on that change, in a **Check** column, and the Made heading counts how many to check. `What changed.txt` in the backup notes it too.
- **Changed: The Review section comes right after Check now** on the Contact Sync page, so a check's results are just below the button.

## 0.3.8

- **Changed: iCloud accounts are added and removed on the Contact Sync page**, like Google accounts, instead of on the Configuration tab. A new account is signed in straight away, so a wrong Apple ID or password shows up at once, and no restart is needed. To change a password, add the account again with the new one.
- **Behind the scenes: Accounts move to the page.** Accounts already on the Configuration tab move to the page by themselves the first time this version starts; they can then be deleted from the Configuration tab.
- **Fix: A business named in First name in one account and Company in another** wasn't recognized as one contact, so applying would have made a duplicate in each account. They're now treated as one contact, and the review shows the difference to settle.

## 0.3.7

- **Fix: A card with only a first name, or only a last name,** never matched its copy in another account, so applying made a second copy of it in each. A name on its own now matches, under the same rules as a full name.
- **Fix: After Apply copied someone into another account,** the choices you'd made for them in the review could be forgotten, and rows you'd unticked came back ticked. Those choices now stay with the person.
- **Fix: Saving an iCloud card whose photo couldn't be downloaded** saved none of its changes. They're now saved, with the photo left as it was.
- **New: A warning when more than 10 contacts disappear** from one account at once. None of them are deleted from your other accounts until you tick each one.
- **Improved: An account that can't be read during an apply** is named, with why, instead of an unexpected error. If the accounts can't be read again after the changes are made, the apply still counts as done.
- **Fix: After applying one person**, the contact and group counts on the Contact Sync page are up to date.
- **Fix: A person being deleted everywhere** no longer shows a duplicates card.
- **Fix: A group whose only new members are waiting on a possible match** isn't created until they can join it.

## 0.3.6

- **New: Custom labels.** Label dropdowns end with **Custom…**, which opens a box to type any label, such as "Facebook" or "Personal". iCloud and Google both keep it as typed.

## 0.3.5

- **Changed: Answered possible matches move to a collapsed Decided section** instead of disappearing, each with your answer and a button to change it, so one answer can be changed without forgetting every decision.
- **Improved: Changing an answer to Different people** separates the two contacts even after they were synced as one person.

## 0.3.4

- **Changed: Apply changes… is at the bottom of the review**, where you finish, instead of the top.

## 0.3.3

- **Improved: The Apply page names the groups**: which ones each account creates or deletes, and which ones the person joins or leaves, or for everyone, how many people join or leave each.

## 0.3.2

- **Improved: Applying one person is quicker.** It reads, backs up and rechecks only that person's cards and the groups, instead of every contact, and stops only if something about that person changed.
- **New: What changed.txt.** Every backup folder lists every change that apply made and every one it didn't, so you can tell which backup is from just before a change.
- **Changed: A one-person backup holds just their cards**, in a folder whose name ends with theirs. Backed-up photos are named after the person.

## 0.3.1

- **New: Duplicates within one account are a decision**, like possible matches. Each shows every card side by side, with **Merge into one** and **Keep both**. Merging keeps the card with the most details, moves everything from the other cards onto it, then deletes the others when you apply. Until you choose, the extra cards are left alone.
- **Changed: The card with the most details is compared and updated** where a person has more than one card in an account.
- **Improved: Replacing or removing an iCloud photo** also removes Apple's notes about the old one.
- **Behind the scenes: Google contacts are read with every field Google keeps**, so a merge can carry all of them over.

## 0.3.0

Apply. Contact Sync now writes the changes you review.

- **New: Apply.** **Apply changes…** at the top of the review applies every ticked change; **Apply just *name*…** under a person's table applies only theirs, with their group changes. A page shows what changes in each account before you press **Apply now**.
- **New: Checks and backups before writing.** Every account is checked again, and nothing is written if something changed since that page opened. Then every account is backed up to `addon_configs/local_contact_sync/backups`, as `.vcf` and `.json` files plus the full-size photos of the contacts it changes, keeping the last 10 backups.
- **New: Only what's in the review is written.** Everything else on each contact stays as it is, including details only one service has. Photos are copied at full size.
- **New: A results page** lists every change made and every one that wasn't, with the reason. People with a failed change stay in the review to try again.
- **New: Deletions carry across.** After each apply, a record of what every account holds lets later reviews carry deletions across: a contact, detail, photo, group or group membership deleted from one account is deleted from the others instead of being copied back. A deleted list value starts unticked; tick it to keep it everywhere.
- **Improved: The recently changed value is preselected** where accounts disagree, over one left as it was.
- **Improved: Contacts matched at the last apply stay matched**, even after a name or number changes in one account.
- **Changed: People in an unanswered possible match** are left out of Apply until you answer it.
- **New: Daily notification.** A notify entity or service told after the daily check when changes are waiting or an account couldn't be read. The add-on now has Home Assistant API access for this.

## 0.2.9

- **Improved: A cell that would change shows its new value below the old one**, the way lists do: the old value struck through, and the new one marked + in green. A replaced photo shows the new one, outlined in green, next to the faded old one.

## 0.2.8

- **Fix: Label dropdowns in the After sync column** show its green, like the other values there.

## 0.2.7

- **Improved: Clearer colors in the comparison tables.** The **After sync** column is green, values that would be replaced or removed are struck through, values an account would gain are marked + in green, and an empty cell the sync would fill says "will be added". Account cells are no longer shaded.

## 0.2.6

- **Fix: After unticking a row, the row that moved into its place could look unticked too.** The review now always shows what's actually saved.

## 0.2.5

- **New: A comparison table for each person**, with a column per account showing what it has now and an **After sync** column showing what every account will have once you apply. Only details that differ get a row.
- **Improved: Lists are grouped by label**, such as "Work address", so different values sit side by side. Untick a value in **After sync** to leave it out of every account.
- **Improved: Label differences** show every account's label next to each other, with the dropdown in **After sync**.
- **New: Groups have their own table**, with each account's member count.
- **Changed: Rows unticked in an earlier version** show ticked once more, except label fixes.

## 0.2.4

- **Changed: The review saves every click straight away**: ticking or unticking a change, choosing a label, picking a value, or answering a possible match. There are no Save buttons; a short "Saved" note confirms each one, and the page keeps your place.
- **Improved: Handled items move out of the way.** Answered matches disappear, picked values move to a collapsed **Decided** section, and unticked changes to **Ignored**.
- **Changed: Values still to decide show nothing selected**, with the value that will be used marked, so any pick counts as a decision.

## 0.2.3

- **New: Label fixes have a dropdown.** Pick the label for a phone number, email, address or website instead of only accepting "other". It offers the labels iCloud and Google both have, plus any already on that value, and starts on the label another account uses.
- **Improved: One line per label fix** for every account that needs it, instead of one per account. Label fixes unticked in an earlier version show ticked once more.

## 0.2.2

- **Improved: Unticked changes move to a collapsed Ignored section** at the bottom of the review, so the changes still waiting stay on top. Tick one there and press **Save choices** to bring it back.

## 0.2.1

- **Improved: Same full name, matched automatically.** Contacts with the same full name in different accounts are matched unless something contradicts it: both copies have phone numbers or emails but none in common, or both have birthdays on different days. The same name twice in one account is still asked about.
- **Improved: Possible-match cards show everything each copy holds**: company and job title, phone numbers, emails, addresses, websites, related names, birthday, groups, the start of any note, the photo, and when it was last changed.

## 0.2.0

Review page. Still read-only: nothing is written to any account.

- **New: Matching across accounts.** The same person is matched automatically when they share a phone number or email address and their names agree; otherwise it's a possible match for you to confirm or reject.
- **New: Every change a sync would make**, for each account: new contacts, missing phone numbers, emails, addresses, websites and related names, birthdays, and photos. Untick any change to skip it.
- **New: Choosing between values.** Where accounts disagree on a name, nickname, company, job title, birthday, note or photo, you pick which value wins; the most recently changed one is preselected.
- **New: Leftover labels** from other sync tools, such as "PREF", are replaced with real ones.
- **New: Groups kept in step.** Google labels and iCloud groups an account lacks are created there, and contacts are added to the groups they belong to.
- **New: Photos compared by what they show**, so the same picture counts as the same even after re-compression.
- **New: Matches, choices and skips are kept** between checks. **Start over** forgets them.

## 0.1.2

- **New: iCloud accounts section** on the Contact Sync page, listing each configured iCloud account and where to add or change them.
- **Improved: Setup guide** with step-by-step instructions for the Google Cloud project, the OAuth consent screen, and the Branding step Google requires before the app can be published.
- **New: This changelog and a README.**

## 0.1.1

- **Changed: The Configuration tab has a separate Google section** for the client ID and secret, and every field has a name and help text.
- **Improved: Setup guide** updated to match.

## 0.1.0

First version. Read-only: it connects to every configured account and reports what it finds, and never changes any contacts.

- **New: Any number of iCloud and Google accounts**: iCloud with an Apple ID and app-specific password, Google with Google sign-in.
- **New: A daily check** at a set time, plus a **Check now** button.
- **New: Contact Sync page** in the Home Assistant sidebar, with contact and group counts for each account, errors, and the last and next check times.
- **New: A copy of each account's contacts** from the latest check is saved, for inspection.
