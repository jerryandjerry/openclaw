# Agent System Issues Report — 2026-04-06

## Critical: iMessage Echo Loop Bug

**Symptom**: Agent's outbound iMessage replies are picked up by the iMessage monitor and re-injected into the session as "user" messages, causing infinite feedback loops.

**Evidence**: 146 echoed messages found in session `8bf12887-67a5-4ba8-92bb-7f9b68223ebb.jsonl`. Agent sends "好👌" → monitor reads it from chat.db with `is_from_me = false` → injected as user message → agent responds → repeat.

**Root cause**: The `is_from_me` filter at `extensions/imessage/src/monitor/inbound-processing.ts:149` should drop agent-sent messages, but messages sent via the `imsg` RPC are not marked as `is_from_me = true` in the Messages database when the monitor reads them.

**Impact**:

- Floods Jerry's iMessage with dozens of "好👌" / "👌" echo replies
- Session bloated to 2000+ lines / 2.5MB
- Token waste: ~19M tokens burned in one day
- Gateway OOM crash after 63 hours (4GB heap exhausted)
- Agent acts on its own echoed messages (e.g. changed Note title without waiting for user confirmation)

**Screenshots**: IMG_3352 through IMG_3357 in this folder.

---

## Issue: Heartbeat GOOGL Bug (from 2026-03-22)

**Symptom**: Agent sends "GOOGL 到 300了" alert on Sunday even after HEARTBEAT.md was updated to say "weekends don't check."

**Root cause**: MiniMax M2.5 execution bug — model's thinking says "don't send, it's Sunday" but simultaneously emits a `message.send` tool call. The literal template text "GOOGL 到 300 了，可以看看要不要买" in HEARTBEAT.md acts as a trigger the model can't resist.

**Fix applied**: Removed GOOGL content from HEARTBEAT.md. Created dedicated cron jobs (`all-stocks-morning/noon/afternoon`) with `isolatedSession + lightContext` instead.

---

## Issue: Exec Permission Denial Loop

**Symptom**: Agent tried `exec("ls -la ~/.openclaw/")` → requires approval → approval can only be done in gateway UI, not via iMessage → agent kept retrying → infinite loop crashed gateway.

**Root cause**: `exec-approvals.json` had `security: "deny"` (default). Code at `src/node-host/invoke.ts:79` defaults to `"allowlist"` when `openclaw.json` doesn't set `tools.exec.security`, overriding `exec-approvals.json`.

**Fix applied**: Set `tools.exec.security: "full"` and `tools.exec.ask: "off"` in both `openclaw.json` (global + per-agent) and `exec-approvals.json`.

---

## Issue: Cron Job Timeouts

**Symptom**: Stock price cron jobs return "Request timed out before a response was generated" and deliver error messages to Jerry.

**Root cause**: `agents.defaults.timeoutSeconds` was set to 120s. Stock cron jobs used web search (slow) to get prices. Default timeout is 600s.

**Fix applied**:

- Removed 120s timeout override (back to 600s default)
- Created `~/.openclaw/workspace/stock_price.py` using `yfinance` — direct API call, no web search needed
- Updated cron job payloads to run the script via exec

---

## Issue: Cron Jobs Delivering to Wrong Target

**Symptom**: Stock price updates going to wrong number / "Not Delivered."

**Root cause**: Cron jobs had `"channel": "last"` — resolves to whatever channel was last used, not necessarily Jerry's iMessage.

**Fix applied**: Set explicit `"channel": "imessage", "to": "+8613288005530"` on all cron jobs.

---

## Issue: Leetcode Reminder Suppressed by Quiet Hours

**Symptom**: 11 PM leetcode cron fires, agent replies "🛌 安静时间👌" instead of relaying the reminder.

**Root cause**: Cron fires at exactly 23:00 (quiet hours start). Agent applies HEARTBEAT.md quiet hours rule to cron reminders.

**Fix applied**:

- Moved quiet hours to 00:00-08:00
- Updated HEARTBEAT.md to exempt cron/scheduled reminders from quiet hours
- Moved leetcode cron to 22:30

---

## Issue: GPT-5.4 Fallback Causing Duplicate Message Injection

**Symptom**: Every inbound message appears twice in the session — first attempt returns empty `[]`, then the same message is re-injected.

**Root cause**: Model config was `{"primary": "openai-codex/gpt-5.4", "fallbacks": ["minimax-portal/MiniMax-M2.5"]}`. GPT-5.4 had hit usage limit, returned error + empty response. System enqueued followup run, MiniMax M2.5 handled the retry. Each message logged twice.

**Fix applied**: Changed model config to `"minimax-portal/MiniMax-M2.5"` directly (no primary/fallback).

---

## Configuration Changes Applied

| File                                   | Change                                                                      |
| -------------------------------------- | --------------------------------------------------------------------------- |
| `~/.openclaw/openclaw.json`            | `agents.defaults.model` → `"minimax-portal/MiniMax-M2.5"`                   |
| `~/.openclaw/openclaw.json`            | `tools.exec.security` → `"full"`, `tools.exec.ask` → `"off"`                |
| `~/.openclaw/openclaw.json`            | Removed `agents.defaults.timeoutSeconds: 120`                               |
| `~/.openclaw/exec-approvals.json`      | `defaults/agents.*/agents.main` all set to `security: "full"`, `ask: "off"` |
| `~/.openclaw/workspace/HEARTBEAT.md`   | Removed GOOGL content, quiet hours 00:00-08:00, cron reminders exempt       |
| `~/.openclaw/workspace/stock_price.py` | New script using yfinance with portfolio cost basis                         |
| `~/.openclaw/cron/jobs.json`           | All stock/leetcode jobs: explicit iMessage delivery, script-based payload   |

## Critical: Phantom "User" Messages — Three Sources

All three inject messages into the main session as `role: "user"` with Jerry's sender metadata, causing the agent to respond unprompted.

### Source 1: Agent echo loop (146 instances)

Agent sends reply via iMessage → iMessage monitor reads it from chat.db with `is_from_me = false` → re-injected as user message → agent responds → repeat.

### Source 2: Cron error notifications

Cron job fails (e.g. phone-drawer-730 timeout) → error message wrapped with Jerry's sender metadata → injected as user message → agent responds "刚才超时了，有什么事？" → delivered to Jerry's iMessage.

### Source 3: Cron timeout/system events

System events like "Request timed out before a response was generated" are injected as user messages with Jerry's number, triggering agent replies.

**All three should never appear as user messages.** Agent echoes should be filtered by `is_from_me`. System events and cron errors should be logged internally, not routed through the user message pipeline.

---

## Session Files Referenced

- `34abd4a6-d7ec-447f-b3b4-10f3363b94c2.jsonl` — 2026-03-22 session (GOOGL heartbeat bug)
- `8bf12887-67a5-4ba8-92bb-7f9b68223ebb.jsonl` — 2026-04-01 to 04-06 session (echo loop, exec denial, OOM crash)
