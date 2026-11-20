# Conversation intelligence and personalization

## What changed

JARVIS keeps recent completed turns, carries bounded extractive quotes from older turns, retrieves topic-relevant approved memories, and supports explicit recall of saved conversations. Tone/detail settings provide a consistent style while preserving the same privacy and capability boundaries. No automation, model download, or new dependency is introduced.

The system prompt instructs the model to distinguish user-reported/saved claims, verified facts, assumptions, and unknowns; to prefer current explicit corrections over older claims; and to ask for clarification when references are ambiguous. It must not invent previous conversations or claim a memory write occurred. These are model instructions, not a guarantee against hallucination. The app itself still has no computer-control tools.

## Follow-ups and relevant memories

Short references such as “What about its battery?” use the last completed user topic to form a retrieval query. Explicit topic changes use the new question alone. Retrieval uses normalized words, simple plural handling, stop words, and inverse-frequency weighting. Saved preferences no longer bypass relevance checks, so an unrelated editor preference is not inserted into a question about lunar eclipses.

This is local lexical retrieval, not semantic search. Synonyms, ambiguous pronouns, multiple matching projects, and indirect references may require clarification. Recent user/assistant turns remain source context; historical assistant output is not promoted to verified fact. No automatic memory extraction occurs.

## Long sessions and summaries

The browser retains up to 10 completed recent pairs within the existing 30000-character request-history cap. When older whole pairs are removed, it builds a **deterministic extractive summary** of source-labelled quotes, with individual excerpts limited to 220 characters. Up to 16 summary cards retain initial anchors and a rolling tail. The serialized summary is capped at 4500 characters and travels as `context_summary` on subsequent requests.

This summary is not an AI-written account of what happened and does not invent decisions or facts. It is lossy: middle details and parts of long turns can be omitted. The SESSION CONTEXT panel shows it and provides a confirmed clear action. Clearing it leaves recent context, visible messages, and saved SQLite data unchanged. Reloading clears temporary context and summaries; no browser localStorage or server summary store is used.

The backend can also quote a small number of older request turns that do not fit its immediate window. Prompt instructions, style, current question, recent whole turns, summary, approved memories, and archive excerpts share an approximate character budget (normally three times configured context tokens, with a floor preserving the current question and core instructions). Supplemental data is bounded and may be omitted to preserve current context. At most three approved entries and two archive excerpts are supplied. Only a bounded prefix of the browser summary fits the prompt. This is not exact tokenizer accounting; Ollama still enforces its token context, especially for multilingual content.

Neither summaries nor retrieved excerpts are included in archive writes. Only the new completed pair is saved when both existing history consents are active. A new AI answer may repeat referenced information; that visible answer can then be archived under the same consent rules. A displayed summary therefore does not imply persistent memory, full recall, or archival approval.

## Prior-conversation references and permission

The memory panel has a new, separate **Recall previous conversations** checkbox, off by default. Memory must be enabled to approve this permission. It persists locally, and disabling memory clears it along with future-history consent.

Even with permission, archive retrieval runs only when the question refers to an earlier conversation, such as “last time”, “yesterday”, “previous chat”, or “What did we discuss?”. “Earlier in this chat” uses current session context instead. Retrieval scans up to 500 recent saved turns, filters sensitive content again, and selects relevant excerpts. A topic-free “last time” reference uses the newest eligible saved conversation. The current conversation is excluded when its ID is available in the request. If no matching authorized record fits, the model is instructed to say so and ask for details rather than invent recall.

Archives contain historical user statements and AI answers, not independently verified facts. Enabling recall does not enable history saving, create new archives, change previously approved memories, or persist summaries. Records that were never saved cannot be recovered. Archive timestamps/source IDs help distinguish conversations, but relative dates are not a full calendar/date-range search engine.

## Assistant preferences

Expand ASSISTANT PREFERENCES to choose:

| Setting | Options |
| --- | --- |
| Tone | Professional, friendly, formal |
| Answer detail | Balanced, concise, detailed |

Changes initially apply only to the current browser session through the next chat request. They do not write SQLite. To persist them, memory must be enabled and the exact tone/detail must be explicitly approved before clicking Save assistant preferences. Changing a selection clears approval. Saved settings are reloaded for later sessions when memory is enabled; explicit session choices override them. Use session defaults changes only this session until separately approved for saving.

Disabling memory restores session defaults instead of silently continuing to use a previously loaded saved style. Existing approved free-text preferences can still be viewed/edited/deleted in the memory panel; they now require topic relevance for retrieval. Style settings accept only bounded enums, not arbitrary system prompt text, secrets, or changes to safety/capability rules.

## Storage compatibility and API

SQLite schema version 2 adds an `options` table for archive-recall permission and approved assistant style. Version-1 data is readable without migration or writes. The table/version is added idempotently on the next already-authorized settings/save/archive operation; existing memories and history are preserved. Merely loading chat or reading style does not create a database. Default recall is false and default style is professional/balanced when no saved configuration is accessible.

- Chat adds optional `context_summary` (maximum 5000 characters) and `assistant_preferences` (`tone`, `detail`) fields. System-role injection and unknown style fields remain rejected.
- `GET /memory/personality` reads saved style when authorized memory is enabled, otherwise defaults.
- `PUT /memory/personality` requires valid tone/detail, `approved:true`, and enabled/allowed memory.
- `PUT /memory/settings` accepts `recall_history`, default false, separately from `save_history`.

No transcript/summary is logged or silently saved by these features. Existing credential filtering, unencrypted local SQLite storage limits, confirmed deletion, operator disablement, and no-cloud behavior remain as documented in [MEMORY.md](MEMORY.md). An in-flight request cannot retract references it already received; start a new page session to discard temporary context.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p test_conversation_intelligence.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm test
```

Tests use synthetic memories, temporary SQLite files, and injected/intercepted model responses. They cover follow-ups, topic changes, irrelevant preferences, archive permission, inaccessible prior conversations, bounded prompt construction, summary non-persistence, style approval/disablement, version-1 migration, and longer browser sessions. Ollama was checked and remains unreachable, so live language quality, ambiguous real-world follow-up resolution, and hallucination rates are unverified. No dependencies or models were installed/downloaded and no personal database was enabled during testing.

Startup remains the existing backend and frontend commands in the README. Restart an old backend to load API v0.6.0.

Verification: all 67 backend tests and 25 Chromium browser tests passed, along with the TypeScript/Vite production build and Python dependency checks. The existing non-failing Starlette HTTPX deprecation warning remains. The real personal memory database stayed uncreated/disabled during testing; all persisted test records used temporary SQLite files. Live Ollama response quality remains unverified.
