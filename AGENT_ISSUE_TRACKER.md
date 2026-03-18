# Agent Workflow Issues Tracker

## Open Issues

### 1. Agents don't reliably write TODO to HEARTBEAT.md before actions
- **Date identified:** 2026-03-17
- **Affected agents:** All (most noticeable: Manager, 2D Drafter)
- **Root cause:** HEARTBEAT.md instructions buried in long SOUL.md; LLM deprioritizes mid-prompt instructions
- **Evidence:** Session logs show agents skip HEARTBEAT.md writes on most turns, or only write sporadically
- **Fix plan:**
  - [ ] Move HEARTBEAT.md rules to the TOP of SOUL.md (3 lines max)
  - [ ] Consider `before_prompt_build` plugin hook to inject mandatory HEARTBEAT instructions into every agent's system prompt

### 2. Agents don't clear finished tasks from HEARTBEAT.md
- **Date identified:** 2026-03-17
- **Affected agents:** 2D Drafter (Jade), others likely
- **Root cause:** LLM marks tasks `[x]` instead of deleting the line; system prompt grows unbounded
- **Evidence:** Jade's session `98ff4a6d` shows HEARTBEAT.md filled with `[x]` completed items never removed
- **Fix plan:**
  - [ ] Change instruction from "update status" to explicit "DELETE the completed line from HEARTBEAT.md (do NOT mark [x])"
  - [ ] Consider `after_tool_call` plugin hook to validate HEARTBEAT.md writes don't contain `[x]` items

### 3. Agents mention wrong people in Discord
- **Date identified:** 2026-03-17
- **Affected agents:** 2D Drafter (Jade), others likely
- **Root cause:** LLM "corrects" Discord mention syntax `<@botId>` to human-readable `@Jacob_Director` plain text, which Discord doesn't recognize as a mention
- **Evidence:** Jade's session shows `@Jacob_Director` plain text instead of `<@botId>` Discord mention format
- **Fix plan:**
  - [ ] Add Discord mention ID lookup table to each agent's TOOLS.md with explicit "NEVER write @Name" instruction
  - [ ] Build `message_sending` plugin hook to auto-rewrite plain-text mentions to `<@id>` format before delivery (catches errors LLM will keep making)

### 4. Agents don't reliably follow their workflow (wrong tools)
- **Date identified:** 2026-03-17
- **Affected agents:** 2D Drafter (Jade) — produces SVG code instead of using image generation tools
- **Root cause:** TOOLS.md lacks tool-specific guidance per role; SOUL.md workflow too long for LLM to retain fully
- **Evidence:** Jade's session shows SVG markup output instead of calling nano_banana or other image generation tools
- **Fix plan:**
  - [ ] Add explicit tool instructions per role in TOOLS.md (e.g., "ALWAYS use nano_banana for images. NEVER produce SVG code.")
  - [ ] Shorten SOUL.md — compress manager's 17-step workflow to essential rules
  - [ ] Consider `before_tool_call` plugin hook to block SVG-producing writes for the drafter role

### 5. Manager doesn't follow project lifecycle reliably
- **Date identified:** 2026-03-17
- **Affected agents:** Manager
- **Root cause:** 17-step workflow in SOUL.md is too long; instructions get diluted during context compaction
- **Evidence:** Manager skips project initialization steps (doesn't copy full project structure), sometimes does closeout without approval, sometimes skips closeout entirely
- **Fix plan:**
  - [ ] Shorten SOUL.md to critical rules only
  - [ ] Move the full 17-step workflow to a separate reference file the manager can read on demand
  - [ ] Add phase-gate checkpoints: "STOP and confirm with user before proceeding to next phase"

### 6. Jacob (Director) not responding to Discord messages
- **Date identified:** 2026-03-17
- **Affected agents:** Jacob (Director)
- **Root cause:** API rate limit errors on every LLM call attempt; fallback to MiniMax M2.5 not yet active
- **Evidence:** Session logs show rate limit errors; gateway config updated but not yet restarted
- **Fix plan:**
  - [ ] Restart gateway to apply MiniMax M2.5 fallback config
  - [ ] Verify Jacob responds after restart

---

## Fix Priority

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Restart gateway (fixes #6) | 5 min | Jacob comes back online |
| 2 | Add Discord mention ID table to TOOLS.md (#3) | 15 min | Correct @mentions |
| 3 | Move HEARTBEAT rules to top of SOUL.md (#1, #2) | 15 min | Better task tracking |
| 4 | Add tool guidance per role in TOOLS.md (#4) | 15 min | Correct tool usage |
| 5 | Shorten manager SOUL.md (#5) | 30 min | Better workflow compliance |
| 6 | Build `message_sending` plugin hook (#3) | 1-2 hrs | Auto-fix mentions permanently |
| 7 | Build `before_tool_call` plugin hook (#4) | 1-2 hrs | Block wrong tool usage |
| 8 | Build `before_prompt_build` plugin hook (#1) | 1-2 hrs | Enforce HEARTBEAT across all agents |

---

## Resolved Issues

(none yet)
