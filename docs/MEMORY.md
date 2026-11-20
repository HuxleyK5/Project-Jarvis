# Phase 3: local SQLite memory

## Defaults and what is saved

Memory and history storage default **off**. Startup, status checks, and ordinary chat do not create the database when no memory file exists. Python's built-in [sqlite3 module](https://docs.python.org/3.12/library/sqlite3.html) provides local storage without an additional server, package installation, embedding model, or paid API.

The dashboard's **SAVED MEMORY & CONVERSATIONS** panel has separate controls:

- **Enable persistent memory** enables approved-entry saving and retrieval. This choice persists across restarts.
- **Save future conversation history** separately approves saving subsequent completed user/AI pairs, including on later visits until turned off. The UI states this explicitly. Disabling memory also clears history consent, so re-enabling does not silently re-enable history saving.
- Preferences, important projects, and useful facts are saved only through the reviewed-text form and **Approve and save memory**. Editing resets approval and requires approving the exact updated text again. Chat requests cannot silently create or edit such memories.
- Archived history stores only the latest newly completed question and answer with IDs/timestamp. It does not backfill the supplied temporary context, failed/stopped/partial answers, wake acknowledgements, microphone audio, or synthesized audio. History is committed only if both the persisted setting and that chat request's opt-in are true. A visible stream notice explains saved, duplicate, disabled, sensitive-skipped, or failed storage.

Saved entries and archived exchanges are searchable/viewable in the panel. Entry edit/delete and exchange delete controls are provided. Deletion requires a confirmation dialog and API confirmation flag. Disabling memory stops new saving and approved-entry retrieval but retains data for viewing/deletion; it does not erase the database. Saved history is not automatically reopened as a new chat or converted into approved facts.

## Storage and configuration

Default file: `data/memory.sqlite3`, ignored by Git. SQLite files/journals are additionally ignored by extension. The file is created lazily by an explicit memory settings/save action. Schema version 2 adds optional recall/style settings while preserving version-1 records. Each operation opens/closes its own connection and uses bound SQL parameters. Write transactions serialize consent checks and writes so a committed disable is honored before another save proceeds.

| Environment setting | Default | Effect |
| --- | --- | --- |
| JARVIS_MEMORY_DB | repo/data/memory.sqlite3 | Optional local database file path; restart to change |
| JARVIS_MEMORY_ALLOWED | 1 | Set exactly 0 to block enablement, new writes, and retrieval; existing records remain viewable/deletable |

The environment example is not auto-loaded. This implementation stores an ordinary **unencrypted** local SQLite file. Anyone with access to it can read it. No cloud sync, backup, encryption, or remote database is configured. SQLite may use transient rollback journals. API data responses and frontend fetches use no-store behavior; the app does not intentionally log memory text or rejected content.

Deleting removes records from application searches/retrieval. The connection requests SQLite's [secure_delete behavior](https://www.sqlite.org/pragma.html#pragma_secure_delete) to clear deleted cells, but that is not a guarantee of forensic erasure from filesystem snapshots, backups, OS storage, or browser/AI runtime memory. No backups or existing personal data were deleted during development. Removing a saved entry also cannot retract information already supplied to an in-flight AI request or temporary conversation; start a fresh page/session when that matters.

## Privacy filtering and limits

Passwords and authentication information must never be entered for storage. `privacy.py` rejects known credential labels/patterns, private-key markers, common API-key/JWT shapes, credential-bearing URLs, and long credential-shaped values. It also conservatively blocks detected personal-data categories such as SSNs, payment/account details, diagnoses, birth dates, and home-address labels. There is no override to save a detected secret. If either side of a completed exchange matches, the entire exchange is skipped rather than partially redacted or hashed into the archive. Synthetic tests confirm rejected strings do not appear in the SQLite file.

This filter is a **heuristic**, not a semantic guarantee that arbitrary unlabeled secrets or sensitive descriptions can be recognized. It can both miss novel formats and reject harmless technical discussion mentioning credential terms. The reviewed-text approval and opt-in history controls are additional privacy boundaries, not permission to store credentials. Do not use JARVIS as a password manager or enter authentication secrets. For sensitive conversations, keep history off. No model-driven automatic memory extraction or background sensitive-data collection is implemented.

## Retrieval and temporary context

