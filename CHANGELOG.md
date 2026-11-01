# Changelog

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
