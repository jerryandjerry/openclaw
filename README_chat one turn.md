# OpenClaw: What Happens When You Send One Message

This document traces the complete code path from a user typing a message in Telegram to the LLM API call and response — every file, every function, every data structure involved.

---

## Overview — Precise 18-Step Process

Every step below maps directly to the code execution order in `runEmbeddedAttempt()` (attempt.ts).
Steps 1–4 happen in the channel layer before `attempt.ts` is called.
Steps 5–18 happen inside `runEmbeddedAttempt()`.

```
User types "hello" in Telegram group
        │
        ▼
┌──────────────────────────┐
│ 1. Telegram Webhook       │  src/telegram/webhook.ts
│    receives POST          │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 2. Bot Handler            │  src/telegram/bot-handlers.ts
│    debounce + filter      │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 3. Resolve Route          │  src/routing/resolve-route.ts
│    7-tier binding →       │  src/routing/session-key.ts
│    agentId + sessionKey   │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 4. Load/Create Session    │  src/config/sessions/store.ts
│    Index Entry            │  sessions.json + {id}.jsonl path
└────────┬─────────────────┘
         ▼
═══════════════════════════════════════════════════
  attempt.ts: runEmbeddedAttempt() begins here
═══════════════════════════════════════════════════
         ▼
┌──────────────────────────┐
│ 5. Resolve Skills         │  attempt.ts:249–267
│    loadWorkspaceSkillEntries()  → SkillEntry[]
│    resolveSkillsPromptForRun()  → XML string
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 6. Load Bootstrap Files   │  attempt.ts:270–277
│    resolveBootstrapContextForRun()
│    → WorkspaceBootstrapFile[] + ContextFile[]
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 7. Create Tool Defs       │  attempt.ts:288–327
│    createOpenClawCodingTools()
│    → Tool[] (read, edit, exec, message, etc.)
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 8. Build System Prompt    │  attempt.ts:434–485
│    buildEmbeddedSystemPrompt()  → string
│    createSystemPromptOverride() → string
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 9. Acquire Session Lock   │  attempt.ts:487–492
│    acquireSessionWriteLock()
│    → file-level lock on .jsonl
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 10. Open SessionManager   │  attempt.ts:498–528
│     repairSessionFileIfNeeded()
│     prewarmSessionFile()
│     SessionManager.open()  → SessionManager
│     prepareSessionManagerForRun()
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 11. ★ CREATE SESSION OBJ  │  attempt.ts:575–586
│     createAgentSession({  │
│       model, tools,       │  → { session } object
│       sessionManager,     │  session.agent = Agent
│       settingsManager     │  session.messages = []
│     })                    │  session.prompt = fn
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 12. Set System Prompt     │  attempt.ts:587
│     applySystemPromptOverrideToSession()
│     → session.agent.setSystemPrompt(text)
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 13. Set + Wrap StreamFn   │  attempt.ts:625–658
│     a) ollama → createOllamaStreamFn()
│        else  → streamSimple
│     b) applyExtraParamsToAgent()
│        (temperature, maxTokens, headers)
│     c) cacheTrace.wrapStreamFn()
│     d) anthropicPayloadLogger.wrapStreamFn()
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 14. Sanitize + Load       │  attempt.ts:662–691
│     Chat History          │
│     a) sanitizeSessionHistory()
│     b) validateGeminiTurns()
│     c) validateAnthropicTurns()
│     d) limitHistoryTurns()
│     e) sanitizeToolUseResultPairing()
│     f) agent.replaceMessages(limited)
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 15. Detect + Inject       │  attempt.ts:963–986
│     Images                │
│     detectAndLoadPromptImages()
│     injectHistoryImagesIntoMessages()
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 16. ★ FIRE API CALL       │  attempt.ts:1042–1045
│     activeSession.prompt()│
│     → streamFn chain      │
│       builds HTTP body    │
│       from (model,        │
│       context, options)   │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 17. Tool Call Loop        │  (internal to pi-agent-core)
│     LLM returns tool_use  │  → execute tool locally
│     → send tool_result    │  → re-call LLM
│     repeat until stop     │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 18. Save Results          │  attempt.ts (finally block)
│     .jsonl ← append msgs  │  src/config/sessions/store.ts
│     sessions.json ← update│  (tokens, timestamp, etc.)
└──────────────────────────┘
```

---

## Step 1: Telegram Webhook Receives the Message

**File:** `src/telegram/webhook.ts`

```typescript
export async function startTelegramWebhook(opts: {
  token: string;
  accountId?: string;
  config?: OpenClawConfig;
  path?: string;   // "/telegram-webhook"
  port?: number;   // 8787
}) {
  const bot = createTelegramBot({ token: opts.token, ... });
  const handler = webhookCallback(bot, "http", {
    secretToken: secret,
    onTimeout: "return",
    timeoutMilliseconds: 10_000,
  });

  const server = createServer((req, res) => {
    if (req.url === "/telegram-webhook" && req.method === "POST") {
      handler(req, res);
    }
  });
}
```

Telegram sends a POST request with the update JSON to your server. The `webhookCallback` from the grammY library parses it and dispatches to registered handlers.

---

## Step 2: Bot Handler — Debounce and Filter

**File:** `src/telegram/bot-handlers.ts`

```typescript
export const registerTelegramHandlers = ({
  cfg, accountId, bot, processMessage, ...
}) => {
  // Debounce rapid messages (combines split messages into one)
  const inboundDebouncer = createInboundDebouncer<TelegramDebounceEntry>({
    debounceMs: resolveInboundDebounceMs({ cfg, channel: "telegram" }),
    buildKey: (entry) => entry.debounceKey,
    shouldDebounce: (entry) => {
      if (entry.allMedia.length > 0) return false;
      const text = entry.msg.text ?? entry.msg.caption ?? "";
      if (!text.trim()) return false;
      return !hasControlCommand(text, cfg, { botUsername: entry.botUsername });
    },
    onFlush: async (entries) => {
      const combinedText = entries.map(e => e.msg.text ?? "").join("\n");
      await processMessage(ctx, allMedia, storeAllowFrom);
    },
  });
};
```

### requireMention Filter

If `requireMention: true` is set in the Telegram config, the handler checks whether the message @mentions the bot. If not, the message is **dropped here** — no API call is made.

```typescript
// In bot-handlers.ts — simplified logic
if (requireMention && !mentionsBot(msg, botUsername)) {
  return; // silently ignore
}
```

This is the key to running multiple bots in one group without wasting API calls.

---

## Step 3: Resolve Route — Which Agent Handles This?

**File:** `src/routing/resolve-route.ts`

```typescript
export function resolveAgentRoute(input: ResolveAgentRouteInput): ResolvedAgentRoute {
  const bindings = getEvaluatedBindingsForChannelAccount(input.cfg, channel, accountId);

  // 7-tier priority matching:
  // Tier 1: binding.peer         — exact peer (group/user) match
  // Tier 2: binding.peer.parent  — thread parent match
  // Tier 3: binding.guild+roles  — guild + member roles
  // Tier 4: binding.guild        — guild-only match
  // Tier 5: binding.team         — Microsoft Teams match
  // Tier 6: binding.account      — account-wide match
  // Tier 7: binding.channel      — channel-wide match
  // Default: DEFAULT_AGENT_ID ("main")

  return { agentId, channel, accountId, sessionKey, mainSessionKey, matchedBy };
}
```

### Session Key Construction

**File:** `src/routing/session-key.ts`

```typescript
// Constants
const DEFAULT_AGENT_ID = "main";
const DEFAULT_MAIN_KEY = "main";

// For direct messages (DM):
export function buildAgentMainSessionKey(params: {
  agentId: string;
  mainKey?: string;
}): string {
  return `agent:${agentId}:${mainKey}`;
  // → "agent:main:main" (default agent, default key)
  // → "agent:jenny-manager:main" (specific agent)
}

// For group messages:
export function buildAgentPeerSessionKey(params: {
  agentId: string;
  channel: string;
  peerKind: string;
  peerId: string;
}): string {
  return `agent:${agentId}:${channel}:${peerKind}:${peerId}`;
  // → "agent:jenny-manager:telegram:group:-5102648542"
}
```

### DM Scope — How Direct Messages Are Routed

When `dmScope` is `"main"` (the default), ALL direct messages from any channel share one session:

```
iMessage DM  → "agent:main:main"
Telegram DM  → "agent:main:main"   ← same session!
Discord DM   → "agent:main:main"   ← same session!
```

When `dmScope` is `"channel"`, each channel gets its own DM session:

```
iMessage DM  → "agent:main:imessage:direct:+1234567890"
Telegram DM  → "agent:main:telegram:direct:98765432"
```

Group messages ALWAYS get separate sessions regardless of dmScope.

---

## Step 4: Load or Create Session

**File:** `src/config/sessions/store.ts`

```typescript
// Load the session index
const storePath = resolveStorePath(cfg.session?.store, { agentId });
// → ~/.openclaw/agents/jenny-manager/sessions/sessions.json
const store = loadSessionStore(storePath);

// Look up existing session
const entry = store[sessionKey];
// sessionKey = "agent:jenny-manager:telegram:group:-5102648542"

if (entry) {
  // Reuse existing session
  sessionId = entry.sessionId;         // "20e6c372-..."
  sessionFile = entry.sessionFile;     // ".../{sessionId}.jsonl"
} else {
  // Create new session
  sessionId = crypto.randomUUID();
  sessionFile = path.join(sessionsDir, `${sessionId}.jsonl`);
}
```

### sessions.json Structure

```json
{
  "agent:jenny-manager:telegram:group:-5102648542": {
    "sessionId": "20e6c372-1940-4944-9e35-7ce826b39db6",
    "sessionFile": "~/.openclaw/agents/jenny-manager/sessions/20e6c372-....jsonl",
    "updatedAt": 1772024840177,
    "systemSent": true,
    "channel": "telegram",
    "chatType": "group",
    "lastChannel": "telegram",
    "lastTo": "telegram:group:-5102648542",
    "lastAccountId": "jenny-bot",
    "modelProvider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "contextTokens": 200000,
    "inputTokens": 28,
    "outputTokens": 180,
    "totalTokens": 27719,
    "deliveryContext": {
      "channel": "telegram",
      "to": "telegram:group:-5102648542",
      "accountId": "jenny-bot"
    },
    "skillsSnapshot": { "prompt": "...", "skills": [...], "resolvedSkills": [...] },
    "systemPromptReport": { ... }
  }
}
```

### Session Store Maintenance

- **Cache TTL:** 45 seconds (re-reads from disk after expiry)
- **Pruning:** entries older than 30 days are removed
- **Cap:** max 500 entries per agent
- **Rotation:** file rotated at 10MB
- **Writes:** atomic (write to temp file, then rename)

---

## Step 5: Resolve Skills (attempt.ts:249–267)

**Files:** `src/agents/skills/workspace.ts`, `src/agents/skills/frontmatter.ts`, `src/markdown/frontmatter.ts`, `src/agents/skills/bundled-dir.ts`

Skills are resolved **before** bootstrap files in the actual code order.

```typescript
// attempt.ts:249–251 — scan skill folders from disk
const skillEntries = shouldLoadSkillEntries
  ? loadWorkspaceSkillEntries(effectiveWorkspace)
  : [];

// attempt.ts:262–267 — build the <available_skills> XML string
const skillsPrompt = resolveSkillsPromptForRun({
  skillsSnapshot: params.skillsSnapshot,
  entries: shouldLoadSkillEntries ? skillEntries : undefined,
  config: params.config,
  workspaceDir: effectiveWorkspace,
});
```

This triggers a 13-step loading chain: scan 6 directories → read SKILL.md twice (once by external package for name/description, once by OpenClaw for metadata/gating) → merge by name with precedence → filter by gates → compact paths → cap at 150 skills / 30K chars → generate XML → store in `SkillSnapshot`.

