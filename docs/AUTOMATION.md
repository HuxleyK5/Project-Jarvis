# JARVIS automation engine

The engine converts one requested outcome into a bounded, ordered plan over the existing six tools. The local model proposes JSON only. Application code assigns permissions, validates literal inputs, starts approved tools, verifies observable results, and reports completed/incomplete steps. Ordinary chat still does not execute actions.

## Use the dashboard

Start the independent backend and frontend as described in the README, then open `http://127.0.0.1:5173`.

1. In **COMPUTER TOOLS**, approve the specific folders/apps/sites you want available. Enabling tools alone allows system information; folder access still requires selected roots.
2. In **WORKFLOWS**, explicitly enable automation. Optionally approve automatic execution for selected low-risk tools. Approve metadata history and apply the permissions.
3. Describe a complete outcome, for example: “Check system information, then list my approved project folder.” Choose **Generate workflow plan**. Ollama must be available; no model is downloaded. If the full outcome is unsupported or ambiguous, clarify it instead of accepting a partial interpretation.
4. Inspect the outcome, ordered tools, exact arguments, categories, and any blocked steps. Confirm the whole exact plan when required, then start it. A plan containing any blocked step cannot execute even its safe prefix.
5. View per-step results/verification and completed/incomplete step numbers. Use **Cancel workflow** to stop remaining work. Disable automation and tools when finished.

Manual structured plans work without Ollama and use exactly the same validation and permissions. The initial example checks system information twice so the sequential engine can be exercised without opening windows or accessing documents. To list a folder, use its current approved root ID from the tool policy; do not put an arbitrary absolute path in the arguments.

## Permission categories

| Category | Assignment and execution behavior |
| --- | --- |
| Automatic | Only `system_info`, `list_directory`, and `search_files`, and only when explicitly opted into automatic workflow permission. Tool/root approvals still apply. Starting the requested plan needs no additional confirmation checkbox. |
| Confirmation required | Every other authorized tool, including `read_text`, `open_application`, and `open_website`. Low-risk tools also use this category unless approved for automatic use. The exact complete plan must be confirmed before any step starts. |
| Blocked | Unknown tools, invalid inputs, absent/revoked tool permissions, inaccessible paths, or anything outside the fixed registry. Blocks the entire plan. |

The model cannot assign categories or grant permissions. Client-supplied risk/approval fields inside plans are rejected. Workflow permissions are separate from single-tool approvals, default off, and reset on backend restart. They can narrow existing tool permissions but never expand them. User-approved automatic workflow execution does not change the original single-tool panel's per-action approval behavior.

## Execution, verification, and failure

Plans contain one to eight static steps with schema-validated literal arguments. No shell/code, loops, substitutions, result expressions, arbitrary executables, document writes, or dynamically generated next steps are supported. Model-selected document reads require the exact relative document path in the original request. Unsupported tool names in an explicit plan are shown as blocked; they cannot run.

Planning never executes. An explicit start request is required, and confirmation is required if any step needs it. Immediate approvals expire after five minutes. Plans cannot be edited after creation or replayed after execution; submit a new plan to change or retry actions. At most one workflow worker and one tool worker can run. A conflicting manual tool causes a safe failure rather than an automatic retry. Tool/automation permission revisions invalidate prior plans, even if a root-free system tool remains individually authorized. Permissions and inputs are rechecked before each step and during polling.

The engine calls the same registry used by the original tools panel. Cancellation propagates to its current operation and prevents future steps. Enumeration/read cancellation is cooperative. Already completed actions are not undone; blocking OS calls cannot be forcibly interrupted, and opened apps/sites are not closed. A cancelled native worker must finish before another tool may start. Workflow deadline: 180 seconds; step wait deadline: 20 seconds, in addition to the registry's existing bounded file traversal.

Verification uses deterministic tool-specific result checks, rather than asking the AI whether it succeeded:

- System information: structured current OS/disk result; unknown fields remain unknown.
- Listing/search: structured bounded entries; empty matches are valid, and truncation is disclosed.
- Document read: returned text, length, and untrusted-document marker; text claims are not independently verified.
- App/site opening: Windows accepted the launch handoff. Visible window state, final website loading/redirects, and semantic outcomes remain **unverified**. A completed launch step means only its handoff completed, not that the requested content was inspected.

On failure or failed verification, remaining pending steps are skipped. The report retains successful prefix steps and lists every incomplete step. No automatic retries can duplicate launches. A logging failure before execution blocks it; a later logging failure stops remaining work and appears in the session report. Final history-write failure is disclosed instead of falsely claiming durable recording.

## Future workflows with APScheduler

The optional adapter targets APScheduler **3.x** `AsyncIOScheduler`, using one-time date triggers, explicit UTC/offset-aware timestamps, a 30-second misfire grace period, coalescing and one instance. See the official [asyncio scheduler documentation](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html) and [user guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html).

