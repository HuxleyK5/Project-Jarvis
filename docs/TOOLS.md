# Phase 4: permission-controlled computer tools

Tools default **off** on every backend start. No dependency installation, model download, or system setting change is required. Open the dashboard's **COMPUTER TOOLS** panel. Approve the session permissions, preview one manual or model-selected action, and approve its exact inputs before running it. Ordinary chat does not execute tools.

The separate [automation engine](AUTOMATION.md) can sequence these same capabilities under its own explicitly approved workflow permissions. Its automatic low-risk opt-in and significant-action confirmation do not change this panel's single-action approval behavior or expand file/app/site access.

## Capabilities

| Registry name | Inputs | Result and limits |
| --- | --- | --- |
| `system_info` | `{}` | Current Windows/OS, processor, logical CPUs, RAM when detectable, workspace drive capacity/free bytes. Unknown RAM is `null`. No GPU inference. |
| `list_directory` | `root`, optional relative `path` (default `.`) | Immediate file/folder names; at most 100 results. |
| `search_files` | `root`, optional `path`, `query` | Case-insensitive literal filename matching, recursive, at most 100 results/5000 scanned entries/10 seconds. Does not search file contents. |
| `read_text` | `root`, exact relative `path` | One user-selected UTF-8 `.txt`, `.md`, `.rst`, or `.csv` document, up to 64 KiB. Binary, hard-linked, and detected sensitive documents are refused. |
| `open_application` | `application` | Approved `notepad` or `calculator`; fixed executable in the actual Windows system directory, no arguments, `shell=False`. Reports Windows accepting the launch request, not verified visible app state. |
| `open_website` | `website` | An exact approved HTTPS URL, opened with the Windows URL association. No credentials, custom port, query or fragment. Reports launch acceptance, not page loading. |

Each definition includes a description and strict Pydantic-generated JSON input schema. Unknown tools, extra fields, wrong types and unauthorized IDs fail validation. Root and website IDs come from current session permissions; they are regenerated when permissions change.

## Permissions and privacy

The permission form approves existing absolute local directories and the built-in application/website allowlists. It does not grant execution authority: **every action requires a separate exact preview and approval**. Enabling system information alone needs no approved directories. Folder approvals include their ordinary subfolders. Choose the narrowest folder you intend to expose; drive roots, network shares, hidden paths, system/dependency/credential folders, and reparse/link paths are blocked. Approval is session-wide for all local dashboard tabs, rather than per browser tab.

Relative paths cannot contain traversal, drive prefixes, alternate data streams, device names, hidden components or trailing-dot/space aliases. Paths and approval are revalidated at execution; traversal checks repeat during search. File reads verify the actual opened handle remains inside the approved directory before reading. Do not use an approved folder concurrently modified by untrusted local processes: path checks are not an operating-system sandbox, particularly for directory enumeration races. This local tool layer does not grant privileges or defend against another process already running with your Windows account's access.

The existing conservative memory privacy detector also refuses potentially sensitive documents. It can produce false positives and cannot detect every secret. Review the selected document and approve only intended content. Results appear as escaped text, never HTML or executable instructions. File contents/results are not sent to Ollama, stored as approved memory, or archived with conversation history. The planner receives only the explicit tool request, schema catalog, and approved folder/site/application catalog. Normal memory/history controls are unchanged.

The only tool-system writes are its own append-only **`data/tool-audit.jsonl`**. It records timestamp, event ID, operation ID, known tool name and status; no file paths/names, URLs, document contents, requests, errors or results. Logging is disclosed in the permission checkbox and independent of chat-history saving. Rejected validated proposals and execution transitions are logged. HTTP authorization/input-validation failures are denied before registry execution. A log-write failure prevents a new action from starting; cancellation and disabling remain possible. Existing logs are never cleared automatically. Review local logs before sharing them.

Application/browser launch hands off to approved existing software, which can have its own network, session-restoration, and storage behavior. HTTPS approval controls the initial URL, not subsequent website redirects, downloads, or navigation. JARVIS does not verify the final visible state.

## AI selection and cancellation