**Full detailed trace with input/output/function/code for each step: see [Progressive Skill Loading](#progressive-skill-loading--how-it-actually-works) section.**

---

## Step 6: Load Workspace Bootstrap Files (attempt.ts:270–277)

**File:** `src/agents/workspace.ts`

```typescript
export async function loadWorkspaceBootstrapFiles(dir: string): Promise<WorkspaceBootstrapFile[]> {
  const resolvedDir = resolveUserPath(dir);

  // Files loaded in THIS exact order:
  const entries = [
    { name: "AGENTS.md",    filePath: path.join(resolvedDir, "AGENTS.md") },
    { name: "SOUL.md",      filePath: path.join(resolvedDir, "SOUL.md") },
    { name: "TOOLS.md",     filePath: path.join(resolvedDir, "TOOLS.md") },
    { name: "IDENTITY.md",  filePath: path.join(resolvedDir, "IDENTITY.md") },
    { name: "USER.md",      filePath: path.join(resolvedDir, "USER.md") },
    { name: "HEARTBEAT.md", filePath: path.join(resolvedDir, "HEARTBEAT.md") },
    { name: "BOOTSTRAP.md", filePath: path.join(resolvedDir, "BOOTSTRAP.md") },
  ];

  // Memory files appended last
  entries.push(...(await resolveMemoryBootstrapEntries(resolvedDir)));

  // Read each file from disk (cached by mtime)
  const result: WorkspaceBootstrapFile[] = [];
  for (const entry of entries) {
    try {
      const content = await readFileWithCache(entry.filePath);
      result.push({ name: entry.name, path: entry.filePath, content, missing: false });
    } catch {
      result.push({ name: entry.name, path: entry.filePath, missing: true });
    }
  }
  return result;
}
```

### File Caching

```typescript
async function readFileWithCache(filePath: string): Promise<string> {
  const stats = await fs.stat(filePath);
  const mtimeMs = stats.mtimeMs;
  const cached = workspaceFileCache.get(filePath);

  if (cached && cached.mtimeMs === mtimeMs) {
    return cached.content;  // cache hit — same mtime
  }

  const content = await fs.readFile(filePath, "utf-8");
  workspaceFileCache.set(filePath, { content, mtimeMs });
  return content;
}
```

### What Each File Does

| File | Purpose | Always Loaded? |
|------|---------|----------------|
| `AGENTS.md` | Agent roster, descriptions, bindings config | Yes |
| `SOUL.md` | Personality, behavior rules, tone, boundaries | Yes (main sessions) |
| `TOOLS.md` | Environment-specific notes (cameras, SSH hosts, TTS voices) | Yes |
| `IDENTITY.md` | Cosmetic: name, emoji, avatar, creature type | Yes (main sessions) |
| `USER.md` | Info about the human user (preferences, context) | Yes (main sessions) |
| `HEARTBEAT.md` | Cron/heartbeat task instructions | Yes (main sessions) |
| `BOOTSTRAP.md` | Custom bootstrap content (optional) | Yes (main sessions) |
| `MEMORY.md` | Agent's persistent memory across conversations | Yes (main sessions) |

### Subagent/Cron Filter

```typescript
const MINIMAL_BOOTSTRAP_ALLOWLIST = new Set(["AGENTS.md", "TOOLS.md"]);

export function filterBootstrapFilesForSession(files, sessionKey?) {
  if (!sessionKey || (!isSubagentSessionKey(sessionKey) && !isCronSessionKey(sessionKey))) {
    return files;  // main sessions get ALL files
  }
  return files.filter((file) => MINIMAL_BOOTSTRAP_ALLOWLIST.has(file.name));
  // subagents and cron only get AGENTS.md + TOOLS.md
}
```

### Truncation Limits

**File:** `src/agents/pi-embedded-helpers/bootstrap.ts`

```typescript
// Default limits
const maxChars = 20_000;      // per file
const totalMaxChars = 150_000; // all files combined

// When truncated: keep 70% from head + 20% from tail
const headRatio = 0.7;
const tailRatio = 0.2;
```

---

## Step 7: Create Tool Definitions (attempt.ts:288–327)

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

Tool definitions are created **before** the system prompt, because the system prompt references tool names.

```typescript
// attempt.ts:288–326
const toolsRaw = params.disableTools
  ? []
  : createOpenClawCodingTools({
      exec: { ...params.execOverrides, elevated: params.bashElevated },
      sandbox,
      messageProvider: params.messageChannel ?? params.messageProvider,
      agentAccountId: params.agentAccountId,
      messageTo: params.messageTo,
      sessionKey: params.sessionKey ?? params.sessionId,
      agentDir,
      workspaceDir: effectiveWorkspace,
      config: params.config,
      abortSignal: runAbortController.signal,
      modelProvider: params.model.provider,
      modelId: params.modelId,
      // ... 15+ more params
    });
// attempt.ts:327
const tools = sanitizeToolsForGoogle({ tools: toolsRaw, provider: params.provider });
```

### Output: Tool[] Array

Each tool is a `Tool` object with `name`, `description`, and `parameters` (JSON Schema):

```typescript
// Tool type (from @mariozechner/pi-ai)
interface Tool {
  name: string;           // "read", "edit", "exec", "message", etc.
  description: string;    // human-readable description
  parameters: object;     // JSON Schema for the tool's input
}
```

The complete tool list: `read`, `edit`, `write`, `exec`, `process`, `browser`, `canvas`, `nodes`, `message`, `tts`, `agents_list`, `sessions_list`, `sessions_history`, `sessions_send`, `sessions_spawn`, `subagents`, `session_status`, `web_search`, `web_fetch`, `memory_search`, `memory_get`.

---

## Step 8: Build System Prompt String (attempt.ts:434–485)

**Files:** `src/agents/pi-embedded-runner/run/attempt.ts`, `src/agents/system-prompt.ts`

```typescript
// attempt.ts:434–460 — assemble the full system prompt string
const appendPrompt = buildEmbeddedSystemPrompt({
  workspaceDir: effectiveWorkspace,
  contextFiles,         // bootstrap files from Step 6
  skillsPrompt,         // <available_skills> XML from Step 5
  tools,                // tool definitions from Step 7
  ownerNumbers: params.ownerNumbers,
  userTimezone,
  userTime,
  userTimeFormat,
  promptMode,           // "full" or "minimal" (for subagents/cron)
  runtimeInfo,
  modelAliasLines: buildModelAliasLines(params.config),
  // ... 10+ more params
});

// attempt.ts:484–485 — finalize into a callable override
const systemPromptOverride = createSystemPromptOverride(appendPrompt);
const systemPromptText = systemPromptOverride();  // → the final string
```

### System Prompt Structure (in order)

```
┌─────────────────────────────────────────────────┐
│ 1. Base Framework Instructions                   │
│    - Safety rules                                │
│    - Tool usage guidelines                       │
│    - Response formatting rules                   │
├─────────────────────────────────────────────────┤
│ 2. # Project Context                             │
│    "If SOUL.md is present, embody its persona"   │
│                                                  │
│    ## ~/.openclaw/workspace/AGENTS.md             │
│    <full file content>                           │
│                                                  │
│    ## ~/.openclaw/workspace/SOUL.md               │
│    <full file content>                           │
│                                                  │
│    ## ~/.openclaw/workspace/TOOLS.md              │
│    <full file content>                           │
│                                                  │
│    ## ~/.openclaw/workspace/IDENTITY.md           │
│    <full file content>                           │
│                                                  │
│    ## ~/.openclaw/workspace/USER.md               │
│    <full file content>                           │
│                                                  │
│    ## ~/.openclaw/workspace/HEARTBEAT.md          │
│    <full file content>                           │
│                                                  │
│    ## ~/.openclaw/workspace/MEMORY.md             │
│    <full file content>                           │
├─────────────────────────────────────────────────┤
│ 3. ## Skills (mandatory)                         │
│    "Before replying: scan <available_skills>"    │
│    "If exactly one skill applies: read its       │
│     SKILL.md with read tool, then follow it."    │
│                                                  │
│    <available_skills>                            │
│      <skill><name>weather</name>...</skill>      │
│      <skill><name>github</name>...</skill>       │
│      ...19 skills...                             │
│    </available_skills>                           │
├─────────────────────────────────────────────────┤
│ 4. Runtime Info                                  │
│    - Current date/time                           │
│    - User timezone                               │
│    - Model aliases                               │
│    - Sandbox mode                                │
│    - TTS hints                                   │
└─────────────────────────────────────────────────┘

Total: ~29,775 chars (from systemPromptReport in sessions.json)
  - Project context (bootstrap files): ~12,883 chars
  - Non-project (framework + skills + tools): ~16,892 chars
```

### Skills Section Code

```typescript
// src/agents/system-prompt.ts, lines 17-39
function buildSkillsSection(skillsPrompt: string, readToolName: string): string[] {
  return [
    "## Skills (mandatory)",
    "Before replying: scan <available_skills> <description> entries.",
    `- If exactly one skill clearly applies: read its SKILL.md at <location> with \`${readToolName}\`, then follow it.`,
    "- If multiple could apply: choose the most specific one, then read/follow it.",
    "- If none clearly apply: do not read any SKILL.md.",
    "Constraints: never read more than one skill up front; only read after selecting.",
    skillsPrompt,  // the <available_skills> XML
  ];
}
```

### Context Files Injection Code

```typescript
// src/agents/system-prompt.ts, lines 579-599
if (validContextFiles.length > 0) {
  lines.push("# Project Context", "");
  lines.push("The following project context files have been loaded:");
  if (hasSoulFile) {
    lines.push(
      "If SOUL.md is present, embody its persona and tone.",
    );
  }
  for (const file of validContextFiles) {
    lines.push(`## ${file.path}`, "", file.content, "");
  }
}
```

---

## Step 9: Acquire Session Write Lock (attempt.ts:487–492)

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

```typescript
// attempt.ts:487–492
const sessionLock = await acquireSessionWriteLock({
  sessionFile: params.sessionFile,
  maxHoldMs: resolveSessionLockMaxHoldFromTimeout({
    timeoutMs: params.timeoutMs,
  }),
});
```

This is a file-level lock that prevents concurrent writes to the same `.jsonl` session file. Only one `runEmbeddedAttempt()` call can hold the lock per session at a time.

---

## Step 10: Open SessionManager (attempt.ts:498–528)

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

```typescript
// attempt.ts:498–501 — repair corrupted .jsonl if needed
await repairSessionFileIfNeeded({
  sessionFile: params.sessionFile,
  warn: (message) => log.warn(message),
});

// attempt.ts:513 — pre-load .jsonl contents into memory
await prewarmSessionFile(params.sessionFile);
// → ~/.openclaw/agents/jenny-manager/sessions/{sessionId}.jsonl

// attempt.ts:514 — open SessionManager on the .jsonl file
sessionManager = guardSessionManager(SessionManager.open(params.sessionFile), {
  agentId: sessionAgentId,
  sessionKey: params.sessionKey,
  inputProvenance: params.inputProvenance,
  allowSyntheticToolResults: transcriptPolicy.allowSyntheticToolResults,
});

// attempt.ts:522–528 — prepare for this run
await prepareSessionManagerForRun({
  sessionManager,
  sessionFile: params.sessionFile,
  hadSessionFile,
  sessionId: params.sessionId,
  cwd: effectiveWorkspace,
});
```

**Output:** A `SessionManager` object that wraps the `.jsonl` file for reading/writing messages.

### .jsonl File Format

Each line is a JSON object:

```jsonl
{"type":"session","version":2,"id":"20e6c372-...","timestamp":1772024830000,"cwd":"/Users/home/.openclaw/workspace"}
{"type":"message","role":"user","content":"What's the weather?","timestamp":1772024831000}
{"type":"tool_use","name":"read","id":"toolu_01abc","input":{"path":"~/.openclaw/workspace/skills/weather-1/SKILL.md"}}
{"type":"tool_result","tool_use_id":"toolu_01abc","content":"# Weather Skill\n..."}
{"type":"message","role":"assistant","content":"Let me check the weather for you.","timestamp":1772024835000}
{"type":"tool_use","name":"exec","id":"toolu_02def","input":{"command":"curl wttr.in/Sydney?format=j1"}}
{"type":"tool_result","tool_use_id":"toolu_02def","content":"{\"current_condition\":[...]}"}
{"type":"message","role":"assistant","content":"It's currently 22°C and sunny in Sydney.","timestamp":1772024840000}
```

---

## Step 11: Create Session Object (attempt.ts:575–586) ★ KEY STEP

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

This is where the **session object** is created. It is the central object that holds the agent, messages, and the `prompt()` method.

```typescript
// attempt.ts:548–573 — split tools into SDK builtIn vs custom
const { builtInTools, customTools } = splitSdkTools({
  tools,
  sandboxEnabled: !!sandbox?.enabled,
});
const allCustomTools = [...customTools, ...clientToolDefs];

