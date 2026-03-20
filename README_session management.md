# OpenClaw Session Management

## What is a Session?

A session is a continuous conversation transcript between an agent and a user/channel. It's stored as a JSONL file on disk. Sessions persist across messages — a new message does NOT create a new session. The same session keeps accumulating messages until it's explicitly reset or auto-reset.

## Key Concepts: Session Key vs Session ID

| Term | What it is | Lifetime | Example |
|------|-----------|----------|---------|
| **Session Key** | Routing address — identifies WHO is talking WHERE | Permanent (never changes for a given route) | `agent:manager:discord:channel:1481682092541607936` |
| **Session ID** | UUID for the transcript file on disk | Changes on every reset | `6b09092c-20d5-4364-b901-52ab48fd1414` |

The session key is the stable address. The session ID is the current transcript. When a session resets, the key stays the same but gets a new session ID (new JSONL file).

## Storage Layout

```
~/.openclaw/agents/{agentId}/sessions/
├── sessions.json                          ← maps session keys → SessionEntry objects
├── {sessionId}.jsonl                      ← active transcript (append-only)
├── {sessionId}.jsonl.reset.{timestamp}    ← archived transcript (daily/manual reset)
└── {sessionId}.jsonl.deleted.{timestamp}  ← deleted transcript
```

**File:** `src/config/sessions/store.ts`

Each `SessionEntry` in `sessions.json` contains:

```typescript
type SessionEntry = {
  sessionId: string;          // UUID
  sessionFile: string;        // path to JSONL transcript
  updatedAt: number;          // last activity timestamp (unix ms)
  compactionCount: number;    // how many times compacted
  systemSent: boolean;        // whether system message was sent
  thinkingLevel?: string;     // user-set thinking preference
  verboseLevel?: string;      // user-set verbose preference
  modelOverride?: string;     // user-set model override
  // ... more metadata
};
```

## Session Key Construction

**File:** `src/routing/session-key.ts`

Session keys are built from the agent ID + context (channel, chat type, peer):

```typescript
// Main session (CLI/web)
export function buildAgentMainSessionKey(params) {
  return `agent:${agentId}:${mainKey}`;  // e.g. "agent:main:main"
}

// Per-peer session (DM, group, thread)
export function buildAgentPeerSessionKey(params) {
  // DM scope determines granularity:
  // "main"                    → agent:main:main (all DMs share one session)
  // "per-peer"                → agent:main:direct:username
  // "per-channel-peer"        → agent:main:telegram:direct:username
  // "per-account-channel-peer"→ agent:main:telegram:manager:direct:username

  // Groups/channels:
  // agent:main:discord:channel:1481682092541607936

  // Threads:
  // agent:main:discord:thread:9876543210
}
```

**Session key patterns:**

| Pattern | Scope |
|---------|-------|
| `agent:{id}:main` | Main interactive session |
| `agent:{id}:{channel}:direct:{peerId}` | DM per sender |
| `agent:{id}:{channel}:channel:{channelId}` | Group channel |
| `agent:{id}:{channel}:thread:{threadId}` | Thread/topic |
| `agent:{id}:cron:{cronJobUUID}` | Cron job (one per job) |
| `subagent:{parentKey}:{childId}` | Subagent session |

## When Does a New Session Start?

There are exactly **three** triggers for a new session. All of them are checked inside `initSessionState()`:

**File:** `src/auto-reply/reply/session.ts:169–375`

### Trigger 1: Explicit `/new` or `/reset` command

```typescript
// src/auto-reply/reply/session.ts:262–295
for (const trigger of resetTriggers) {
  const triggerLower = trigger.toLowerCase();
  if (trimmedBodyLower === triggerLower || strippedForResetLower === triggerLower) {
    isNewSession = true;
    bodyStripped = "";
    resetTriggered = true;
    break;
  }
}
```

Default reset triggers: `["/new", "/reset"]`

### Trigger 2: Session staleness (daily or idle auto-reset)

**File:** `src/config/sessions/reset.ts:139–159`

