# Setting up "Sign in with Google" (for maintainers)

Screenwriter's Google Drive sync needs an **OAuth client** that belongs to the project: Google uses it to
show "Screenwriter wants to access your Google Drive" and to issue sign-ins. It's free and takes about
10 minutes. Users never see any of this — they just click *Sign in with Google*.

Without it, the app still builds and runs; the Google option is simply hidden, and cloud-folder sync
(Drive for desktop, Dropbox, iCloud, OneDrive) works as before.

## 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/> with the Google account that should own the app.
2. Project picker (top left) → **New project** → name it `Screenwriter` → **Create**, and select it.

## 2. Turn on the Drive API

**APIs & Services → Library** → search **Google Drive API** → **Enable**.

## 3. Describe the app (consent screen)

Open **Google Auth Platform** (APIs & Services → OAuth consent screen) → **Get started**:

- **App name**: `Screenwriter` · **User support email**: your address.
- **Audience**: **External**.
- **Contact information**: your address. Accept the policy → **Create**.

Then:

- **Branding**: add the app logo (`screenwriter/resources/icon.png`), the home page
  `https://dntatme.github.io/screenwriter/`, and privacy-policy / terms links if you have them.
- **Data access → Add or remove scopes**: add `.../auth/drive.file` (*See, edit, create and delete only the
  specific Google Drive files you use with this app*), plus `openid` and `.../auth/userinfo.email`. All three are
  *non-sensitive*, so Google doesn't require a security review.
- **Audience → Publish app** (status **In production**). While an app is in *Testing*, only listed test users can
  sign in and their sign-in expires every 7 days.

## 4. Create the desktop client

**Clients → Create client** → Application type **Desktop app** → name `Screenwriter desktop` → **Create**, then
**Download JSON**.

For a desktop app, Google treats the "client secret" as not really secret (it ships inside the app, and the
sign-in is protected by PKCE instead). Still, keep it out of the public repository — GitHub and Google scan for it.

## 5. Use it

**While developing**, either put the downloaded file at `screenwriter/resources/google_client.json` (it's in
`.gitignore`), or set environment variables:

```bash
export SCREENWRITER_GOOGLE_CLIENT_ID="…apps.googleusercontent.com"
export SCREENWRITER_GOOGLE_CLIENT_SECRET="…"
uv run python -m screenwriter
```

**For releases**, add two repository secrets (GitHub → Settings → Secrets and variables → Actions), or from a
terminal:

```bash
gh secret set GOOGLE_CLIENT_ID --repo dntAtMe/screenwriter
gh secret set GOOGLE_CLIENT_SECRET --repo dntAtMe/screenwriter
```

The Release workflow writes them into the build (`screenwriter/resources/google_client.json`); its log says
*Google sign-in: included*.

## What users see

1. **File → Sync & Backup… → Google Drive — Sign in with Google…** (or **File → Open from Google Drive…**).
2. The browser opens Google's sign-in page, then *Screenwriter wants access to your Google Account* listing
   only “See, edit, create and delete only the specific Google Drive files you use with this app”.
3. After **Allow**, the browser says *You're signed in* and the app continues.

The sign-in is remembered in the system's secure store (macOS Keychain, Windows Credential Manager, Linux
Secret Service). Projects appear in the user's **My Drive/Screenwriter** folder as `.screenwriter` files.

## Limits worth knowing

- Unverified apps (no brand verification) can have up to 100 users sign in; after that, submit the app for
  **brand verification** in Google Auth Platform → Verification center (no security assessment is needed for
  these scopes).
- With `drive.file`, the app sees only files it created. A `.screenwriter` file someone uploads to Drive by
  hand won't be listed — they can open it with **File → Open Project File…** instead.