// attempt.ts:575–586 — ★ CREATE THE SESSION OBJECT
({ session } = await createAgentSession({
  cwd: resolvedWorkspace,
  agentDir,
  authStorage: params.authStorage,
  modelRegistry: params.modelRegistry,
  model: params.model,               // Model object (provider, id, contextWindow, etc.)
  thinkingLevel: mapThinkingLevel(params.thinkLevel),
  tools: builtInTools,                // Tool[] from Step 7
  customTools: allCustomTools,        // Tool[] (custom + client tools)
  sessionManager,                     // SessionManager from Step 10
  settingsManager,                    // SettingsManager (compaction settings)
}));
```

### What `createAgentSession()` returns:

```typescript
// From @mariozechner/pi-coding-agent (external package)
const session = {
  agent: {
    streamFn: StreamFn,                // the function that calls the LLM API
    setSystemPrompt(prompt: string): void,
    replaceMessages(msgs: AgentMessage[]): void,
  },
  messages: AgentMessage[],            // current conversation history (from .jsonl)
  sessionId: string,
  prompt(text: string, opts?): Promise<void>,  // fire LLM API call
  isCompacting: boolean,
  dispose(): void,
};
```

**Important:** At this point the session object exists but:
- System prompt is NOT yet set (default from pi-coding-agent)
- streamFn is the default (NOT yet wrapped with extra params)
- History is NOT yet sanitized

---

## Step 12: Set System Prompt on Session (attempt.ts:587)

**File:** `src/agents/pi-embedded-runner/system-prompt.ts`

```typescript
// attempt.ts:587
applySystemPromptOverrideToSession(session, systemPromptText);
```

### What `applySystemPromptOverrideToSession` does:

```typescript
// src/agents/pi-embedded-runner/system-prompt.ts:87-99
export function applySystemPromptOverrideToSession(
  session: AgentSession,
  override: string | ((defaultPrompt?: string) => string),
) {
  const prompt = typeof override === "function" ? override() : override.trim();

  // Set the system prompt on the agent
  session.agent.setSystemPrompt(prompt);

  // Also override internal fields so pi-coding-agent doesn't rebuild it
  const mutableSession = session as unknown as {
    _baseSystemPrompt?: string;
    _rebuildSystemPrompt?: (toolNames: string[]) => string;
  };
  mutableSession._baseSystemPrompt = prompt;
  mutableSession._rebuildSystemPrompt = () => prompt;
}
```

After this step, `session.agent` has the full system prompt string (built in Step 8).

---

## Step 13: Set and Wrap StreamFn (attempt.ts:625–658)

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`, `src/agents/pi-embedded-runner/extra-params.ts`

The `streamFn` is the function that actually makes the HTTP request to the LLM API. It gets set and then wrapped with multiple middleware layers:

```typescript
// attempt.ts:625–637 — SET BASE StreamFn
if (params.model.api === "ollama") {
  // Ollama: use native /api/chat endpoint
  activeSession.agent.streamFn = createOllamaStreamFn(ollamaBaseUrl);
} else {
  // All other providers: use pi-ai's streamSimple
  activeSession.agent.streamFn = streamSimple;
}

// attempt.ts:639–645 — WRAP with extra params (temperature, maxTokens, headers)
applyExtraParamsToAgent(
  activeSession.agent,
  params.config,
  params.provider,
  params.modelId,
  params.streamParams,
);
// This wraps streamFn with:
//   - temperature/maxTokens from config
//   - Anthropic beta headers (if anthropic provider)
//   - OpenRouter app attribution headers (if openrouter provider)
//   - Z.AI tool_stream (if zai provider)
//   - OpenAI Responses store=true (if openai-responses API)

// attempt.ts:647–654 — WRAP with cache trace logger (optional)
if (cacheTrace) {
  activeSession.agent.streamFn = cacheTrace.wrapStreamFn(activeSession.agent.streamFn);
}

// attempt.ts:655–658 — WRAP with Anthropic payload logger (optional)
if (anthropicPayloadLogger) {
  activeSession.agent.streamFn = anthropicPayloadLogger.wrapStreamFn(
    activeSession.agent.streamFn,
  );
}
```

### StreamFn Wrapping Chain (final call order, innermost first):

```
anthropicPayloadLogger.wrapStreamFn()    ← outermost (intercepts onPayload)
  └→ cacheTrace.wrapStreamFn()           ← logs context before API call
      └→ openAIResponsesStoreWrapper     ← forces store=true for OpenAI
          └→ openRouterHeadersWrapper     ← adds HTTP-Referer, X-Title
              └→ anthropicBetaWrapper     ← adds anthropic-beta header
                  └→ extraParamsWrapper   ← injects temperature, maxTokens
                      └→ streamSimple()   ← base: makes actual HTTP request
```

### StreamFn Signature

```typescript
type StreamFn = (
  model: Model,      // { id, provider, api, contextWindow, ... }
  context: Context,   // { systemPrompt, messages, tools }
  options?: StreamOptions,  // { temperature, maxTokens, headers, apiKey, signal, ... }
) => AsyncIterable<StreamEvent>;
```

---

## Step 14: Sanitize + Load Chat History (attempt.ts:662–691)

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

The session object was created with the raw `.jsonl` history from the SessionManager.
Now that history is sanitized and loaded into the session:

```typescript
// attempt.ts:662–671 — (a) sanitize raw messages
const prior = await sanitizeSessionHistory({
  messages: activeSession.messages,   // raw from .jsonl via SessionManager
  modelApi: params.model.api,         // "anthropic-messages" | "openai-chat" | etc.
  modelId: params.modelId,
  provider: params.provider,
  config: params.config,
  sessionManager,
  sessionId: params.sessionId,
  policy: transcriptPolicy,
});

// attempt.ts:673–675 — (b) validate Gemini turn order
const validatedGemini = transcriptPolicy.validateGeminiTurns
  ? validateGeminiTurns(prior)
  : prior;

// attempt.ts:676–678 — (c) validate Anthropic turn order (user/assistant alternation)
const validated = transcriptPolicy.validateAnthropicTurns
  ? validateAnthropicTurns(validatedGemini)
  : validatedGemini;

// attempt.ts:679–682 — (d) limit history turns (configurable max)
const truncated = limitHistoryTurns(
  validated,
  getDmHistoryLimitFromSessionKey(params.sessionKey, params.config),
);

// attempt.ts:686–688 — (e) repair orphaned tool_use/tool_result pairs
const limited = transcriptPolicy.repairToolUseResultPairing
  ? sanitizeToolUseResultPairing(truncated)
  : truncated;

// attempt.ts:690–692 — (f) ★ LOAD sanitized history into session object
if (limited.length > 0) {
  activeSession.agent.replaceMessages(limited);
}
```

After this step, `session.messages` contains the clean, validated, truncated conversation history.

---

## Step 15: Detect + Inject Images (attempt.ts:963–986)

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

For vision-capable models, images referenced in the prompt or history are loaded and injected:

```typescript
// attempt.ts:963–976 — detect images in prompt text (e.g., file paths to .png/.jpg)
const imageResult = await detectAndLoadPromptImages({
  prompt: effectivePrompt,
  workspaceDir: effectiveWorkspace,
  model: params.model,
  existingImages: params.images,
  historyMessages: activeSession.messages,
  maxBytes: MAX_IMAGE_BYTES,
  maxDimensionPx: resolveImageSanitizationLimits(params.config).maxDimensionPx,
});

// attempt.ts:980–987 — inject history images into their original positions
const didMutate = injectHistoryImagesIntoMessages(
  activeSession.messages,
  imageResult.historyImagesByIndex,
);
if (didMutate) {
  activeSession.agent.replaceMessages(activeSession.messages);
}
```

---

## Step 16: Fire API Call (attempt.ts:1042–1045) ★ KEY STEP

**File:** `src/agents/pi-embedded-runner/run/attempt.ts`

This is where the actual LLM API call happens:

```typescript
// attempt.ts:1042–1045
if (imageResult.images.length > 0) {
  await abortable(activeSession.prompt(effectivePrompt, { images: imageResult.images }));
} else {
  await abortable(activeSession.prompt(effectivePrompt));
}
```

### What `activeSession.prompt()` does internally:

1. Takes the user's prompt text and wraps it as a user message
2. Calls `session.agent.streamFn(model, context, options)` where:
   - `model` = the Model object from config (provider, id, contextWindow, etc.)
   - `context` = `{ systemPrompt: <from Step 12>, messages: <from Step 14>, tools: <from Step 7> }`
   - `options` = `{ temperature, maxTokens, headers, apiKey, signal, ... }`
3. The `streamFn` chain (from Step 13) processes the request through all wrappers
4. The innermost function (`streamSimple` or `createOllamaStreamFn`) builds the HTTP body and calls `fetch()`

### What the Final HTTP Body Looks Like (Anthropic example):

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 8192,
  "stream": true,
  "system": "<full system prompt from Step 8 — ~29,775 chars>",
  "messages": [
    { "role": "user", "content": "What's the weather in Sydney?" },
    { "role": "assistant", "content": [{ "type": "tool_use", "id": "toolu_01abc", "name": "read", "input": {...} }] },
    { "role": "user", "content": [{ "type": "tool_result", "tool_use_id": "toolu_01abc", "content": "..." }] },
    { "role": "assistant", "content": "It's 22°C and sunny in Sydney." },
    { "role": "user", "content": "hello" }
  ],
  "tools": [
    { "name": "read", "description": "...", "input_schema": {...} },
    { "name": "edit", "description": "...", "input_schema": {...} },
    ...20+ tools...
  ],
  "tool_choice": "auto"
}
```

### What the Final HTTP Body Looks Like (Ollama example):

```json
{
  "model": "qwen3:32b",
  "stream": true,
  "messages": [
    { "role": "system", "content": "<full system prompt>" },
    { "role": "user", "content": "What's the weather?" },
    { "role": "assistant", "content": "...", "tool_calls": [{ "function": { "name": "exec", "arguments": {...} } }] },
    { "role": "tool", "content": "...", "tool_name": "exec" },
    { "role": "assistant", "content": "It's 22°C and sunny." },
    { "role": "user", "content": "hello" }
  ],
  "tools": [
    { "type": "function", "function": { "name": "read", "description": "...", "parameters": {...} } },
    ...
  ],
  "options": { "num_ctx": 65536, "temperature": 0.1 }
}
```

---

## Step 17: Tool Call Loop

If the LLM responds with `tool_use` (or `tool_calls` for Ollama), the pi-agent-core framework automatically:

```
LLM returns:
  { "type": "tool_use", "name": "exec", "input": { "command": "curl wttr.in" } }
          │
          ▼
pi-agent-core executes the matching tool handler locally
          │
          ▼
Sends tool_result back to LLM (re-calls streamFn with updated messages):
  { "type": "tool_result", "content": "Weather: 22°C sunny" }
          │
          ▼
LLM returns final text:
  "It's currently 22°C and sunny!"