**APScheduler is not installed, as requested.** No dependency was installed or downloaded. The UI reports scheduling unavailable, disables schedule controls, and the API returns a clear 503. Immediate workflows work with existing dependencies. `backend/automation/requirements.txt` declares the optional package; installation requires a separate explicit approval. The real adapter test is skipped in this environment; scheduling policy is tested with an injected scheduler.

Once the package is available, a fresh unexecuted plan can be scheduled within seven days, with separate approval of its time. The UI converts the browser's local timezone into an explicit ISO timestamp; the backend rejects naive times. The timezone is displayed beside the scheduled time. The backend must remain running. No recurring schedules, Windows Task Scheduler integration, or system settings are added.

At the due time all permissions are revalidated. Entirely automatic plans start; plans containing significant actions become `awaiting_confirmation` without executing any prefix. These require fresh exact-plan approval within five minutes. Missed or conflicting starts fail honestly and are not silently replayed. Cancelling removes the schedule. Schedules are in-memory and are not restored after a backend restart; this prevents persisted approvals from resurrecting actions under a new session.

## Privacy and history

Executable plans, outcomes, arguments and results stay in bounded backend/browser session memory: up to 100 workflows of eight steps. Restart clears them, pending schedules, permissions and tokens. File contents are not returned to the model or used as instructions, and are not saved as conversation memory. Existing memory/history consent controls remain unchanged. The planner receives only the explicit request plus existing tool schemas and approved directory/app/site catalog.

Explicitly approving workflow permissions includes local execution-metadata history in ignored **`data/workflow-history.jsonl`**. It records workflow ID, UTC timestamp, status, completion counts and known tool names; no instruction/outcome text, paths, website URLs, arguments, document text, raw errors or results. Unknown tool names are recorded as `blocked_tool`. The history survives restart and displays the latest 100 events, but cannot be used to re-execute a plan. Existing `data/tool-audit.jsonl` continues recording tool transitions separately. Disabling automation stops execution; existing metadata remains viewable and is not silently deleted.

Local tool origin/Host checks and `X-Jarvis-Tool-Token` also protect every automation route. All responses use `Cache-Control: no-store`. This protects dashboard requests; it is not a sandbox against processes already running as your Windows account. The existing directory/link/size/privacy restrictions in [TOOLS.md](TOOLS.md) apply unchanged.

## API v0.8

Get the token from `GET /tools/session`. Every route below requires `X-Jarvis-Tool-Token` through the localhost dashboard proxy.

| Route | Contract |
| --- | --- |
| `GET /automation/policy` | Enabled flag, automatic/eligible tools, scheduler availability |
| `PUT /automation/policy` | `{enabled,automatic_tools:[],approved:true}`; permission changes cancel outstanding workflows |
| `POST /automation/plan` | `{question}`; returns `{workflow}` or `{workflow:null,message}` using the local brain/model lock |
| `POST /automation/plans` | Strict `{outcome,steps:[{tool,arguments}]}`; validated explicit plan without AI |
| `GET /automation/workflows` | Current session plans and step reports |
| `GET /automation/workflows/{id}` | One session plan, ordered step states/results and completion report |
| `POST /automation/workflows/{id}/start` | `{approved:true}` for confirmation plans; automatic plans may send `{approved:false}` |
| `POST /automation/workflows/{id}/cancel` | Cancel pending/scheduled/running workflow |
| `POST /automation/workflows/{id}/schedule` | `{when:"ISO timestamp with offset",approved:true}`; optional APScheduler required |
| `GET /automation/history` | Latest 100 persistent metadata events, newest first |

The model planner shares the chat generation lock; its unavailable/busy/timeout/invalid JSON states are errors, never fabricated successful plans. A permission change while model planning is in progress invalidates the generated plan. Errors follow the existing `error.code`/`error.message` contract. Full input schemas appear in `/openapi.json`.

## Verification commands

```powershell
# Repository root
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
.\.venv\Scripts\python.exe -B -m pip check
# frontend directory
npm run build
npm test
```

`backend/tests/test_automation.py` tests real sequential read-only tools, injected natural-language planning, permission categories, blocked plans, confirmation, verification failures, partial reports, cancellation, replay/expiry, history persistence/privacy, worker exclusivity, schedule revocation, missed runs, missing dependencies, registration errors and localhost API protection. Actual app launch handoffs are mocked. The optional real APScheduler one-time callback test is skipped when the package is missing.

`frontend/tests/automation.spec.ts` exercises automatic multi-step execution against the actual backend, exact confirmation, cancelled previews, blocked plans, history/activity, and injected model proposal/error states. Live Ollama planning quality and real app/page visibility are not claimed by synthetic tests.

Verified in this environment: **123 backend tests passed, one real APScheduler test skipped, all 30 Chromium browser tests passed**, and TypeScript/Vite production build, Python dependency consistency, and whitespace checks passed. APScheduler and all other dependencies were left unchanged. Tool and automation permissions were left off; no personal memory database was created or enabled. Persistent workflow history contains synthetic operational metadata from the tests.
