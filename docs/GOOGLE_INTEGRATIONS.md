# Phase 5: Google productivity integrations

Calendar, Gmail and Classroom are independently enabled adapters under `backend/integrations/google/`. They call official HTTPS REST APIs using the existing HTTPX dependency. No dependency, model, credential or account was installed/downloaded/connected during development. They default **disabled** on each backend start. Ordinary chat and automatic workflows cannot invoke these external writes.

## Available capabilities and limits

| Service | Implemented | Deliberate limits |
| --- | --- | --- |
| Calendar | Read upcoming primary-calendar events; preview and approve event creation | Next 30 days, at most 50 events, with a more-results notice. Creation targets primary calendar, offset-aware timed events only. No guests, invitations, recurring-event editing, calendar management or deletion. |
| Gmail | Search messages, read a selected message/thread, explicitly summarize locally, preview/create drafts, preview/send mail | Message search returns up to 20 IDs per page; bodies are read only on selection. Latest 10 thread messages, bounded plain-text excerpts/snippets. No attachment downloads, remote images, HTML execution, mailbox modifications, hidden recipients, aliases or automated sending. |
| Classroom | Read active permitted courses and published coursework, due dates/times, grouped by class | Student scope by default; optional explicit teacher role uses its corresponding read-only scope. No roster/profile, submission, grade or course writes. Access remains limited by Google and school policies. |

Calendar exposes source start/end date-times. All-day event end dates follow Google's exclusive-end convention. Classroom source due dates/times are UTC and complete date-times display in the browser's timezone; absent dates/times are marked unavailable instead of invented. Coursework access is defined by Google's [list method](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork/list) and [CourseWork resource](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork).

## First-time setup: your Google Cloud project

No account credentials are needed in chat, source code, frontend environment variables, or the browser console. Google account setup and OAuth consent must be completed by you in Google's own interface.

1. Create/select your project in Google Cloud Console and enable the Google Calendar API, Gmail API, and/or Google Classroom API for the services you intend to use. Enable only desired APIs.
2. Configure the OAuth consent screen/audience. For a permitted personal test project, add your own account as a test user when required. Managed Workspace accounts may require an administrator-approved application. Follow Google's verification process and your school's policy; do not circumvent blocked access.
3. Create an OAuth client of type **Desktop app**. Download its client JSON to a private location outside the repository. Web-client and service-account JSON files are rejected. Google documents this [desktop OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app).
4. Stop the backend before importing/changing the client. From the repository root, run:

```powershell
.\.venv\Scripts\python.exe -B -m backend.integrations.google.setup --client-file 'C:\private-location\client_secret_example.json'
```

The command reads the file and stores only the client ID/secret encrypted with the current Windows user's DPAPI. Imported endpoint URLs are ignored; all OAuth/API endpoints are fixed in code. It does not modify/delete the downloaded source JSON. Protect that original file outside source control; it is still your plaintext download. Common credential filenames and all local runtime data are ignored by Git, but review files before committing.

5. Start JARVIS normally:

```powershell
# Repository root, first terminal
.\.venv\Scripts\python.exe -B -m backend.main
# Second terminal
cd frontend
npm run dev
```

6. Open `http://127.0.0.1:5173`, expand **GOOGLE PRODUCTIVITY**, and enable one service. Choose its capabilities, approve encrypted credential storage, and apply. Inspect its scope list before connecting. Select **Connect or renew**, then open the Google consent link in your normal browser. Choose the intended Google account and approve there. Return to JARVIS after the callback tab reports completion. Each service has its own consent action and credential slot; the application does not assume all three use the same account.

If setup is absent, the dashboard shows setup required and disables connection/data controls. Missing credentials are not replaced with test data. Changing the imported client requires reconnecting; old tokens are bound to the client ID that issued them.

## OAuth and necessary permissions

The desktop flow uses random state, per-attempt PKCE S256, a five-minute expiry, and a temporary server bound to `127.0.0.1` on an OS-assigned port. It opens no public listener, embedded sign-in view or deprecated copy/paste authorization flow. The callback listener validates state, host and single-use flow state and does not log authorization URLs/codes. The verifier and authorization code remain in process memory. Tokens are exchanged only with Google's fixed token endpoint.

Each connection requests exactly the current service/capability scopes, without an incremental-authorization flag. Desktop OAuth does not support Google's web-style incremental authorization. Capability changes that require missing scopes show permissions missing and require a new consent flow. A prior broader grant may still exist at Google; app-level controls remain narrower until explicitly enabled. Revoke the cloud grant to remove prior permissions, then reconnect with only the desired capabilities.