```

This loop continues until the LLM returns `stopReason: "stop"` (no tool calls). Each iteration goes through the full `streamFn` wrapping chain again.

---

## Step 18: Save Results

**File:** `src/agents/pi-embedded-runner/run/attempt.ts` (finally block), `src/config/sessions/store.ts`

### Append to .jsonl

All new messages (user prompt + assistant responses + tool uses + tool results) are appended to the `.jsonl` file by the SessionManager automatically during the `prompt()` call:

```jsonl
{"type":"message","role":"user","content":"hello","timestamp":1772024850000}
{"type":"message","role":"assistant","content":"Hi there! How can I help?","timestamp":1772024852000}
```

### Update sessions.json

```typescript
// src/config/sessions/store.ts
store[sessionKey] = {
  ...existingEntry,
  updatedAt: Date.now(),
  lastChannel: "telegram",
  lastTo: "telegram:group:-5102648542",
  lastAccountId: "jenny-bot",
  inputTokens: 5,
  outputTokens: 12,
  totalTokens: 27731,
  skillsSnapshot: { ... },  // current skills for change detection
  systemPromptReport: { ... },  // prompt size breakdown
};
saveSessionStore(storePath, store);  // atomic write (temp file → rename)
```

### Release Lock

The session write lock acquired in Step 9 is released in the `finally` block.

---

## All Files on Disk Involved in One Message

```
~/.openclaw/
├── config.yaml                                    ← [READ] agent config, bindings, telegram tokens
│
├── workspace/                                     ← [READ] bootstrap files → system prompt
│   ├── AGENTS.md                                  ← agent roster and descriptions
│   ├── SOUL.md                                    ← personality, behavior, tone
│   ├── TOOLS.md                                   ← environment notes (cameras, SSH, TTS)
│   ├── IDENTITY.md                                ← name, emoji, avatar
│   ├── USER.md                                    ← user preferences and context
│   ├── HEARTBEAT.md                               ← cron/heartbeat instructions
│   ├── BOOTSTRAP.md                               ← custom bootstrap (optional)
│   ├── MEMORY.md                                  ← persistent agent memory
│   └── skills/                                    ← [SCANNED] skill summaries → system prompt
│       ├── weather-1/SKILL.md
│       ├── find-skills/SKILL.md
│       └── tavily-search/SKILL.md
│
├── agents/
│   └── jenny-manager/
│       └── sessions/
│           ├── sessions.json                      ← [READ+WRITE] session index
│           └── 20e6c372-....jsonl                 ← [READ+APPEND] conversation history
│
└── (bundled skills from openclaw install)
    └── skills/                                    ← [SCANNED] bundled skill summaries
        ├── github/SKILL.md
        ├── coding-agent/SKILL.md
        └── .../SKILL.md
```

### Source Code Files (execution order)

| Step | File | Key Function |
|------|------|-------------|
| 1 | `src/telegram/webhook.ts` | `startTelegramWebhook()` |
| 2 | `src/telegram/bot-handlers.ts` | `registerTelegramHandlers()` |
| 3 | `src/routing/resolve-route.ts` | `resolveAgentRoute()` |
| 3 | `src/routing/session-key.ts` | `buildAgentPeerSessionKey()` |
| 4 | `src/config/sessions/store.ts` | `loadSessionStore()` |
| 5 | `src/agents/skills/workspace.ts` | `loadWorkspaceSkillEntries()`, `resolveSkillsPromptForRun()` |
| 6 | `src/agents/workspace.ts` | `loadWorkspaceBootstrapFiles()` |
| 6 | `src/agents/pi-embedded-helpers/bootstrap.ts` | `resolveBootstrapContextForRun()` |
| 7 | `src/agents/pi-embedded-runner/run/attempt.ts` | `createOpenClawCodingTools()` |
| 8 | `src/agents/system-prompt.ts` | `buildEmbeddedSystemPrompt()` |
| 8 | `src/agents/pi-embedded-runner/run/attempt.ts` | `createSystemPromptOverride()` |
| 9 | `src/agents/pi-embedded-runner/run/attempt.ts` | `acquireSessionWriteLock()` |
| 10 | `src/agents/pi-embedded-runner/run/attempt.ts` | `SessionManager.open()`, `prepareSessionManagerForRun()` |
| 11 | `@mariozechner/pi-coding-agent` | `createAgentSession()` → session object |
| 12 | `src/agents/pi-embedded-runner/system-prompt.ts` | `applySystemPromptOverrideToSession()` |
| 13 | `src/agents/pi-embedded-runner/extra-params.ts` | `applyExtraParamsToAgent()` |
| 13 | `src/agents/cache-trace.ts` | `cacheTrace.wrapStreamFn()` |
| 13 | `src/agents/anthropic-payload-log.ts` | `anthropicPayloadLogger.wrapStreamFn()` |
| 13 | `src/agents/ollama-stream.ts` | `createOllamaStreamFn()` (Ollama only) |
| 13 | `@mariozechner/pi-ai` | `streamSimple` (non-Ollama) |
| 14 | `src/agents/pi-embedded-runner/run/attempt.ts` | `sanitizeSessionHistory()`, `replaceMessages()` |
| 15 | `src/agents/pi-embedded-runner/run/attempt.ts` | `detectAndLoadPromptImages()` |
| 16 | `src/agents/pi-embedded-runner/run/attempt.ts` | `activeSession.prompt()` → fires API |
| 17 | `@mariozechner/pi-agent-core` | tool execution loop (internal) |
| 18 | `src/config/sessions/store.ts` | `saveSessionStore()` |

---

## Session Key Examples

| Scenario | Session Key | Shared? |
|----------|-------------|---------|
| DM to default agent (any channel) | `agent:main:main` | Yes — all channels share this |
| DM to jenny-manager (any channel) | `agent:jenny-manager:main` | Yes — all channels share this |
| Telegram group -510264 | `agent:jenny-manager:telegram:group:-5102648542` | No — unique per group |
| iMessage group 1 | `agent:main:imessage:group:1` | No — unique per group |
| Cron job (todo-reminder) | `agent:main:cron:0edbc111-...` | No — unique per cron |
| Cron sub-run | `agent:main:cron:6b2cba1d-...:run:da1f4acf-...` | No — unique per execution |
| Subagent spawned by jenny | `agent:jenny-manager:telegram:group:-510...:sub:0` | No — unique per spawn |

---
---

# OpenClaw: Complete Architecture Reference

Everything below covers the broader OpenClaw architecture beyond the single-message flow documented above.

---

## Project Overview

OpenClaw is a **TypeScript/Node.js** full-featured AI assistant platform. Key stats:

- **Language:** TypeScript (primary), with native apps in Swift/Kotlin
- **Runtime:** Node.js
- **Channels:** 13+ (Telegram, Discord, Slack, WhatsApp, iMessage, MS Teams, Signal, Matrix, Web, SMS/RCS, voice, ACP, CLI)
- **LLM Providers:** OpenAI, Anthropic, Google, Ollama, MiniMax, and more
- **Native Apps:** iOS, macOS, Android (not just a CLI)
- **Key Features:** Multi-agent, multi-channel, voice, browser automation, MCP/ACP integration, persistent memory, cron/heartbeat, canvas/nodes, progressive skill loading

---

## Workspace Files — What Each One Does

All workspace files live in `~/.openclaw/workspace/` (or per-agent workspace overrides). They are loaded as bootstrap context into the system prompt.

### SOUL.md — Personality and Behavior

Defines the agent's core personality, tone, boundaries, and behavioral rules.

```markdown
# Example SOUL.md
## Personality
- Warm, curious, slightly nerdy
- Uses humor but never sarcasm

## Boundaries
- Never share private information
- Always clarify before taking destructive actions

## Vibe
- Casual but competent
- Like talking to a smart friend

## Continuity
- Remember context from previous conversations
- Reference shared history naturally
```

**When to edit:** When you want to change how the agent behaves, what tone it uses, what rules it follows.

### IDENTITY.md — Cosmetic Identity

Purely cosmetic — name, emoji, avatar, creature type. Does NOT affect behavior.

```markdown
# Example IDENTITY.md
name: Claw
creature: raccoon
vibe: playful tinkerer
emoji: 🦝
avatar: /path/to/avatar.png
```

**When to edit:** When you want to change the agent's display name or avatar. Has no effect on behavior — that's SOUL.md's job.

### SOUL.md vs IDENTITY.md

| Aspect | SOUL.md | IDENTITY.md |
|--------|---------|-------------|
| Purpose | Behavior, personality, rules | Name, emoji, avatar |
| Affects responses? | Yes — tone, boundaries, style | No — cosmetic only |
| Example | "Never use sarcasm" | "name: Claw, emoji: 🦝" |
| Edit when | Changing how agent acts | Changing how agent looks |

### TOOLS.md — Environment-Specific Notes

Static notes about the local environment — NOT the same as skills or tool definitions.

```markdown
# Example TOOLS.md
## Cameras
- Front door: rtsp://192.168.1.100:554/stream1
- Backyard: rtsp://192.168.1.101:554/stream1

## SSH Hosts
- homelab: ssh pi@192.168.1.50
- vps: ssh root@203.0.113.10