The **Ask JARVIS to select a tool** control uses the existing local provider and the same generation lock as chat. `Brain.select_tool` asks for one strict JSON selection or `null`; the registry validates it against current permissions. Invalid, unsupported or unapproved selections never execute. A model-selected document must also be named in the user's request. Ambiguity returns an honest no-selection response; the manual controls remain usable without Ollama. No prompt can create or expand permissions.

Proposals expire five minutes after creation. Replays fail; at most one active tool worker is permitted. Permission changes cancel pending/running actions. Cancel works before approval and cooperatively during enumeration/reading. Cancelling selection aborts the browser request; depending on disconnect timing, the model may finish generating an unapproved proposal. It can never execute without a later approval request. Cancellation cannot undo a launch already handed to Windows, and blocking OS calls cannot be forcibly interrupted; a cancelled worker discards results. Tools do not terminate apps or close browser windows.

Operations/results exist only in bounded server memory (up to 200 operations); activity metadata is bounded to 200 events and the dashboard feed to 50. Dismissing a result hides it in that tab; restarting the backend clears in-memory operations, permissions and session tokens. Persistent audit metadata remains. No deletion/overwrite tool, arbitrary command execution, generic executable path, app arguments, keyboard/mouse control, or autonomous multi-step workflow is available.

## API

Tool responses use `Cache-Control: no-store`. Tool routes reject non-loopback Host, untrusted Origin and cross-site browser fetches; no CORS access is enabled. `GET /tools/session` supplies a fresh-backend session token and catalog to the same-origin local dashboard. All other tool routes require `X-Jarvis-Tool-Token`. Tokens are held only in browser/server memory; use the Vite same-origin proxy. This is local dashboard request protection, not user authentication against local processes.

- `GET /tools/policy`: effective permissions, disabled by default.
- `PUT /tools/policy`: `{approved:true, enabled, directories:[], applications:[], websites:[]}`. Replaces permissions; cancels previous work. An approved disabled policy revokes access.
- `POST /tools/proposals`: `{tool, arguments}`; validates and returns a pending operation, never executes it.
- `POST /tools/plan`: `{question}`; returns `{proposal}` or `{proposal:null,message}`. Requires Ollama readiness.
- `POST /tools/operations/{id}/execute`: `{approved:true}`; starts an approved operation and returns its snapshot.
- `GET /tools/operations/{id}`: poll pending/running/completed/failed/cancelled/expired, result and sanitized error.
- `POST /tools/operations/{id}/cancel`: cancel remaining work; no approval required.
- `GET /tools/activity`: session operational metadata, newest first.

Schemas are available in `/openapi.json` and the tool catalog. Errors follow the existing `error.code`/`error.message` contract.

## Run and verify

From the project root, start the backend:

```powershell
.\.venv\Scripts\python.exe -B -m backend.main
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`, expand COMPUTER TOOLS, approve session permissions, choose `system_info`, preview, approve and run. Inspect the result and activity feed. Choose a small folder you own to test listing/search and explicitly select a harmless UTF-8 text file to test reading. Cancel a preview and confirm it never runs. Disable tools when finished. Opening apps/sites requires separate allowlist and action approvals.

```powershell
# Project root
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
# frontend directory
npm run build
npm test
```

`backend/tests/test_tools.py` tests all six tools independently, including real temporary file operations, current system information, path/size/privacy restrictions, approvals, cancellation, expiry, logging, API request protection and injected model selection. App/browser handoffs are mocked so tests do not open windows or contact websites. `frontend/tests/tools.spec.ts` exercises approval/preview/result/activity/cancel/revocation against the real local API and model-proposal/error states with explicit mocks. Ollama was unavailable during development, so actual model tool-selection quality remains unverified; no inference or successful launch of app/browser windows is claimed by these tests.

Verification: 96 backend tests and all 27 Chromium browser tests passed, along with the TypeScript/Vite production build and Python dependency consistency check. The tool browser tests were rerun after the final UI/default-selection changes. No personal memory database was enabled or created. Backend tools were left disabled after verification; the audit contains synthetic test-operation metadata only.