The browser's existing recent-turn context remains temporary. SQLite memory is a separate manager; no transcript is automatically restored into it on reload. When persistent memory is enabled, lexical retrieval ranks up to five approved entries. Brain includes at most three shortened entries when they fit the shared context budget; unrelated preferences are excluded. The server adds them as quoted reference data with instructions not to execute embedded requests. All entries, including preferences, now require a topic match; unrelated preferences are omitted. This is lightweight lexical retrieval, not semantic/vector search or a guarantee that the model will use every record correctly.

Conversation archives remain searchable by the user. Model recall additionally requires the separate recall_history approval and a reference to an earlier conversation; archived answers are labelled historical claims. Otherwise only relevant approved entries are retrieved. Records are normalized for case, Unicode compatibility, repeated whitespace, and trailing sentence punctuation, with a database unique constraint preventing equivalent memories even across categories. The user's displayed wording is retained. Conversation duplicates are suppressed by request ID and normalized exchange fingerprint within the same conversation. No automatic merges or destructive overwrites are performed.

Search shows up to 100 matches. Literal archive searches escape SQL wildcard characters and use parameter binding. Browser content is rendered as text rather than HTML. Approved-entry context adds a bounded amount of prompt text; older temporary turns may still be trimmed by the existing context policy. Database errors omit retrieval so ordinary chat can proceed; history storage failure produces a notice without losing a completed AI answer. Memory-management errors are returned without leaking SQL values.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET / PUT | /memory/settings | Read settings / explicitly approve enablement and history choice |
| GET | /memory/entries?q=... | View/search saved preferences, projects, and facts |
| POST | /memory/entries | Save `{kind, content, approved:true}` |
| PUT | /memory/entries/{id} | Approve an edit using the same fields |
| DELETE | /memory/entries/{id}?confirm=true | Delete one approved memory |
| GET | /memory/conversations?q=... | Search/view archived exchanges; optional conversation_id UUID filter |
| DELETE | /memory/conversations/{turn_id}?confirm=true | Delete one archived exchange |

Setting body: `{enabled:true, save_history:false, approved:true}`. New databases start disabled. Memory kinds are `preference`, `project`, and `fact`; content is limited to 2000 nonblank characters. Duplicate saves return 409; missing approval/disabled writes return 403; invalid/sensitive content returns 400 or validation 422; missing records return 404. The local API has no multi-user authentication; it relies on the existing loopback-only deployment and browser same-origin restrictions, not isolation from other programs on the computer.

Optional chat fields for opted-in archive saving: `save_history:true`, `conversation_id` UUID, and `turn_id` UUID. The browser uses a new conversation ID per page session and a new turn ID per send. The stream adds `{"type":"memory","status":"saved"}` (or `duplicate`, `disabled`, `skipped_sensitive`, `error`) before its normal done event. Without request opt-in, the chat contract is unchanged and no archive write is attempted.

## Run and verify

Startup is unchanged. From the project root:

```powershell
.\.venv\Scripts\python.exe -m backend.main
```

In another terminal:

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173 and expand the memory panel. Restart an old backend to load the new routes. Nothing is saved until the user enables the relevant feature and approves it.

Tests:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p test_memory.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm test
```

Memory tests use temporary databases and synthetic content only. They cover approval, credential filtering, normalization/duplicates, search, edit/delete confirmation, disablement, retrieval, opted-in successful chat, and exclusion of failed/non-opted-in exchanges. One test actually starts a local backend process on an isolated port, saves a synthetic project, stops that process, restarts it using the same temporary database, and verifies the project/settings persisted. Another verifies archived chat across app-instance restarts. Browser memory tests use intercepted storage responses and validate approval/edit/delete/search and history notices without enabling the user's real database. Existing missing AI/voice prerequisites remain unchanged; no live model inference is implied by memory tests.

Verification completed November 20, 2026: 56 backend tests and 22 browser tests passed, including actual process-restart persistence. The TypeScript/Vite production build and Python dependency consistency checks passed. No dependencies were installed and the project's real memory database was not created or enabled. The pre-existing non-failing Starlette HTTPX deprecation warning remains.

Conversation continuity, extractive session summaries, assistant style, and schema compatibility are detailed in [CONVERSATION.md](CONVERSATION.md). Temporary summaries are not persistent memory.