## TTS Voices
- Default: alloy
- For stories: nova
```

**Always loaded** into the system prompt. Gives the agent knowledge about what's available in the environment.

### TOOLS.md vs Skills

| Aspect | TOOLS.md | Skills (SKILL.md) |
|--------|----------|-------------------|
| Loading | Always loaded (full content) | Progressive (summary only, read on demand) |
| Purpose | Environment notes | Reusable task instructions |
| Format | Free-form markdown | Structured with frontmatter |
| Location | `~/.openclaw/workspace/TOOLS.md` | `~/.openclaw/workspace/skills/*/SKILL.md` |
| Example | "Camera IPs, SSH hosts" | "How to capture camera frames" |

### AGENTS.md — Agent Roster

Defines all agents, their descriptions, and binding configurations.

### USER.md — User Information

Information about the human user — preferences, context, background.

### HEARTBEAT.md — Cron Instructions

Instructions for heartbeat/cron-triggered runs.

### BOOTSTRAP.md — Custom Bootstrap (Optional)

Any additional custom content to inject into the system prompt.

### MEMORY.md — Persistent Memory

Agent's persistent memory across conversations. Updated by the agent itself via the `memory_search`/`memory_get` tools.

### Loading Order and Limits

Files are loaded in this exact order (from `workspace.ts`):

```
1. AGENTS.md       ← agent roster
2. SOUL.md         ← personality/behavior
3. TOOLS.md        ← environment notes
4. IDENTITY.md     ← cosmetic identity
5. USER.md         ← user info
6. HEARTBEAT.md    ← cron instructions
7. BOOTSTRAP.md    ← custom content
8. MEMORY.md       ← persistent memory
```

**Limits:**
- Per-file max: **20,000 chars**
- Total max: **150,000 chars**
- Truncation strategy: **70% head + 20% tail** (10% gap)
- Subagent/cron sessions only get: **AGENTS.md + TOOLS.md**

---

## Tools vs Skills vs MCP

These three concepts are all "information given to the LLM," but they differ in how they're delivered and what happens after.

### Tools — Executable Functions

Tools are **code functions** with JSON Schema parameters. They are:
1. Sent in the `tools` array of the API request as JSON schemas
2. The LLM returns `tool_use` blocks to invoke them
3. OpenClaw **executes** the function locally and sends results back

```json
{
  "name": "exec",
  "description": "Execute a shell command",
  "input_schema": {
    "type": "object",
    "properties": {
      "command": { "type": "string" },
      "timeout": { "type": "number" }
    },
    "required": ["command"]
  }
}
```

**Built-in tools** (20 tools from the sessions.json example):

| Tool | Properties | Purpose |
|------|------------|---------|
| `read` | 4 | Read files from disk |
| `edit` | 6 | Edit files (diff-based) |
| `write` | 3 | Write/create files |
| `exec` | 12 | Execute shell commands |
| `process` | 12 | Manage processes |
| `browser` | 28 | Browser automation |
| `canvas` | 18 | Visual canvas operations |
| `nodes` | 33 | Node graph operations |
| `message` | 85 | Send messages to channels |
| `tts` | 2 | Text-to-speech |
| `agents_list` | 0 | List configured agents |
| `sessions_list` | 4 | List active sessions |
| `sessions_history` | 3 | Read session history |
| `sessions_send` | 5 | Send message to another session |
| `sessions_spawn` | 10 | Spawn a subagent |
| `subagents` | 4 | Manage running subagents |
| `session_status` | 2 | Get current session info |
| `web_search` | 6 | Search the web |
| `web_fetch` | 3 | Fetch a URL |
| `memory_search` | 3 | Search persistent memory |
| `memory_get` | 3 | Get memory entries |

### Skills — Markdown Instructions (Progressive Loading)

> Full 13-step code trace: see [Progressive Skill Loading](#progressive-skill-loading--how-it-actually-works) section.

Skills are **markdown instruction files** (`SKILL.md`). They are:
1. Scanned at startup — only **name + description + location** go into the system prompt as XML
2. The LLM reads the full SKILL.md via the `read` tool **on demand**
3. The LLM **follows the instructions** in the skill file

```xml
<available_skills>
  <skill>
    <name>weather</name>
    <description>Get current weather and forecasts (no API key required).</description>
    <location>~/.openclaw/workspace/skills/weather-1/SKILL.md</location>
  </skill>
</available_skills>
```

The system prompt instructs the LLM:
```
Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: read its SKILL.md at <location> with `read`, then follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply: do not read any SKILL.md.
Constraints: never read more than one skill up front; only read after selecting.
```

**Skill sources (6 directories, lowest → highest precedence):**

| Source | Directory | Code label |
|--------|-----------|------------|
| Extra dirs | Configured via `skills.load.extraDirs` | `openclaw-extra` |
| Bundled | Shipped with the install | `openclaw-bundled` |
| Managed | `~/.openclaw/skills/` | `openclaw-managed` |
| Personal agents | `~/.agents/skills/` | `agents-skills-personal` |
| Project agents | `<workspace>/.agents/skills/` | `agents-skills-project` |
| Workspace | `<workspace>/skills/` | `openclaw-workspace` |

Same-named skills in higher-precedence directories override lower ones.

**Skill limits:**
- Max **150 skills** in the prompt (configurable: `skills.load.maxSkillsInPrompt`)
- Max **30,000 chars** total for skills XML (configurable: `skills.load.maxSkillsPromptChars`)
- Max **256KB** per SKILL.md file size
- Each skill has `disableModelInvocation` flag (if true, excluded from prompt XML)

### MCP/ACP — External Tool Servers

MCP (Model Context Protocol) tools come from **external servers** connected via stdio or HTTP. OpenClaw wraps them through the **ACP (Agent Client Protocol)** layer.

**Connection flow:**

```typescript
// 1. Spawn external MCP server process
const agent = spawn(serverCommand, args, {
  stdio: ["pipe", "pipe", "inherit"],
});

// 2. Initialize ACP connection
const client = new ClientSideConnection(handlers, stream);
await client.initialize({
  protocolVersion: PROTOCOL_VERSION,
  clientCapabilities: { fs: { readTextFile: true, writeTextFile: true }, terminal: true },
  clientInfo: { name: "openclaw-acp-client", version: "1.0.0" },
});

// 3. Create session
const session = await client.newSession({ cwd, mcpServers: [] });
```

**Permission handling for MCP tools:**
- Safe kinds auto-approved: `read`, `search`
- Dangerous tools require user permission prompt
- Classification: `read | search | fetch | edit | delete | move | execute | other`

### Comparison Table

| Aspect | Tools | Skills | MCP/ACP |
|--------|-------|--------|---------|
| Format | JSON Schema | Markdown (SKILL.md) | JSON Schema (from server) |
| In API request | `tools` array | System prompt text | `tools` array (wrapped) |
| Execution | Framework runs code locally | LLM reads + follows instructions | Framework calls external server |
| Loading | All schemas sent every request | Progressive (summary → read on demand) | Discovered via `list_tools()` |
| Examples | `exec`, `read`, `write` | `weather`, `github`, `coding-agent` | External APIs, databases |

---

## 7-Tier Binding System — Message Routing

When a message arrives, OpenClaw must decide **which agent handles it**. The binding system evaluates 7 tiers in strict priority order.

**File:** `src/routing/resolve-route.ts`

```typescript
const tiers = [
  {
    matchedBy: "binding.peer",           // Tier 1: exact peer match
    predicate: (c) => c.match.peer.state === "valid",
  },
  {
    matchedBy: "binding.peer.parent",    // Tier 2: thread parent match
    predicate: (c) => c.match.peer.state === "valid",
  },
  {
    matchedBy: "binding.guild+roles",    // Tier 3: guild + member roles
    predicate: (c) => hasGuildConstraint(c.match) && hasRolesConstraint(c.match),
  },
  {
    matchedBy: "binding.guild",          // Tier 4: guild only
    predicate: (c) => hasGuildConstraint(c.match) && !hasRolesConstraint(c.match),
  },
  {
    matchedBy: "binding.team",           // Tier 5: MS Teams match
    predicate: (c) => hasTeamConstraint(c.match),
  },
  {
    matchedBy: "binding.account",        // Tier 6: account-specific
    predicate: (c) => c.match.accountPattern !== "*",
  },
  {
    matchedBy: "binding.channel",        // Tier 7: channel-wide default
    predicate: (c) => c.match.accountPattern === "*",
  },
];

// Falls through to DEFAULT_AGENT_ID ("main") if no tier matches
```

### Practical Example

Config with 4 bots in one Telegram group:

```yaml
telegram:
  accounts:
    jenny-bot:
      token: "BOT_TOKEN_1"
      bindings:
        - peer: "group:-5102648542"
          agentId: jenny-manager
    jack-bot:
      token: "BOT_TOKEN_2"
      bindings:
        - peer: "group:-5102648542"
          agentId: jack-3d-drafter
    jade-bot:
      token: "BOT_TOKEN_3"
      bindings:
        - peer: "group:-5102648542"
          agentId: jade-2d-drafter
    jacob-bot:
      token: "BOT_TOKEN_4"
      bindings:
        - peer: "group:-5102648542"
          agentId: jacob-director
```

When a message arrives in group `-5102648542` via `jenny-bot`:
1. Tier 1 (peer) matches: `peer: "group:-5102648542"` → routes to `jenny-manager`
2. Session key: `agent:jenny-manager:telegram:group:-5102648542`

---

## Multi-Agent Architecture

### Subagent Spawning

**File:** `src/agents/tools/sessions-spawn-tool.ts`

The `sessions_spawn` tool creates subagent sessions:

```typescript
const SessionsSpawnToolSchema = Type.Object({
  task: Type.String(),                                    // required: task description
  label: Type.Optional(Type.String()),                    // display name
  agentId: Type.Optional(Type.String()),                  // which agent to spawn
  model: Type.Optional(Type.String()),                    // model override
  thinking: Type.Optional(Type.String()),                 // extended thinking level
  runTimeoutSeconds: Type.Optional(Type.Number()),        // execution timeout
  cleanup: optionalStringEnum(["delete", "keep"]),        // session cleanup policy
});
```

**Subagent characteristics:**
- Get their own session key with `:subagent:` or `:sub:` suffix
- Only receive **AGENTS.md + TOOLS.md** as bootstrap files (not SOUL.md, IDENTITY.md, etc.)
- Depth tracked via `getSubagentDepth()` — counts `:subagent:` occurrences in session key
- Can be cleaned up (`delete`) or kept (`keep`) after completion

### Inter-Agent Communication

**File:** `src/agents/tools/sessions-send-helpers.ts`

Agents communicate via a **ping-pong exchange protocol**:

```
Agent A calls sessions_send(targetSession, "Please review this design")
    │
    ▼
Agent B receives message, processes, replies
    │
    ▼
Agent A receives reply, can respond back
    │
    ▼
... up to 5 exchanges (MAX_PING_PONG_TURNS) ...
    │
    ▼
Either agent replies "REPLY_SKIP" to stop
```

**Special tokens:**
- `REPLY_SKIP` — Stops the ping-pong exchange ("I'm done, no more back-and-forth")
- `ANNOUNCE_SKIP` — Silent exit from the announce phase ("Nothing to report to the channel")

**Turn context injected into each exchange:**

```typescript
function buildAgentToAgentReplyContext(params) {
  return [
    "Agent-to-agent reply step:",
    `Current agent: ${currentLabel}.`,
    `Turn ${params.turn} of ${params.maxTurns}.`,
    `Agent 1 (requester) session: ${params.requesterSessionKey}.`,
    `Agent 2 (target) session: ${params.targetSessionKey}.`,
    `If you want to stop the ping-pong, reply exactly "REPLY_SKIP".`,
  ].join("\n");
}
```

### Available Inter-Agent Tools

| Tool | Purpose |
|------|---------|
| `agents_list` | List all configured agents |
| `sessions_list` | List active sessions (filter by kind, recency) |
| `sessions_history` | Read another session's conversation history (max 80KB) |
| `sessions_send` | Send a message to another session (triggers ping-pong) |
| `sessions_spawn` | Spawn a new subagent session |
| `subagents` | List/manage running subagents |

### sessions_list Parameters

```typescript
{
  kinds: string[],           // filter by session kind
  limit: number,             // max entries to return
  activeMinutes: number,     // only sessions active in last N minutes
  messageLimit: number,      // include last N messages per session
}
```

### sessions_history Parameters

```typescript
{
  sessionKey: string,        // which session to read
  limit: number,             // max messages to return
  includeTools: boolean,     // include tool_use/tool_result entries
}
```

**Constraints:** max 80KB response, 4000 chars per text block, strips images/usage/cost data.

---

## Telegram Multi-Bot Group Setup

### The Problem

When multiple bots are in one Telegram group with **privacy mode OFF**, every bot receives every message. With 4 bots, that's 4 LLM API calls per human message.

### The Solution: `requireMention`

**File:** `src/config/types.telegram.ts`

```typescript
export type TelegramGroupConfig = {
  requireMention?: boolean;        // only respond when @mentioned
  groupPolicy?: GroupPolicy;       // "open" | "disabled" | "allowlist"
  allowFrom?: Array<string | number>;  // allowed sender IDs
  skills?: string[];               // skill allowlist for this group
  systemPrompt?: string;           // extra system prompt for this group
  enabled?: boolean;               // enable/disable bot for this group
  topics?: Record<string, TelegramTopicConfig>;  // per-topic config
};
```

### Correct Config for 4 Bots in One Group

```yaml
telegram:
  accounts:
    jenny-bot:
      token: "BOT_TOKEN_1"
      bindings:
        - peer: "group:-5102648542"
          agentId: jenny-manager
      groups:
        "-5102648542":
          requireMention: true      # only respond to @jenny_bot
          groupPolicy: open

    jack-bot:
      token: "BOT_TOKEN_2"
      bindings:
        - peer: "group:-5102648542"
          agentId: jack-3d-drafter
      groups:
        "-5102648542":
          requireMention: true      # only respond to @jack_3d_bot
          groupPolicy: open

    jade-bot:
      token: "BOT_TOKEN_3"
      bindings:
        - peer: "group:-5102648542"
          agentId: jade-2d-drafter
      groups:
        "-5102648542":
          requireMention: true
          groupPolicy: open

    jacob-bot:
      token: "BOT_TOKEN_4"
      bindings:
        - peer: "group:-5102648542"
          agentId: jacob-director
      groups:
        "-5102648542":
          requireMention: true
          groupPolicy: open
```

**Key points:**
- `requireMention` must be set **per-account, per-group** (not top-level)
- Telegram privacy mode must be **OFF** (so bots can see @mentions)
- The `requireMention` filter runs **before** the LLM API call — no wasted tokens
- Each bot only responds when its specific @username is mentioned

### Per-Agent Skills

Each agent can have different skills via the group config or workspace structure:

```yaml
# In the group config:
groups:
  "-5102648542":
    skills: ["3d-modeling", "blender"]  # only these skills for this group

# Or via per-agent workspace:
# ~/.openclaw/agents/jack-3d-drafter/workspace/skills/
#   └── 3d-modeling/SKILL.md
#   └── blender/SKILL.md
```

---

## Sessions Deep Dive

### Session Key Format

```
agent:{agentId}:{rest}
```

Where `{rest}` varies by context:

| Context | Rest Format | Example |
|---------|-------------|---------|
| Default DM | `main` | `agent:main:main` |
| Channel DM | `{channel}:direct:{peerId}` | `agent:main:telegram:direct:98765` |
| Group | `{channel}:group:{groupId}` | `agent:main:telegram:group:-510264` |
| Group topic | `{channel}:group:{groupId}:topic:{threadId}` | `agent:main:telegram:group:-510264:topic:42` |
| Cron | `cron:{cronId}` | `agent:main:cron:0edbc111-...` |
| Cron sub-run | `cron:{cronId}:run:{runId}` | `agent:main:cron:0edb...:run:da1f...` |
| Subagent | `{parent}:subagent:{n}` | `agent:main:telegram:group:-510264:subagent:0` |

### DM Scope

**File:** `src/routing/session-key.ts`

The `dmScope` config controls whether DMs from different channels share a session:

| dmScope | Behavior | DM Session Key |
|---------|----------|----------------|
| `"main"` (default) | All channels share one DM session | `agent:main:main` |
| `"channel"` | Each channel gets its own DM session | `agent:main:telegram:direct:12345` |

### Thread Parent Resolution

```typescript
// src/sessions/session-key-utils.ts
function resolveThreadParentSessionKey(sessionKey: string): string | null {
  // Finds the last ":thread:" or ":topic:" marker
  // Returns everything before it as the parent session key
  // "agent:main:telegram:group:-510264:topic:42" → "agent:main:telegram:group:-510264"
}
```

### Subagent Depth Tracking

```typescript
function getSubagentDepth(sessionKey: string): number {
  return sessionKey.split(":subagent:").length - 1;
  // "agent:main:telegram:group:-510264:subagent:0" → depth 1
  // "agent:main:...:subagent:0:subagent:1" → depth 2
}
```

### sessions.json Index Fields

Complete field reference from the actual template file:

| Field | Type | Description |
|-------|------|-------------|
| `sessionId` | UUID | Links to the `.jsonl` transcript file |
| `sessionFile` | string | Absolute path to the `.jsonl` file |
| `updatedAt` | number | Unix timestamp (ms) of last activity |
| `systemSent` | boolean | Whether system prompt has been sent to LLM |
| `channel` | string | Channel this session belongs to |
| `chatType` | string | `"direct"` or `"group"` |
| `lastChannel` | string | Last channel that wrote to this session |
| `lastTo` | string | Last delivery target |
| `lastAccountId` | string | Last bot account that handled this |
| `modelProvider` | string | LLM provider (e.g., `"anthropic"`) |
| `model` | string | Model name (e.g., `"claude-sonnet-4-20250514"`) |
| `contextTokens` | number | Model's context window size |
| `inputTokens` | number | Tokens in last input |
| `outputTokens` | number | Tokens in last output |
| `totalTokens` | number | Total tokens used across session |
| `totalTokensFresh` | boolean | Whether totalTokens is up-to-date |
| `cacheRead` | number | Prompt cache hits |
| `cacheWrite` | number | Prompt cache writes |
| `abortedLastRun` | boolean | Whether last LLM run was interrupted |
| `label` | string | Display label (used for cron sessions) |
| `groupId` | string | Telegram group ID (for group sessions) |
| `displayName` | string | Human-readable session name |
| `deliveryContext` | object | `{ channel, to, accountId }` — where to send replies |
| `origin` | object | `{ label, provider, from, to }` — who started this |
| `authProfileOverride` | string | API key profile override |
| `skillsSnapshot` | object | Frozen skills state for change detection |
| `systemPromptReport` | object | Diagnostic info about the system prompt |

### Session Store Maintenance

**File:** `src/config/sessions/store.ts`

| Setting | Value |
|---------|-------|
| Cache TTL | 45 seconds |
| Pruning | Entries older than 30 days removed |
| Entry cap | Max 500 entries per agent |
| File rotation | At 10MB |
| Write strategy | Atomic (temp file → rename) |

---

## History Compaction

When conversation history grows too large for the context window, OpenClaw compacts it.

**File:** `src/agents/pi-embedded-runner/compact.ts`

### How It Works

1. **Detect overflow** — History tokens exceed context window threshold
2. **Lock session** — Write lock prevents concurrent access
3. **Run before_compaction hooks** — Plugins get notified
4. **Call `session.compact()`** — LLM summarizes old messages into a condensed form
5. **Measure metrics** — Pre/post message count, token count, char count
6. **Run after_compaction hooks** — Analytics/cleanup
7. **Save compacted history** — Old messages replaced with summary

### Compaction Result

```typescript
{
  ok: boolean,
  compacted: boolean,
  reason?: string,    // "no_compactable_entries", "below_threshold", "timeout", etc.
  result?: {
    summary: string,           // the LLM-generated summary
    firstKeptEntryId: string,  // where the kept history starts
    tokensBefore: number,
    tokensAfter?: number,
  }
}
```

### Compaction Reasons (when skipped)

| Reason | Meaning |
|--------|---------|
| `no_compactable_entries` | Nothing to compact |
| `below_threshold` | History is small enough |
| `already_compacted_recently` | Compacted too recently |
| `guard_blocked` | Safety guard prevented it |
| `summary_failed` | LLM failed to generate summary |
| `timeout` | Compaction timed out |
| `provider_error_4xx` | LLM API client error |
| `provider_error_5xx` | LLM API server error |

---

## Progressive Skill Loading — How It Actually Works

**Final goal:** produce one XML `string` that gets injected into the system prompt, telling the LLM what skills exist and where to `read` them on demand. The full SKILL.md body is never in the prompt.

**Entry point:** `attempt.ts:249–267` calls `loadWorkspaceSkillEntries()` → `resolveSkillsPromptForRun()`. Both are in `src/agents/skills/workspace.ts`. `loadWorkspaceSkillEntries()` (line 556–564) is a thin wrapper that calls `loadSkillEntries()` (line 221–406).

---

### Step 1: Resolve 6 Source Directories

**Function:** `loadSkillEntries()` — workspace.ts:324–335
**Input:** `workspaceDir: string`, `config: OpenClawConfig`
**Output:** 6 resolved directory paths, each tagged with a source label

```typescript
// workspace.ts:324–335
const managedSkillsDir    = opts?.managedSkillsDir ?? path.join(CONFIG_DIR, "skills");  // ~/.openclaw/skills/
const workspaceSkillsDir  = path.resolve(workspaceDir, "skills");                       // <workspace>/skills/
const bundledSkillsDir    = opts?.bundledSkillsDir ?? resolveBundledSkillsDir();         // next to executable
const extraDirsRaw        = opts?.config?.skills?.load?.extraDirs ?? [];                 // from openclaw.json
const pluginSkillDirs     = resolvePluginSkillDirs({ workspaceDir, config: opts?.config });
const mergedExtraDirs     = [...extraDirs, ...pluginSkillDirs];
const personalAgentsSkillsDir = path.resolve(os.homedir(), ".agents", "skills");         // ~/.agents/skills/
const projectAgentsSkillsDir  = path.resolve(workspaceDir, ".agents", "skills");         // <workspace>/.agents/skills/
```

---

### Step 2: Scan Each Directory for SKILL.md Files

**Function:** `loadSkills()` (inner closure) — workspace.ts:231–322
**Input:** `{ dir: string, source: string }` — one of the 6 directories
**Output:** `Skill[]` — array of `Skill` objects from that directory

**Key object — `ResolvedSkillsLimits`** (workspace.ts:130–136, defaults at lines 95–99):
```typescript
type ResolvedSkillsLimits = {
  maxCandidatesPerRoot:     300,    // max child dirs to scan per source
  maxSkillsLoadedPerSource: 200,    // max skills loaded from one source
  maxSkillsInPrompt:        150,    // max skills in final XML
  maxSkillsPromptChars:     30_000, // max chars in final XML string
  maxSkillFileBytes:        256_000 // max SKILL.md file size (256KB)
};
```

**Process:**

1. `listChildDirectories(baseDir)` (workspace.ts:150–176) — calls `fs.readdirSync(dir, { withFileTypes: true })`, returns child folder names, skips `.`-prefixed and `node_modules`
2. Sort alphabetically, cap at `maxSkillsLoadedPerSource` (line 263)
3. For each child folder:

```typescript
// workspace.ts:285–307
for (const name of limitedChildren) {
  const skillDir = path.join(baseDir, name);       // e.g. ~/.openclaw/skills/weather
  const skillMd = path.join(skillDir, "SKILL.md"); // e.g. ~/.openclaw/skills/weather/SKILL.md

  if (!fs.existsSync(skillMd)) { continue; }       // no SKILL.md → skip

  const size = fs.statSync(skillMd).size;
  if (size > limits.maxSkillFileBytes) { continue; } // > 256KB → skip

  // ════════════════════════════════════════════════════════════
  // READ #1 — external package reads SKILL.md frontmatter
  // ════════════════════════════════════════════════════════════
  const loaded = loadSkillsFromDir({ dir: skillDir, source: params.source });
  loadedSkills.push(...unwrapLoadedSkills(loaded));
}
```

`loadSkillsFromDir()` is imported from `@mariozechner/pi-coding-agent` (workspace.ts:6). Source code unavailable — it's a build/runtime dependency not in node_modules. It reads SKILL.md, parses frontmatter, returns `Skill` objects.

`unwrapLoadedSkills()` (workspace.ts:208–219) handles two possible return shapes:
```typescript
function unwrapLoadedSkills(loaded: unknown): Skill[] {
  if (Array.isArray(loaded))                              return loaded as Skill[];
  if (loaded && typeof loaded === "object" && "skills" in loaded)
    return (loaded as { skills?: unknown }).skills as Skill[];   // { skills: Skill[] }
  return [];
}
```

**Key object — `Skill`** (from `@mariozechner/pi-coding-agent`, type shape inferred from usage):
```typescript
// Proven by usage at workspace.ts lines 51, 372, 393, 594, 700, 718:
type Skill = {
  name:         string;   // from frontmatter "name:"         (line 372: merged.set(skill.name, skill))
  description?: string;   // from frontmatter "description:"  (line 718: entry.skill.description?.trim())
  filePath:     string;   // absolute path to SKILL.md        (line 393: fs.readFileSync(skill.filePath))
  baseDir:      string;   // parent directory of SKILL.md     (line 594: path.basename(entry.skill.baseDir))
  // possibly other fields (proven by spread ...s at line 50)
};
```

Example — given `~/.openclaw/skills/weather/SKILL.md`:
```markdown
---
name: weather
description: "Get current weather and forecasts via wttr.in"
metadata: { "openclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---
# Weather Skill
(body content — NOT read at this step)
```

Read #1 produces:
```typescript
{
  name: "weather",
  description: "Get current weather and forecasts via wttr.in",
  filePath: "/home/jj/.openclaw/skills/weather/SKILL.md",
  baseDir: "/home/jj/.openclaw/skills/weather"
}
```

Note: Read #1 does **NOT** extract `metadata`. That field is OpenClaw-specific. That's why Read #2 exists (Step 4).

---

### Step 3: Merge by Name (Precedence)

**Function:** `loadSkillEntries()` — workspace.ts:369–388
**Input:** 6 arrays of `Skill[]` (one per source directory from Step 2)
**Output:** `Map<string, Skill>` — deduplicated, one `Skill` per unique name

```typescript
// workspace.ts:369–388
const merged = new Map<string, Skill>();
// Precedence: extra(lowest) < bundled < managed < personal < project < workspace(highest)
for (const skill of extraSkills)          { merged.set(skill.name, skill); }  // overwritten by...
for (const skill of bundledSkills)        { merged.set(skill.name, skill); }  // overwritten by...
for (const skill of managedSkills)        { merged.set(skill.name, skill); }  // overwritten by...
for (const skill of personalAgentsSkills) { merged.set(skill.name, skill); }  // overwritten by...
for (const skill of projectAgentsSkills)  { merged.set(skill.name, skill); }  // overwritten by...
for (const skill of workspaceSkills)      { merged.set(skill.name, skill); }  // wins
```

`Map.set()` overwrites on duplicate key. If `weather` exists in both bundled and workspace, the workspace `Skill` object (with its `filePath` pointing to the workspace copy) replaces the bundled one.

---

### Step 4: Re-read SKILL.md for OpenClaw Metadata

**Function:** `loadSkillEntries()` — workspace.ts:390–404
**Input:** `Map<string, Skill>` from Step 3 (deduplicated `Skill` objects)
**Output:** `SkillEntry[]` — each `Skill` now wrapped with parsed frontmatter, metadata, and invocation policy

```typescript
// workspace.ts:390–404
const skillEntries: SkillEntry[] = Array.from(merged.values()).map((skill) => {
  let frontmatter: ParsedSkillFrontmatter = {};
  try {
    // ════════════════════════════════════════════════════════════
    // READ #2 — OpenClaw re-reads the same SKILL.md file
    // ════════════════════════════════════════════════════════════
    const raw = fs.readFileSync(skill.filePath, "utf-8");
    frontmatter = parseFrontmatter(raw);   // → parseFrontmatterBlock() in src/markdown/frontmatter.ts
  } catch {}
  return {
    skill,                                                   // Skill from external package (Step 2)
    frontmatter,                                             // ParsedSkillFrontmatter
    metadata:   resolveOpenClawMetadata(frontmatter),        // OpenClawSkillMetadata
    invocation: resolveSkillInvocationPolicy(frontmatter),   // SkillInvocationPolicy
  };
});
```

**Why Read #2?** The external package (Read #1) only extracts `name`, `description`, `filePath`, `baseDir` — standard AgentSkills-spec fields. It does NOT parse `metadata`, `user-invocable`, or `disable-model-invocation`. OpenClaw needs these for gating (Step 5) and invocation policy. The external `Skill` type has no fields for them, so OpenClaw must re-read and re-parse the file itself.

**`parseFrontmatter()`** (src/agents/skills/frontmatter.ts:21–23) calls **`parseFrontmatterBlock()`** (src/markdown/frontmatter.ts:133–157) which runs a **dual parse** — two parsers on the same frontmatter block:

```typescript
// src/markdown/frontmatter.ts:133–157
export function parseFrontmatterBlock(content: string): ParsedFrontmatter {
  const normalized = content.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!normalized.startsWith("---")) return {};
  const endIndex = normalized.indexOf("\n---", 3);
  if (endIndex === -1) return {};
  const block = normalized.slice(4, endIndex);        // text between --- markers

  const lineParsed = parseLineFrontmatter(block);     // regex: /^([\w-]+):\s*(.*)$/ per line
  const yamlParsed = parseYamlFrontmatter(block);     // YAML.parse(block, { schema: "core" })

  if (yamlParsed === null) return lineParsed;          // YAML failed → line parser only
  const merged: ParsedFrontmatter = { ...yamlParsed };
  for (const [key, value] of Object.entries(lineParsed)) {
    if (value.startsWith("{") || value.startsWith("[")) {
      merged[key] = value;                            // line parser wins for JSON values
    }
  }
  return merged;
}
```

Why two parsers? The `metadata` field is a single-line JSON string: `{ "openclaw": { ... } }`. The YAML parser destructures it into a nested JS object (loses the raw string). The line parser captures everything after `metadata:` as a raw string. The merge rule (lines 151–155) ensures JSON values keep the raw string form, which OpenClaw later `JSON.parse()`-s.

**Key object — `ParsedSkillFrontmatter`** (src/agents/skills/types.ts:64):
```typescript
type ParsedSkillFrontmatter = Record<string, string>;
// All values are strings. For the weather skill:
{
  name: "weather",
  description: "Get current weather and forecasts via wttr.in",
  metadata: "{ \"openclaw\": { \"emoji\": \"🌤️\", \"requires\": { \"bins\": [\"curl\"] } } }"
}
```

**`resolveOpenClawMetadata()`** (src/agents/skills/frontmatter.ts:81–101) takes the `metadata` string, calls `resolveOpenClawManifestBlock()` which `JSON.parse()`-s it, then extracts:

**Key object — `OpenClawSkillMetadata`** (src/agents/skills/types.ts:19–33):
```typescript
type OpenClawSkillMetadata = {
  always?:     boolean;            // true → skip all other gates
  skillKey?:   string;             // override config key (default: skill name)
  primaryEnv?: string;             // env var for skills.entries.<name>.apiKey
  emoji?:      string;             // macOS Skills UI icon
  homepage?:   string;             // URL for macOS Skills UI
  os?:         string[];           // platform filter: ["darwin", "linux", "win32"]
  requires?: {
    bins?:     string[];           // each must exist on PATH
    anyBins?:  string[];           // at least one must exist on PATH
    env?:      string[];           // env var must exist or be in config
    config?:   string[];           // openclaw.json paths that must be truthy
  };
  install?:    SkillInstallSpec[]; // installer specs (brew/node/go/uv/download)
};
```

**`resolveSkillInvocationPolicy()`** (src/agents/skills/frontmatter.ts:103–113) reads top-level frontmatter keys:

**Key object — `SkillInvocationPolicy`** (src/agents/skills/types.ts:35–38):
```typescript
type SkillInvocationPolicy = {
  userInvocable:           boolean;   // from "user-invocable:" key (default: true)
  disableModelInvocation:  boolean;   // from "disable-model-invocation:" key (default: false)
};
```

**Key object — `SkillEntry`** (src/agents/skills/types.ts:66–71) — the output of Step 4:
```typescript
type SkillEntry = {
  skill:       Skill;                     // from external package (name, desc, filePath, baseDir)
  frontmatter: ParsedSkillFrontmatter;    // Record<string, string> — raw key-value pairs
  metadata?:   OpenClawSkillMetadata;     // parsed from metadata JSON string — gating info
  invocation?: SkillInvocationPolicy;     // user-invocable + disable-model-invocation flags
};
```

Example — for the weather skill, Step 4 produces:
```typescript
{
  skill:       { name: "weather", description: "Get current...", filePath: "/home/jj/...", baseDir: "/home/jj/..." },
  frontmatter: { name: "weather", description: "Get current...", metadata: "{ \"openclaw\": ... }" },
  metadata:    { emoji: "🌤️", requires: { bins: ["curl"] } },
  invocation:  { userInvocable: true, disableModelInvocation: false }
}
```

`loadSkillEntries()` returns `SkillEntry[]`. This is the output of the entire function (workspace.ts:221–406).

---

### Step 5: Filter by Gates

**Function:** `filterSkillEntries()` — workspace.ts:67–88, calls `shouldIncludeSkill()` — config.ts:70–112
**Input:** `SkillEntry[]` from Step 4
**Output:** `SkillEntry[]` — only skills that pass all gate checks

```typescript
// workspace.ts:67–88
function filterSkillEntries(entries, config, skillFilter, eligibility): SkillEntry[] {
  let filtered = entries.filter((entry) => shouldIncludeSkill({ entry, config, eligibility }));
  if (skillFilter !== undefined) {
    const normalized = normalizeSkillFilter(skillFilter) ?? [];
    filtered = normalized.length > 0
      ? filtered.filter((entry) => normalized.includes(entry.skill.name))
      : [];
  }
  return filtered;
}
```

`shouldIncludeSkill()` (src/agents/skills/config.ts:70–112) checks gates in this order:

```typescript
// config.ts:70–112
export function shouldIncludeSkill(params): boolean {
  const skillKey = resolveSkillKey(entry.skill, entry);         // metadata.skillKey ?? skill.name
  const skillConfig = resolveSkillConfig(config, skillKey);     // config.skills.entries[skillKey]

  if (skillConfig?.enabled === false)        return false;       // ① explicitly disabled in config
  if (!isBundledSkillAllowed(entry, allow))  return false;       // ② not in allowBundled list
  if (osList.length > 0 && !osList.includes(platform)           // ③ wrong OS
      && !remotePlatforms.some(p => osList.includes(p)))
    return false;
  if (entry.metadata?.always === true)       return true;        // ④ always: true → skip remaining

  return evaluateRuntimeRequires({                               // ⑤ check bins, env, config
    requires: entry.metadata?.requires,
    hasBin: hasBinary,                                           //   bins:   each must be on PATH
    hasEnv: (envName) => Boolean(                                //   env:    in process.env or config
      process.env[envName] || skillConfig?.env?.[envName] ||
      (skillConfig?.apiKey && entry.metadata?.primaryEnv === envName)
    ),
    isConfigPathTruthy: (p) => isConfigPathTruthy(config, p),   //   config: path must be truthy
  });
}
```

Example:
```
weather       → ✅ requires.bins: ["curl"] → curl exists on PATH → included
some-mac-tool → ❌ os: ["darwin"] but runtime is linux  → removed
disabled-skill→ ❌ config.skills.entries.disabled-skill.enabled: false → removed
```

---

### Step 6: Remove `disableModelInvocation` Skills from Prompt List

**Function:** `buildWorkspaceSkillSnapshot()` — workspace.ts:466–468
**Input:** `SkillEntry[]` from Step 5 (gate-filtered)
**Output:** `SkillEntry[]` — only skills the LLM is allowed to see in the prompt

```typescript
// workspace.ts:466–468
const promptEntries = eligible.filter(
  (entry) => entry.invocation?.disableModelInvocation !== true,
);
```

Skills with `disable-model-invocation: true` in frontmatter pass gating but are excluded from the XML prompt. They can still be invoked by the user via `/slash-command`.

---

### Step 7: Extract `Skill[]` from Entries

**Function:** `buildWorkspaceSkillSnapshot()` — workspace.ts:469
**Input:** `SkillEntry[]` from Step 6
**Output:** `Skill[]` — unwrapped back to plain `Skill` objects for prompt generation

```typescript
// workspace.ts:469
const resolvedSkills = promptEntries.map((entry) => entry.skill);
```

---

### Step 8: Apply Size Limits

**Function:** `applySkillsPromptLimits()` — workspace.ts:408–444
**Input:** `Skill[]` from Step 7
**Output:** `{ skillsForPrompt: Skill[], truncated: boolean, truncatedReason: "count" | "chars" | null }`

```typescript
// workspace.ts:408–444
function applySkillsPromptLimits(params: { skills: Skill[]; config?: OpenClawConfig }) {
  const limits = resolveSkillsLimits(params.config);

  // Cap 1: max number of skills (default 150)
  const byCount = params.skills.slice(0, limits.maxSkillsInPrompt);

  // Cap 2: max chars in XML output (default 30,000) — binary search
  const fits = (skills: Skill[]): boolean => {
    const block = formatSkillsForPrompt(skills);       // calls external package to generate XML
    return block.length <= limits.maxSkillsPromptChars;
  };

  if (!fits(skillsForPrompt)) {
    let lo = 0;
    let hi = skillsForPrompt.length;
    while (lo < hi) {                                  // binary search for largest fitting prefix
      const mid = Math.ceil((lo + hi) / 2);
      if (fits(skillsForPrompt.slice(0, mid))) { lo = mid; }
      else { hi = mid - 1; }
    }
    skillsForPrompt = skillsForPrompt.slice(0, lo);
  }

  return { skillsForPrompt, truncated, truncatedReason };
}
```

---

### Step 9: Compact File Paths

**Function:** `compactSkillPaths()` — workspace.ts:45–53
**Input:** `Skill[]` from Step 8
**Output:** `Skill[]` with `filePath` shortened (`/home/jj/...` → `~/...`)

```typescript
// workspace.ts:45–53
function compactSkillPaths(skills: Skill[]): Skill[] {
  const home = os.homedir();
  const prefix = home.endsWith(path.sep) ? home : home + path.sep;
  return skills.map((s) => ({
    ...s,
    filePath: s.filePath.startsWith(prefix)
      ? "~/" + s.filePath.slice(prefix.length)     // /home/jj/.openclaw/... → ~/.openclaw/...
      : s.filePath,
  }));
}
```

Saves tokens in the system prompt. The LLM's `read` tool understands `~/` paths.

---

### Step 10: Generate XML String

**Function:** `formatSkillsForPrompt()` — from `@mariozechner/pi-coding-agent` (external, source unavailable)
**Called at:** workspace.ts:483
**Input:** `Skill[]` from Step 9 (with compacted paths)
**Output:** `string` — the final XML block

```typescript
// workspace.ts:480–486
const prompt = [
  remoteNote,                                                          // optional remote node note
  truncationNote,                                                      // optional truncation warning
  formatSkillsForPrompt(compactSkillPaths(skillsForPrompt)),           // ← THE XML string
]
  .filter(Boolean)
  .join("\n");
```

Output format (from docs/tools/skills.md:269–283):
```xml
<available_skills>
  <skill>
    <name>weather</name>
    <description>Get current weather and forecasts via wttr.in or Open-Meteo.</description>
    <location>~/.openclaw/skills/weather/SKILL.md</location>
  </skill>
  <skill>
    <name>github</name>
    <description>GitHub operations via gh CLI.</description>
    <location>~/.openclaw/skills/github/SKILL.md</location>
  </skill>
</available_skills>
```

Token cost formula (documented): `total_chars = 195 + Σ (97 + len(name) + len(description) + len(location))`
- 195 = `<available_skills>...</available_skills>` wrapper (only when ≥1 skill)
- 97 = per-skill XML tag overhead (`<skill><name>`, `</name>`, `<description>`, etc.)

---

### Step 11: Store in SkillSnapshot

**Function:** `buildWorkspaceSkillSnapshot()` — workspace.ts:488–497
**Input:** XML `string` from Step 10, eligible `SkillEntry[]` from Step 5
**Output:** `SkillSnapshot` — stored in `sessions.json` for reuse across turns

**Key object — `SkillSnapshot`** (src/agents/skills/types.ts:82–89):
```typescript
type SkillSnapshot = {
  prompt:          string;                                       // the XML string from Step 10
  skills:          Array<{ name: string; primaryEnv?: string }>; // eligible skill names + env keys
  skillFilter?:    string[];                                     // agent-level filter if applied
  resolvedSkills?: Skill[];                                      // full Skill objects for change detection
  version?:        number;                                       // snapshot version counter
};
```

```typescript
// workspace.ts:488–497
return {
  prompt,                                  // XML string → will be injected into system prompt
  skills: eligible.map((entry) => ({
    name: entry.skill.name,
    primaryEnv: entry.metadata?.primaryEnv,
  })),
  resolvedSkills,                          // Skill[] for detecting changes between sessions
  version: opts?.snapshotVersion,
};
```

Purpose: if skills change between sessions (installed, removed, modified), the snapshot detects the diff and triggers system prompt regeneration.

---

### Step 12: Resolve Prompt for Agent Run

**Function:** `resolveSkillsPromptForRun()` — workspace.ts:536–554
**Called from:** attempt.ts:262–267
**Input:** `SkillSnapshot` (if cached from previous session) or `SkillEntry[]` (if freshly loaded)
**Output:** `string` — the XML prompt string to inject into the system prompt

```typescript
// workspace.ts:536–554
export function resolveSkillsPromptForRun(params): string {
  const snapshotPrompt = params.skillsSnapshot?.prompt?.trim();
  if (snapshotPrompt) {
    return snapshotPrompt;              // ← fast path: reuse cached XML from SkillSnapshot
  }
  if (params.entries && params.entries.length > 0) {
    const prompt = buildWorkspaceSkillsPrompt(params.workspaceDir, {
      entries: params.entries,          // ← slow path: re-run Steps 5–10
      config: params.config,
    });
    return prompt.trim() ? prompt : "";
  }
  return "";
}
```

If a `SkillSnapshot` exists with a cached `prompt` string, it's reused directly — no re-scanning, no re-parsing. Otherwise, the full chain (Steps 5–10) runs via `buildWorkspaceSkillsPrompt()`.

---

### Step 13: LLM Reads Skill on Demand (at inference time)

**No function** — this is decided by the LLM at inference time, not by OpenClaw code.

The system prompt now contains the XML from Step 10. When the user sends a message:
1. LLM scans `<available_skills>` descriptions to find a matching skill
2. LLM calls the `read` tool with the `<location>` path from the XML
3. LLM receives the **full** SKILL.md (frontmatter + body with instructions)
4. LLM follows those instructions (e.g., calls `exec` tool with a curl command)

Example:
```
User message:  "What's the weather in Tokyo?"

LLM sees in system prompt:
  <name>weather</name>
  <description>Get current weather and forecasts via wttr.in</description>
  <location>~/.openclaw/skills/weather/SKILL.md</location>

LLM calls: read({ path: "~/.openclaw/skills/weather/SKILL.md" })

LLM receives full file including body:
  # Weather Skill
  ## Commands
  curl "wttr.in/Tokyo?format=3"
  ...

LLM calls: exec({ command: "curl wttr.in/Tokyo?format=3" })

LLM responds: "Tokyo: ☀️ +22°C"
```

---

### Summary: Data Flow Table

```
Step  Function (file:lines)                         Input                        Output
───────────────────────────────────────────────────────────────────────────────────────────────────────
 1    loadSkillEntries (workspace.ts:324–335)        workspaceDir, config         6 directory paths
 2    loadSkills (workspace.ts:231–322)              directory path               Skill[]
      ├─ listChildDirectories (workspace.ts:150)     baseDir                      string[] (folder names)
      ├─ fs.existsSync + fs.statSync                 SKILL.md path                existence + size check
      └─ loadSkillsFromDir [external]                skillDir                     Skill (READ #1)
 3    merged.set (workspace.ts:369–388)              6 × Skill[]                  Map<string, Skill>
 4    Array.map (workspace.ts:390–404)               Map<string, Skill>           SkillEntry[]
      ├─ fs.readFileSync                             skill.filePath               raw string (READ #2)
      ├─ parseFrontmatter → parseFrontmatterBlock    raw string                   ParsedSkillFrontmatter
      ├─ resolveOpenClawMetadata                     frontmatter                  OpenClawSkillMetadata
      └─ resolveSkillInvocationPolicy                frontmatter                  SkillInvocationPolicy
 5    filterSkillEntries (workspace.ts:67–88)        SkillEntry[]                 SkillEntry[] (filtered)
      └─ shouldIncludeSkill (config.ts:70–112)       SkillEntry, config           boolean
 6    .filter (workspace.ts:466–468)                 SkillEntry[]                 SkillEntry[] (prompt-eligible)
 7    .map (workspace.ts:469)                        SkillEntry[]                 Skill[]
 8    applySkillsPromptLimits (workspace.ts:408)     Skill[]                      Skill[] (≤150, ≤30K chars)
 9    compactSkillPaths (workspace.ts:45–53)         Skill[]                      Skill[] (~/... paths)
10    formatSkillsForPrompt [external]               Skill[]                      string (XML)
11    return {...} (workspace.ts:488–497)            XML + entries                SkillSnapshot
12    resolveSkillsPromptForRun (workspace.ts:536)   SkillSnapshot | entries      string (XML for prompt)
13    (LLM at inference time)                        XML in system prompt         read tool call → exec
```

Key objects created along the way:
```
Skill                    → Step 2 output  (name, description, filePath, baseDir)
ParsedSkillFrontmatter   → Step 4 output  (Record<string, string> — raw frontmatter key-values)
OpenClawSkillMetadata    → Step 4 output  (requires, os, emoji, primaryEnv, install, always, skillKey)
SkillInvocationPolicy    → Step 4 output  (userInvocable, disableModelInvocation)
SkillEntry               → Step 4 output  (wraps Skill + frontmatter + metadata + invocation)
ResolvedSkillsLimits     → Step 2 config  (max counts and sizes for scanning + prompt generation)
SkillSnapshot            → Step 11 output (prompt XML + skill list + version — cached in sessions.json)
```

---

## Complete File Map

```
~/.openclaw/
├── config.yaml                              ← Master config (agents, channels, bindings, tokens)
│
├── workspace/                               ← Shared workspace (all agents by default)
│   ├── AGENTS.md                            ← Agent roster and descriptions
│   ├── SOUL.md                              ← Personality, behavior, boundaries
│   ├── TOOLS.md                             ← Environment notes (cameras, SSH, TTS)
│   ├── IDENTITY.md                          ← Name, emoji, avatar (cosmetic)
│   ├── USER.md                              ← Info about the human user
│   ├── HEARTBEAT.md                         ← Cron/heartbeat instructions
│   ├── BOOTSTRAP.md                         ← Custom bootstrap content (optional)
│   ├── MEMORY.md                            ← Agent persistent memory
│   └── skills/                              ← User-installed skills
│       ├── weather-1/SKILL.md
│       ├── find-skills/SKILL.md
│       └── tavily-search/SKILL.md
│
├── agents/                                  ← Per-agent state
│   ├── main/
│   │   └── sessions/
│   │       ├── sessions.json                ← Session index
│   │       ├── {uuid-1}.jsonl               ← Conversation transcript
│   │       └── {uuid-2}.jsonl
│   ├── jenny-manager/
│   │   └── sessions/
│   │       ├── sessions.json
│   │       └── {uuid}.jsonl
│   └── jack-3d-drafter/
│       └── sessions/
│           ├── sessions.json
│           └── {uuid}.jsonl
│
└── (optional per-agent workspaces)
    └── agents/jenny-manager/workspace/      ← Agent-specific overrides
        ├── SOUL.md                          ← Jenny's personality
        └── skills/
            └── project-management/SKILL.md  ← Jenny-only skill
```

### Source Code Map

```
src/
├── telegram/
│   ├── webhook.ts                           ← HTTP server for Telegram webhooks
│   └── bot-handlers.ts                      ← Message processing, debounce, requireMention
│
├── routing/
│   ├── resolve-route.ts                     ← 7-tier binding system
│   └── session-key.ts                       ← Session key construction
│
├── config/
│   ├── sessions/
│   │   ├── store.ts                         ← sessions.json management (load/save/prune/rotate)
│   │   └── paths.ts                         ← Session file path resolution
│   └── types.telegram.ts                    ← TelegramGroupConfig types
│
├── sessions/
│   └── session-key-utils.ts                 ← Key parsing, subagent depth, thread parent
│
├── agents/
│   ├── workspace.ts                         ← Bootstrap file loading + caching
│   ├── system-prompt.ts                     ← System prompt assembly
│   ├── bootstrap-files.ts                   ← Bootstrap context resolution
│   │
│   ├── skills/
│   │   └── workspace.ts                     ← Skill scanning, formatting, limits
│   │
│   ├── tools/
│   │   ├── sessions-spawn-tool.ts           ← Subagent spawning
│   │   ├── sessions-send-helpers.ts         ← Ping-pong exchange protocol
│   │   ├── sessions-list-tool.ts            ← List sessions
│   │   └── sessions-history-tool.ts         ← Read session history
│   │
│   ├── pi-embedded-runner/
│   │   ├── run/
│   │   │   └── attempt.ts                   ← THE main orchestrator (session → API → save)
│   │   └── compact.ts                       ← History compaction
│   │
│   └── pi-embedded-helpers/
│       └── bootstrap.ts                     ← File truncation and char budgets
│
└── acp/
    ├── client.ts                            ← ACP/MCP client connection
    └── translator.ts                        ← ACP gateway agent
```