```typescript
export function evaluateSessionFreshness(params: {
  updatedAt: number;
  now: number;
  policy: SessionResetPolicy;
}): SessionFreshness {
  const dailyResetAt =
    params.policy.mode === "daily"
      ? resolveDailyResetAtMs(params.now, params.policy.atHour)
      : undefined;
  const idleExpiresAt =
    params.policy.idleMinutes != null
      ? params.updatedAt + params.policy.idleMinutes * 60_000
      : undefined;
  const staleDaily = dailyResetAt != null && params.updatedAt < dailyResetAt;
  const staleIdle = idleExpiresAt != null && params.now > idleExpiresAt;
  return {
    fresh: !(staleDaily || staleIdle),
    dailyResetAt,
    idleExpiresAt,
  };
}
```

Two modes:

| Mode | Default | How it works |
|------|---------|-------------|
| `daily` | **Yes** (default) | Resets at configured hour. Default: **4 AM local time**. Checks: was `session.updatedAt` before today's 4 AM? |
| `idle` | No | Resets after N minutes of inactivity. Default idle: 120 minutes. |

**Defaults:**

```typescript
// src/config/sessions/reset.ts:20-21
export const DEFAULT_RESET_MODE: SessionResetMode = "daily";
export const DEFAULT_RESET_AT_HOUR = 4;
```

**CRITICAL: The daily reset is NOT a background timer.** It's a freshness check that runs when a new message arrives. If nobody sends a message to the agent, the reset never fires. The session sits stale until the next message triggers the check.

This is why you might see gaps in daily resets — if no one talked to the agent on Mar 16, 17, 18, those days have no reset. The next message (e.g., on Mar 20) triggers the check, finds the session stale, and resets it then.

```typescript
// src/auto-reply/reply/session.ts:333–340
const freshEntry = entry
  ? evaluateSessionFreshness({ updatedAt: entry.updatedAt, now, policy: resetPolicy }).fresh
  : false;
// If not fresh → isNewSession = true
```

**Per-type configuration** (can set different policies for DMs, groups, threads):

```typescript
// src/config/sessions/reset.ts:84–120
// Config example in openclaw.json:
// {
//   "session": {
//     "resetByType": {
//       "direct": { "mode": "idle", "idleMinutes": 120 },
//       "group":  { "mode": "daily", "atHour": 4 },
//       "thread": { "mode": "idle", "idleMinutes": 60 }
//     }
//   }
// }
export function resolveSessionResetPolicy(params) {
  const mode =
    typeReset?.mode ??
    baseReset?.mode ??
    (!hasExplicitReset && legacyIdleMinutes != null ? "idle" : DEFAULT_RESET_MODE);
  const atHour = normalizeResetAtHour(
    typeReset?.atHour ?? baseReset?.atHour ?? DEFAULT_RESET_AT_HOUR,
  );
  return { mode, atHour, idleMinutes };
}
```

### Trigger 3: First message ever (no existing session entry)

If no `SessionEntry` exists for the session key, a new one is created with `crypto.randomUUID()`.

## What Happens on Reset

**File:** `src/auto-reply/reply/session.ts:357–374`

```typescript
// New session ID generated
sessionId = crypto.randomUUID();
isNewSession = true;
systemSent = false;
abortedLastRun = false;

// User preferences ARE preserved across resets:
if (resetTriggered && entry) {
  persistedThinking = entry.thinkingLevel;
  persistedVerbose = entry.verboseLevel;
  persistedReasoning = entry.reasoningLevel;
  persistedTtsAuto = entry.ttsAuto;
  persistedModelOverride = entry.modelOverride;
  persistedProviderOverride = entry.providerOverride;
  persistedLabel = entry.label;
}
```

**Transcript archiving:**

**File:** `src/gateway/session-utils.fs.ts:177–228`

