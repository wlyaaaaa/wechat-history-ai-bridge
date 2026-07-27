# Privacy Boundary

This document defines what may and may not enter the public repository `wlyaaaaa/wechat-history-ai-bridge`.

## Repository Classification

`E:\Projects\Tools\WeFlowBridge` is the local checkout for the public repository `wlyaaaaa/wechat-history-ai-bridge`. Treat every committed file as public material even when it describes local-only workflows.

Allowed public content:

- Endpoint notes and API behavior summaries.
- Placeholder examples such as `wxid_xxx`, `<talker>`, and `<token>`.
- Watchdog and health-check scripts that do not embed secrets.
- Public-safe troubleshooting notes.
- AI consumer contracts that describe metadata fields but not private message content.

Forbidden public content:

- `.env` and any `.env.*` real configuration.
- `WEFLOW_TOKEN`, `WEFLOW_DB_KEY`, image keys, cookies, or local account secrets.
- raw messages, full JSON exports, chatlab exports, copied chat transcripts, and durable message archives.
- screenshots of conversations, contact lists, account pages, QR codes, or private WeChat UI.
- database files such as `.db`, `.sqlite`, `.sqlite3`, WAL/SHM files, or decrypted database material.
- media exports including images, voice, video, stickers, files, and anything under `exports/`, `api-media/`, `dump/`, or cache folders.
- relationship analysis results that quote private content beyond minimal task-specific excerpts.

## Local Files

Local-only files may exist in the working directory, but must stay ignored:

| Local path or pattern | Reason |
| --- | --- |
| `.env` | Contains base URL and token. |
| `.env.*` | May contain real environment variants. |
| `logs/` | Runtime logs can reveal machine state or local paths. |
| `exports/` | WeFlow or AI export output can contain raw messages. |
| `api-media/` | Media exports are private. |
| `dump/` | Ad hoc dumps can contain full payloads. |
| `*.db`, `*.sqlite`, `*.sqlite3` | Databases are private by default. |
| `*.db-wal`, `*.db-shm`, `*.sqlite-wal`, `*.sqlite-shm`, `*.sqlite3-wal`, `*.sqlite3-shm` | SQLite sidecar files can contain private message data. |

## AI Output Rules

Default output should be metadata-first:

- current library judgment
- target conversation
- `talker`
- time window
- retry count
- message count
- latest-batch self-check result

Message text should be minimized:

- Prefer summaries over full transcripts.
- Use short excerpts only when the user asks for evidence.
- Do not quote unrelated private messages.
- Do not persist raw message batches in this repository.

## Downstream Project Boundary

Downstream private projects may request message excerpts through `.agents`
skills. They must not copy WeFlow databases, exports or media into their own Git
repositories.

With explicit user source authorization, `PersonalOS` may retain an immutable,
account-scoped source package in its private late-bound runtime. That package
may contain a completed source-native export, database/WAL/SHM recovery
snapshot, media payloads or references, hashes, coverage, lineage and
checkpoints. It is recovery and evidence material, not a second writable WeFlow
database or a new public archive product. WeFlow/WeLive owns source data,
decryption and export implementation; WeFlowBridge owns the version-bound
adaptation, handoff and verification contracts; PersonalOS owns the authorized
private package and its replaceable derived representations.

This permission never moves secrets or raw payloads into this public repository,
never authorizes source write-back, and never lets an empty or partial export
advance a completeness checkpoint.

`CareerCapital`, `SocialCapital`, and `LifeCases` may reference WeFlow evidence for specific decisions, but each project owns only its domain-specific interpretation.

## Public Commit Checklist

Before committing this repository:

1. Run `git diff --check`.
2. Check changed files for token-looking values, `WEFLOW_TOKEN`, `access_token=`, private keys, and real `.env` content.
3. Confirm changed files do not include raw messages, screenshots, database files, exports, or media.
4. Keep summaries public-safe and avoid private names unless they are already intentionally documented placeholders.
