# AI Consumer Contract v2

This document defines how AI consumers should use `E:\Projects\Tools\WeFlowBridge` as a WeChat data source adapter.

Contract v2 is verified against WeFlow `26.7.3` / `26.7.3.0` on 2026-07-09. It keeps the older defensive `/api/v1/messages` rules, but adds the 7.3 API shapes that are better for AI integration: JSON-body `POST` calls, ChatLab Pull, incremental `sync` metadata, quote metadata, and explicit media manifests.

Machine-readable companions:

- HTTP API surface: [docs/openapi.yaml](openapi.yaml)
- Envelope schema: [schemas/ai-consumer-envelope.v2.schema.json](../schemas/ai-consumer-envelope.v2.schema.json)

## Project Role

`E:\Projects\Tools\WeFlowBridge` is the provider-facing adapter for local WeFlow data access. It owns public-safe endpoint notes, health checks, watchdog scripts, and the contract for AI consumers.

It does not own relationship analysis, career analysis, PersonalOS memory, raw message archives, or long-term semantic indexes. Those belong to downstream projects that call this adapter through approved skills.

## Consumer Layers

| Consumer | Allowed role | Not allowed |
| --- | --- | --- |
| `.agents` / `weflow-toolkit v0.2+` | Call the local API, judge active library, normalize metadata, enforce privacy rules | Store raw chat history as durable project data |
| `PersonalOS` | Register WeChat history and, after explicit source authorization, retain a version-bound immutable source package in its private late-bound runtime | Put private payloads in Git, maintain a second writable WeFlow state, write back to WeChat, or make ordinary queries depend on WeFlow being online |
| `CareerCapital` | Query work-related conversations when a task needs evidence | Own family, romance, or unrelated social facts |
| `SocialCapital` | Query relationship, family, romance, and friend context when needed | Own career negotiation or salary facts |
| `LifeCases` | Pull excerpts as evidence for a specific cross-domain case | Become a permanent WeChat archive |

## Required Output Envelope

Any AI consumer that reads WeFlow messages must report or internally preserve these fields:

| Field | Meaning |
| --- | --- |
| `current_library` | Active WeFlow account database judgment: `root`, `亦泊`, or `unknown` |
| `library_evidence` | One or two evidence strings used to judge the active library |
| `target_account` | Account requested by the user, if any |
| `target_conversation` | Human-readable target group or contact name |
| `talker` | WeFlow conversation ID used for API calls; redact raw `wxid_...` and `...@chatroom` in public/user-facing output by default |
| `time_window` | `latest`, or explicit `since/end/offset` pagination window for historical ChatLab Pull reads |
| `retry_count` | Number of retries after empty or suspicious responses |
| `message_count` | Number of messages returned in the final batch |
| `lastTimestamp_matches_newest` | Whether `sessions.lastTimestamp` equals `messages[0].createTime` for latest reads |
| `content_scope` | Whether output contains metadata only, excerpts, or full text |
| `request_method` | `GET` or `POST`; prefer `POST` when parameters are complex or contain many filters |
| `endpoint_family` | `sessions`, `messages`, `chatlab_pull`, `group_members`, or `sns`; `push` is documented but not an AI envelope endpoint |
| `sync_watermark` | `sync.watermark` from ChatLab Pull, when present |
| `media_manifest` | Non-path metadata-only list of media fields or exported file counts; do not store media payloads or raw media paths in this repository |

## Retrieval Rules

Latest messages:

1. Use `GET /api/v1/messages?talker=<talker>&limit=100`.
2. Do not pass `start/end`.
3. Treat returned messages as `createTime` descending; newest is index `0`.
4. Compare `sessions.lastTimestamp` with `messages[0].createTime`.
5. If they do not match, say the latest batch may be incomplete and retry or change parameters.

Historical reads:

1. Prefer ChatLab Pull: `GET /api/v1/sessions/{id}/messages?since=<unix_seconds>&end=<unix_seconds>&limit=<n>&offset=<n>`.
2. Preserve the returned `sync` block, especially `sync.hasMore`, `sync.nextSince`, `sync.nextOffset`, and `sync.watermark`.
3. Use bounded windows that fit the user request.
4. Fall back to `/api/v1/messages?talker=<talker>&start=<YYYYMMDD>&end=<YYYYMMDD>` only when the consumer needs legacy JSON, keyword filtering, or media export options.
5. Do not infer "no messages" from a single empty response; retry first.

ChatLab Pull:

