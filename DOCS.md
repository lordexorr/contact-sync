# Contact Sync

Keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. It checks once a day and whenever you press **Check now**, and writes nothing to any account until you apply the changes yourself.

**Current build: review only.** It reads every account and shows what a sync would change. It never writes to any account.

## Setup

### 1. Apple app-specific password (each iCloud account)

1. Sign in at [account.apple.com](https://account.apple.com).
2. **Sign-In and Security → App-Specific Passwords**: create one named "Contact Sync".
3. Copy it. It looks like `abcd-efgh-ijkl-mnop`.

Changing an Apple ID's main password revokes its app-specific passwords. If that happens, create a new one and update the Configuration tab.

### 2. Google OAuth client (once, shared by every Google account)

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

### 3. Configure the add-on

On the **Configuration** tab, open the **Google** section and enter the client ID and secret. Under **iCloud accounts**, press **Add** for each iCloud account and enter a label of your choice (shown on the Contact Sync page), its Apple ID, and its app-specific password. Save, then restart the add-on. On the **Info** tab, turn on **Show in sidebar**.

### 4. Connect each Google account

Use a computer for this. The copy-and-paste step is awkward on a phone.

1. Open **Contact Sync** in the sidebar and press **Connect a Google account**.
2. Open the sign-in link and choose the account. Google warns that it hasn't verified the app: choose **Advanced**, then **Go to Contact Sync**. The warning is normal for an app you made yourself.
3. Allow access to contacts. If Google shows a checkbox for contacts, make sure it's ticked.
4. The browser ends on a "This site can't be reached" page. That's expected. Copy the whole address from the address bar, paste it into Contact Sync, and press **Connect**.
5. Repeat for each Google account.

Then press **Check now**. Each account should show its contact count.

## Reviewing changes

After each check, the **Review** section at the top of the Contact Sync page counts what a sync would change. **Open the review** shows the details.

- **Possible matches:** two contacts that might be the same person: the same name with no phone number or email address in common, or the same phone number or email address under different names. Choose **Same person** or **Different people**.
- **Different values:** a name, nickname, company, job title, birthday, note or photo that differs between accounts. The value from the most recently changed contact is selected; pick another and press **Use the selected value** to change it.
- **Changes:** everything each account would get: new contacts; missing phone numbers, emails, addresses, websites, related names, birthdays and photos; labels such as "PREF" replaced with real ones; and groups to create or add contacts to. Google labels count as groups. Untick anything you don't want and press **Save choices**.
- **Start over** forgets every match, choice and skip.

Contacts are matched automatically when they share a phone number or email address and their names agree. Your decisions are kept for later checks.

## Where things are kept

| What | Where |
|---|---|
| Apple app-specific passwords, Google client ID and secret | The add-on's Configuration tab |
| Google sign-ins, last check results | The add-on's private storage |
| Raw contact snapshots from the latest check | `addon_configs/local_contact_sync/snapshots` on the Samba share |

The snapshots are kept under `addon_configs`, outside the add-on's own folder, so contact data can never end up in the add-on's code or on GitHub. Home Assistant gives every add-on a folder there for files you can open.