| Feature | Requested scope suffixes, under `https://www.googleapis.com/auth/` |
| --- | --- |
| Primary Calendar read | `calendar.events.owned.readonly` |
| Calendar read + proposed creation | `calendar.events.owned` |
| Gmail read/search/summary source | `gmail.readonly` |
| Gmail drafts | Additionally `gmail.compose` |
| Gmail send without drafts | Additionally `gmail.send` |
| Gmail drafts + send | `gmail.readonly` + `gmail.compose`; compose already includes sending |
| Classroom student | `classroom.courses.readonly` + `classroom.coursework.me.readonly` |
| Classroom teacher | `classroom.courses.readonly` + `classroom.coursework.students.readonly` |

These are the narrow available scopes for the implemented methods; Google does not provide an event-create-only or draft-create-only scope. Its compose permission is broader than JARVIS's draft feature and includes sending; JARVIS separately requires send enablement and exact-content confirmation. No full-mailbox `mail.google.com`, Gmail modify, Calendar management, Drive, profile, roster, or identity scope is requested. Scope definitions: [Calendar](https://developers.google.com/workspace/calendar/api/auth), [Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes), [Classroom](https://developers.google.com/workspace/classroom/guides/auth).

## Secure storage and privacy

The following are encrypted, current-user DPAPI blobs under ignored local storage:

- `data/google/client.dpapi`: imported desktop OAuth client ID/secret.
- `data/google/calendar.dpapi`, `gmail.dpapi`, `classroom.dpapi`: each service's access/refresh token, client binding, expiry, and granted scopes.