1. Use `GET /api/v1/sessions?format=chatlab` to list AI-friendly remote data-source candidates.
2. Use `/api/v1/sessions/{id}/messages` for bulk or incremental transcript reads.
3. Treat `messages[].platformMessageId` as the stable message identity inside a pull.
4. Preserve `messages[].replyToMessageId` when present so reply chains can be reconstructed.
5. Preserve `quote` as quoted-message metadata. Do not promote quoted private text into public docs.
6. Record `endpoint_family=chatlab_pull` and `request_method=GET`.

JSON messages:

1. `GET /api/v1/messages` and `POST /api/v1/messages` are both valid in WeFlow 26.7.3.
2. Prefer `POST` with `Content-Type: application/json` for complex parameter sets.
3. When media is requested, keep only a non-path `media_manifest` in durable AI outputs: media type, counts, redacted sender role, timestamp, and size if available. Do not store media payloads or raw media paths here.
4. Preserve `replyToMessageId` and `quote` for reply-aware summarization.

Time handling:

1. Treat Unix timestamps as UTC epoch seconds.
2. Convert Chinese-context output to Beijing time with `UTC+8`.
3. Do not use system local timezone as truth.

## Account Judgment

Before reading a target conversation, consumers must judge the active WeFlow database:

1. `GET /api/v1/sessions?limit=80`
2. `GET /api/v1/contacts?keyword=root&limit=20`
3. `GET /api/v1/contacts?keyword=亦泊&limit=20`
4. If the target is a group, also query `GET /api/v1/sessions?keyword=<keyword>&limit=10000`

If the requested account and active library do not match, do not present current-library results as if they came from the requested account.

## Failure Semantics

- Missing target conversation means "not found in the current WeFlow library", not "the conversation does not exist".
- Empty message results mean "empty or unstable response after N retries", not "no messages", unless the active library and time window are verified.
- A forwarded XML source is not proof that the target group is readable in the active library.
- A successful metadata probe is not consent to publish raw messages.
- A successful ChatLab Pull probe is not consent to create a long-term transcript archive.
- A populated `media_manifest` is not consent to publish images, voice, video, emoji, or local media paths.

## Stable Integration Decision

Do not create a separate E-drive project just to manage WeFlow access. The current ownership is:

- `E:\Projects\Tools\WeFlowBridge`: adapter, watchdog, public-safe docs, consumer contract.
- `E:\.agents\plugins\weflow-toolkit` (`weflow-toolkit v0.2+`): AI calling skill and helper scripts.
- Downstream projects: task-specific analysis and decisions.

### Private immutable snapshot handoff

The public repository still stores no raw WeChat data. That repository boundary
does not prohibit an explicitly authorized private consumer from preserving the
source evidence it needs for recovery and offline processing.

For PersonalOS, the supported handoff is:

1. bind one account identity, database/media locator, key reference and
   checkpoint namespace per source instance;
2. acquire through a version-bound WeFlow/WeLive interface into an immutable,
   private, non-repository destination;
3. retain the completed source-native export, required database/WAL/SHM recovery
   snapshot, media payloads or references, hashes, coverage, lineage and gap
   receipts;
4. accept the package only after the export reports complete, all declared
   outputs exist, counts reconcile and recorded hashes read back;
5. keep active WeFlow/WeChat state read-only: no write-back and no second writable database;
6. perform ordinary PersonalOS queries from its own verified package and
   replaceable derived representations, not from a live WeFlow dependency.

Two accounts are two independent source instances and runs. An active-library
probe, a single API response or one account's keys never proves the other
account complete. Empty, partial, version-mismatched or hash-mismatched output
fails closed and does not advance a checkpoint.

Secrets are supplied only through a private configuration or local secret
binding. They must not appear in command-line arguments, stdout/stderr, receipts
or Git. WeFlow/WeLive owns source data, decryption and export implementation;
WeFlowBridge owns only the version-bound adaptation, handoff and verification
contracts; PersonalOS owns its authorized private immutable evidence package,
coverage and derived representations. This does not authorize a new archive
product, vector store, relationship database or duplicate semantic owner.

`tools/build_private_snapshot_manifest.py` is the narrow verification entry for
an already acquired, account-scoped private snapshot. It enumerates files and
hashes raw bytes without parsing message or media content, then performs a full
second-pass SHA-256 readback before publishing a receipt. Its output must stay in
a private non-repository destination. The tool refuses a destination that
resolves to this repository root or any descendant. Use an external private
directory named `private-snapshot-...`; the repository's exact root-level
ignore rule is only a defense-in-depth fallback and never authorizes local
storage. The receipt proves the referenced byte set; it does not decrypt data,
perform the source-native export, or make a mutable source directory immutable.
