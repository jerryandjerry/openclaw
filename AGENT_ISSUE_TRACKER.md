# Agent Workflow Issues Tracker

## Root Cause Analysis (2026-03-18)

**All core issues (#1–#5) share the same fundamental root cause: LLM instruction-following reliability.**

The agents have every tool, config, and piece of information they need:
- `image_generate` is a built-in tool available to all agents (`src/agents/tool-catalog.ts:237`)
- Discord mention IDs are already in each agent's TOOLS.md with correct `<@id>` format
- HEARTBEAT.md instructions are in SOUL.md
- The 17-step workflow is documented

The LLM simply doesn't follow instructions 100% of the time. No prompt engineering, hook system, or injection mechanism can guarantee compliance. This is a known limitation of current LLMs.

**What actually helps (ranked by effectiveness):**
1. **Better/smarter model** — instruction following scales with model capability
2. **Shorter prompts** — less noise = fewer competing instructions = higher compliance rate
3. **Few-shot examples** — show the exact tool call / output format instead of describing it in words
4. **Lower temperature** — more deterministic = more predictable behavior
5. **Repetition at prompt boundaries** — instructions at the very top AND very bottom of system prompt get more attention than the middle

**What does NOT help:**
- Prompt injection via hooks (`before_prompt_build`) — adding more text to an already long prompt makes compliance worse, not better
- Blocking tool calls (`before_tool_call`) — the LLM already made its decision; blocking creates confusing errors
- Regex rewriting of output (`message_sending`) — brittle; can't anticipate all variations the LLM produces
- Adding more detailed instructions — longer instructions get diluted during context compaction

---

## Open Issues

### 1. Agents don't reliably write TODO to HEARTBEAT.md before actions
- **Date identified:** 2026-03-17
- **Affected agents:** All (most noticeable: Manager, 2D Drafter)
- **Root cause:** LLM instruction-following reliability. Instructions compete with task context for the LLM's attention. No architectural enforcement exists — nothing in the runner prevents the LLM from replying without writing HEARTBEAT.md first.
- **Evidence:** Session logs show agents skip HEARTBEAT.md writes on most turns, or only write sporadically
- **What could work:**
  - [ ] Shorten SOUL.md so HEARTBEAT rules aren't buried in noise
  - [ ] Add a few-shot example showing the exact `write_file` call for HEARTBEAT.md
  - [ ] Move HEARTBEAT rules to the very first and very last lines of SOUL.md (primacy + recency effect)
- **What won't work:** Injecting more instructions via hooks (adds prompt length, makes it worse)

### 2. Agents don't clear finished tasks from HEARTBEAT.md
- **Date identified:** 2026-03-17
- **Affected agents:** 2D Drafter (Jade), others likely
- **Root cause:** LLM defaults to familiar markdown patterns. Marking `[x]` is a common pattern in training data; deleting lines is not. The LLM does what "feels natural" over what's instructed.
- **Evidence:** Jade's session `98ff4a6d` shows HEARTBEAT.md filled with `[x]` completed items never removed
- **What could work:**
  - [ ] Change instruction wording: "DELETE the completed line entirely. Do NOT mark [x]. The file must only contain active tasks."
  - [ ] Add a few-shot example showing a before/after of HEARTBEAT.md with a line removed
- **What won't work:** `after_tool_call` hook validation (fires after the write is done; would need to trigger a corrective write, adding complexity)

### 3. Agents mention wrong people in Discord
- **Date identified:** 2026-03-17
- **Affected agents:** 2D Drafter (Jade), others likely
- **Root cause:** LLM instruction-following. The Discord mention ID table is already in each agent's TOOLS.md with the correct `<@id>` format. The LLM has the data but "corrects" the unfamiliar `<@123456789>` syntax to human-readable `@Jacob_Director` because that looks more "natural."
- **Evidence:** Jade's session shows `@Jacob_Director` plain text instead of `<@1481692218249973893>` Discord mention format, despite the ID table being in TOOLS.md
- **Existing system:** Discord extension already has `rewritePlainTextMentions()` (`extensions/discord/src/mentions.ts`) with a directory cache (`extensions/discord/src/directory-cache.ts`). This should catch `@handle` → `<@id>` rewrites if the cache has the bot users.
- **What could work:**
  - [ ] Verify the Discord directory cache includes all agent bot users (if not, the existing rewrite system can't help)
  - [ ] Shorten the mention table and put it at the top of TOOLS.md with a bold warning
  - [ ] Add a few-shot example: `To notify Jacob, write: <@1481692218249973893>`
- **What won't work:** Regex-based `message_sending` hook (can't anticipate "Jacob", "jacob_director", "the director", "@Jacob", etc.)

### 4. Agents don't reliably follow their workflow (wrong tools)
- **Date identified:** 2026-03-17
- **Affected agents:** 2D Drafter (Jade) — produces SVG code instead of using `image_generate` built-in tool
- **Root cause:** LLM instruction-following. The `image_generate` tool IS available to all agents (built-in, `src/agents/tool-catalog.ts:237`). OpenAI image generation API key is configured. The LLM chooses to write SVG via `write_file` because SVG generation is deeply embedded in its training data and feels "easier" than calling an unfamiliar tool.
- **Evidence:** Jade's session shows SVG markup written via `write_file` instead of calling `image_generate`
- **What could work:**
  - [ ] Add explicit instruction in TOOLS.md: "For any visual output, ALWAYS use the `image_generate` tool. NEVER write SVG, HTML canvas, or any markup to produce images."
  - [ ] Add a few-shot example showing the exact `image_generate` tool call with prompt
  - [ ] Shorter SOUL.md so tool-use instructions have more weight
- **What won't work:** Removing `write_file` (breaks everything else); `before_tool_call` hook blocking SVG content (LLM already committed to the approach; blocking just creates a confusing retry loop)

### 5. Manager doesn't follow project lifecycle reliably
- **Date identified:** 2026-03-17
- **Affected agents:** Manager
- **Root cause:** LLM instruction-following with long prompts. The 17-step workflow in SOUL.md exceeds what the LLM can reliably retain and follow. Steps get skipped, reordered, or compressed. Context compaction further dilutes the instructions over long sessions.
- **Evidence:** Manager skips project initialization steps (doesn't copy full project structure), sometimes does closeout without approval, sometimes skips closeout entirely
- **What could work:**
  - [ ] Compress the 17-step workflow to 5-7 critical rules in SOUL.md
  - [ ] Move the full detailed workflow to a separate file the manager reads on demand (reduces system prompt length)
  - [ ] Add explicit stop-gates: "STOP. Do NOT proceed past this step without user confirmation."
  - [ ] Break the workflow into phases — only load the current phase's instructions
- **What won't work:** Adding more detail to the workflow (longer = worse compliance)

### 6. Jacob (Director) not responding to Discord messages
- **Date identified:** 2026-03-17
- **Affected agents:** Jacob (Director)
- **Root cause:** API rate limit errors on every LLM call attempt; MiniMax M2.5 fallback configured but gateway not yet restarted to apply changes
- **Evidence:** Session logs show rate limit errors on all attempts
- **Fix plan:**
  - [ ] Restart gateway to apply MiniMax M2.5 fallback config
  - [ ] Verify Jacob responds after restart

---

## Fix Priority

| Priority | Action | Effort | Expected Impact |
|----------|--------|--------|-----------------|
| 1 | Restart gateway (#6) | 5 min | Jacob comes back online — only issue with a guaranteed fix |
| 2 | Verify Discord directory cache has agent bots (#3) | 15 min | If cached, existing `rewritePlainTextMentions()` already fixes mentions |
| 3 | Shorten SOUL.md for all agents (#1, #2, #4, #5) | 1 hr | Statistically improves all instruction-following (biggest single lever) |
| 4 | Add few-shot examples to TOOLS.md (#1, #2, #3, #4) | 30 min | Shows exact expected behavior instead of describing it |
| 5 | Split manager workflow into phases (#5) | 1 hr | Reduces active instruction set per phase |
| 6 | Upgrade to better model when available (#1-#5) | — | Fundamentally improves instruction-following across all issues |

---

## Key Insight

The gap between "the agent has the right information" and "the agent does the right thing" is the core challenge of LLM-based multi-agent systems. Current mitigations are statistical (shorter prompts, better models, few-shot examples), not deterministic. True enforcement would require architectural changes to the runner (e.g., mandatory tool-call verification before allowing a response), which is a significant engineering effort.

---

## Resolved Issues

(none yet)