```typescript
// Old transcript is renamed (not deleted):
export function archiveFileOnDisk(filePath: string, reason: ArchiveFileReason): string {
  const ts = formatSessionArchiveTimestamp();
  const archived = `${filePath}.${reason}.${ts}`;
  fs.renameSync(filePath, archived);  // e.g. foo.jsonl → foo.jsonl.reset.2026-03-15T09-07-58.410Z
  return archived;
}
```

Archive reasons:
- `.reset.{timestamp}` — session was reset (daily auto-reset or `/new`)
- `.deleted.{timestamp}` — session was explicitly deleted

**Hooks fired on reset:**
- `session_end` (plugin hook) — for the old session
- `session_start` (plugin hook) — for the new session
- `before_reset` (plugin hook) — before the reset happens

## Session Compaction (Long Sessions)

When a session gets too long, it does NOT start a new session. Instead it **compacts** — summarizes older messages to free token space while keeping the same session.

**File:** `src/agents/pi-embedded-runner/compact.ts`

**When compaction triggers:**
- **Overflow:** During an LLM call, context exceeds token budget
- **Manual:** User runs `/compact` command

**What happens during compaction:**
1. Reads the JSONL transcript file
2. Feeds older messages to the LLM for summarization
3. Replaces old messages with a shorter summary turn
4. Rewrites the JSONL file with fewer messages
5. Increments `sessionEntry.compactionCount`
6. Same session ID — same transcript file (just shorter)

**Compaction is NOT a reset:** The session continues with the same ID. Only the message history is compressed.

**Hooks fired:**
- `before_compaction` (plugin hook) — includes `sessionFile` path so plugins can read the full transcript async
- `after_compaction` (plugin hook)
- `session:compact:before` / `session:compact:after` (internal hooks)

## Heartbeat Sessions

**Heartbeats use the SAME session as normal messages.** They don't create their own session.

**File:** `src/infra/heartbeat-runner.ts:167–246`

The heartbeat run reads/writes to the same JSONL transcript that regular messages use. This means:
- Heartbeat messages appear in the same conversation history
- The agent sees previous heartbeat results when processing new messages
- Session compaction applies to heartbeat messages too

## Cron Sessions

Unlike heartbeats, cron jobs get their **own dedicated session key**:

```
agent:main:cron:{cronJobUUID}
```

Each cron job creates a separate JSONL transcript. This is why you see many session files for the "main" agent — most are from individual cron runs, not from conversations.

## Session Type Summary

| Type | Session Key | Shares History? | Auto-Reset? |
|------|------------|----------------|-------------|
| Main (CLI/web) | `agent:{id}:main` | Yes (one continuous thread) | Daily at 4 AM |
| DM | `agent:{id}:{channel}:direct:{peer}` | Yes per sender | Daily at 4 AM |
| Group channel | `agent:{id}:{channel}:channel:{channelId}` | Yes per channel | Daily at 4 AM |
| Thread | `agent:{id}:{channel}:thread:{threadId}` | Yes per thread | Configurable |
| Heartbeat | Same as the session it targets | Yes (shared with normal messages) | Same policy as parent |
| Cron | `agent:{id}:cron:{jobUUID}` | No (isolated per job) | No auto-reset |
| Subagent | `subagent:{parentKey}:{childId}` | No (isolated) | No auto-reset |

## Configuration Reference

```jsonc
// openclaw.json
{
  "session": {
    // Session scope for DMs
    "scope": "per-sender",  // "per-sender" | "per-channel-peer" | "per-account-channel-peer"

    // Global reset policy
    "reset": {
      "mode": "daily",     // "daily" | "idle"
      "atHour": 4           // 0-23, local time (daily mode)
      // "idleMinutes": 120  // (idle mode)
    },

    // Per-type overrides
    "resetByType": {
      "direct": { "mode": "daily", "atHour": 4 },
      "group":  { "mode": "daily", "atHour": 4 },
      "thread": { "mode": "idle", "idleMinutes": 60 }
    },

    // Per-channel overrides
    "resetByChannel": {
      "discord": { "mode": "daily", "atHour": 6 },
      "telegram": { "mode": "idle", "idleMinutes": 180 }
    }
  }
}
```
