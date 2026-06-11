# Google OAuth (Passport)

1. Create OAuth 2.0 credentials in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) (Web application).
2. Set **Authorized redirect URIs** to the **exact** same value as `GOOGLE_CALLBACK_URL` in `.env` (copy from server log on startup, e.g. `http://localhost:5000/api/auth/google/callback`). **Character-for-character match** is required or Google returns `400: redirect_uri_mismatch`.
3. Copy Client ID and Client Secret into `.env` (see [`.env.example`](./.env.example)).
4. Set `GOOGLE_OAUTH_SUCCESS_REDIRECT` to your SPA URL (e.g. `http://localhost:3000` or `http://localhost:3000/auth/callback`).
5. **Sign in:** `GET /api/auth/google` → Google → callback → frontend `?code=...` → `POST /api/auth/oauth/exchange`. Existing email/password accounts can be linked when Google verifies the same email. **Sign up:** `GET /api/auth/google/register` — same flow, but if that email is already used by another account, redirect uses `?error=email_already_registered` (no auto-link).
6. Exchange codes are stored **in memory** (single process). For multiple API instances, replace with Redis or similar.

**Troubleshooting**

- **Google shows `redirect_uri_mismatch`:** The `redirect_uri` Google receives must match **one line** in **Authorized redirect URIs** (same scheme `http`/`https`, host, port, path — no trailing slash on `/callback` unless you added one everywhere).
  1. See what the API uses: in **development**, open `GET http://localhost:5000/api/auth/google/oauth-config` and copy `GOOGLE_CALLBACK_URL`.
  2. On the machine where Node runs, `services/.env` must set **`GOOGLE_CALLBACK_URL`** to that same string. If the browser hits **`https://your-app.ondigitalocean.app`** but `.env` still says **`http://localhost:5000/...`**, Google still gets **localhost** from your server → either add that exact localhost URI (rarely what you want on prod) or set **`GOOGLE_CALLBACK_URL=https://your-app.ondigitalocean.app/api/auth/google/callback`** on the server and add that URI in Google Console.
  3. Trim spaces: accidental spaces at the end of `GOOGLE_CALLBACK_URL` in `.env` cause mismatch; this project **trims** Google env values on load.
  4. **Authorized JavaScript origins** should include your API origin (e.g. `http://localhost:5000` and your production API origin).
- **Immediately back to app with `?error=google_auth_failed`:** Usually session/state. Ensure the API uses `saveUninitialized: true` for `express-session` (this repo does). Clear cookies for `localhost` and retry in a normal browser tab (not Swagger "Try it out" for the first hop).
- **"Access blocked" / consent:** Finish **OAuth consent screen** in Google Cloud. If publishing status is **Testing**, add your Google account under **Test users**.

**Account linking:** On **sign in** (`/google`), if a user already registered with email/password and Google returns the same verified email, `google_id` is linked. On **sign up** (`/google/register`), an existing email returns `?error=email_already_registered` instead of linking.

**Packages:** `passport`, `passport-google-oauth20`, `express-session`.