No portable encryption key, plaintext-token fallback, secret in source, or token in browser storage is used. Saves encrypt before writing and atomically replace only the application's own credential blob. Encryption/decryption is verified against the real Windows API in tests. Non-Windows use fails closed. DPAPI normally ties decryption to the Windows logon user; it does not protect against a compromised process running as that same user, and moving files to another user/computer may make them unusable. See Microsoft's [CryptProtectData documentation](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

Integration enablement is session-only. Encrypted authorization persists until **Disconnect and forget tokens**, which requires confirmation and forgets only that service's local blob. Disabling blocks new calls, discards data from in-flight reads, cancels pending consent, invalidates pending write proposals and unmounts fetched content. A network write already started may have reached Google and cannot be recalled. Restart clears session enablement, proposals and fetched content; it preserves encrypted credentials.

Disconnecting does not silently revoke the shared Google project grant because that could affect the other integrations. To revoke remotely, review your Google Account's third-party access settings, then reconnect the intended services. No service accounts, domain-wide delegation, administrator impersonation or scraping fallback is implemented.

Fetched account data and action payloads live only in bounded session memory and are not added to SQLite memories, conversation archives, workflow history or execution logs. Activity messages contain service/action/status only. Uvicorn Google-route access records are redacted, outbound Google HTTPX log lines are filtered, and HTTP protocol debug traces are disabled to avoid leaking queries/headers. OAuth callback requests use a separate listener with no access logger.

Email is displayed as escaped text. Plain-text MIME parts are preferred; HTML-only messages show the available snippet with a limitation notice. Attachments/remote images are never fetched. Local AI summarization requires a separate explicit checkbox for the selected conversation, uses the existing local provider and generation lock, treats email as untrusted source data, and has no tool or memory-saving interface. Excerpts are bounded and the model is instructed to identify omissions and uncertainty. A summary is model output to review, not independently verified evidence. If Gmail is disabled/changed while summarizing, the response is discarded. Ollama unavailability is an error; there is no fabricated or paid/cloud fallback.

## External write confirmation

Event creation, draft creation and email sending each require an immutable proposal snapshot followed by explicit confirmation. Merely composing, previewing or generating a summary does not write or send anything. Proposals expire in five minutes, are single-use, and are invalidated by capability changes, reconnection/account changes or disablement. A form edit never changes an existing proposal; cancel it and preview again. All write inputs use strict schemas, including recipients without header injection and ordered offset-aware event times.

Draft creation does **not** send. A send proposal sends the exact reviewed plain-text MIME as a new message. It does not silently send an existing Google draft that another client could have changed. There is no automatic scheduling/workflow registration for Google writes in this phase. Official methods: [draft creation](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create), [message sending](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send).

No write is automatically retried. Network failure or an invalid response can leave the outcome unknown after Google accepted the request; the proposal records that uncertainty and cannot be replayed. Inspect Google before making a new proposal to avoid duplicates. Calendar proposals use a stable client-generated event ID. A completed result reports Google's resource ID, rather than claiming the content was viewed or an email was read by its recipient.

## Authentication and API restrictions

Connection status distinguishes disabled, setup required, authorizing, not connected, connected, token refresh due, permissions missing, authorization timeout, secure storage error and reauthentication required. Connected initially means usable saved authorization, not a live API check. A successful data/action request updates the last-request verification indicator; failures clear it. Status polling performs no background Google reads.

Expired access tokens are refreshed under a per-service lock and the new encrypted token is saved, including refresh-token rotation when supplied. Revoked/invalid refresh tokens and API 401 require reconnecting. Partial scope consent is rejected. Auth/network outages, malformed responses, API 403, quota 429 and write uncertainty use explicit errors without returning raw Google error payloads. An API denial is not presented as an empty course list or successful action.

Gmail read/compose scopes are restricted and can require Google's verification process for deployment; managed accounts may reject the application regardless of local implementation. Refresh tokens for external apps in Testing can expire after seven days for these scopes. See [Gmail scope policy](https://developers.google.com/workspace/gmail/api/auth/scopes) and [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration). Follow the consent, verification and administrator process; no restriction is bypassed.

Classroom's available courses/coursework depend on account role, membership, API enablement, project consent and administrator policy. Students can access only published coursework made available to them. Selecting teacher role changes the requested read scope, not the user's actual privileges. No preview/paid Classroom feature is required or fabricated. If Google denies access, JARVIS reports the limitation and the user must resolve it with the service administrator.

## API v0.9

Every `/integrations/google` route uses the existing localhost dashboard Host/Origin/session-token protection (`X-Jarvis-Tool-Token` from `/tools/session`) and `Cache-Control: no-store`. Credentials never appear in status responses. The desktop callback is separately protected by state/PKCE and its ephemeral loopback listener.

| Route | Purpose |
| --- | --- |
| `GET /integrations/google/status` | All three service flags, authorization/scopes, setup and last-request verification |
| `PUT /integrations/google/{service}/settings` | `{approved:true,enabled,write:false,send:false,role:"student"}` |
| `POST /integrations/google/{service}/connect` | `{approved:true}`; returns official Google consent URL, scopes and expiry |
| `POST /integrations/google/{service}/cancel-auth` | Stop pending consent |
| `POST /integrations/google/{service}/disconnect` | `{approved:true}`; forget the selected service's local token |
| `GET /integrations/google/calendar/events` | Bounded upcoming primary-calendar events |
| `POST /integrations/google/calendar/proposals` | `{title,start,end,description}`; offset-aware date-times |
| `GET /integrations/google/gmail/messages?q=...&page_token=...` | Authorized search, optional pagination |
| `GET /integrations/google/gmail/messages/{id}` | Selected plain-text message view |
| `GET /integrations/google/gmail/threads/{id}` | Latest bounded conversation excerpts |
| `POST /integrations/google/gmail/threads/{id}/summarize` | `{approved:true}`; explicit local AI summary |
| `POST /integrations/google/gmail/proposals/{action}` | `create_draft` or `send_message`; `{to:[],subject,body}` |
| `GET /integrations/google/classroom/courses?page_token=...` | Available active courses |
| `GET /integrations/google/classroom/courses/{id}/assignments?page_token=...` | Published coursework with due fields |
| `GET /integrations/google/proposals/{id}` | Current proposal/outcome |
| `POST /integrations/google/proposals/{id}/execute` | `{approved:true}`; one exact external write |
| `POST /integrations/google/proposals/{id}/cancel` | Cancel a pending action; cannot recall an already started request |

## Testing and verification limits

```powershell
# Repository root
.\.venv\Scripts\python.exe -B -m unittest backend.tests.test_google_integrations -v
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
.\.venv\Scripts\python.exe -B -m pip check
# frontend directory
npm run build
npm test
```

Backend tests independently cover Calendar reads/creation, Gmail search/message/thread/MIME/draft/send/summary, Classroom coursework/denial/roles, narrow scopes, approvals, replay/expiry, refresh/rotation/revocation, client binding, disable races, callback state/PKCE, denied/partial grants, logging privacy, and request protection. They use explicit synthetic HTTP fixtures, plus actual native Windows DPAPI and an actual temporary localhost callback listener. Browser tests cover real disconnected/setup states and injected authorized service responses/approvals, email display, summary consent and grouped assignments.

**No real Google credentials or consent were provided**, so live Google sign-in, account-specific API permissions and actual external writes are unverified. No real email was sent, draft/event created, or classroom account accessed. This is implemented API functionality with clear setup and restriction handling; mocked fixtures are used only in tests, never as application data.
