# Contact Sync

Keeps contacts in sync across any number of iCloud and Google accounts, as one combined list. It checks once a day and whenever you press **Check now**, and writes nothing to any account until you apply the changes yourself.

**Current build: connection check only.** It reads every account and shows how many contacts and groups it found.

## Setup

### 1. Apple app-specific password (each iCloud account)

1. Sign in at [account.apple.com](https://account.apple.com).
2. **Sign-In and Security → App-Specific Passwords**: create one named "Contact Sync".
3. Copy it. It looks like `abcd-efgh-ijkl-mnop`.

Changing an Apple ID's main password revokes its app-specific passwords. If that happens, create a new one and update the Configuration tab.

### 2. Google OAuth client (once, shared by every Google account)

1. In the [Google Cloud console](https://console.cloud.google.com), create a project named "Contact Sync".
2. **APIs & Services → Library**: find **Google People API** and enable it.
3. **OAuth consent screen** (it opens *Google Auth Platform*) → **Get started**: app name "Contact Sync", your email for support and contact, audience **External**.
4. **Audience → Publish app**. Publishing status must read **In production**. In *Testing*, Google signs Contact Sync out every 7 days.
5. **Clients → Create client**: application type **Desktop app**, name "Contact Sync".
6. Copy the **Client ID** and **Client secret** before closing the dialog. Google shows the secret only once.

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

## Where things are kept

| What | Where |
|---|---|
| Apple app-specific passwords, Google client ID and secret | The add-on's Configuration tab |
| Google sign-ins, last check results | The add-on's private storage |
| Raw contact snapshots from the latest check | `addon_configs/local_contact_sync/snapshots` on the Samba share |
