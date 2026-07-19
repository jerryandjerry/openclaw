#!/usr/bin/env python3
"""Render an openclaw session JSONL file as a readable HTML page."""

import json
import html
import sys
import os
from datetime import datetime, timezone

def ts_to_local(ts_str):
    """Convert ISO timestamp to local time string."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%H:%M:%S")
    except:
        return ts_str[:19]

def escape(text):
    return html.escape(str(text)) if text else ""

def render_meta_badges(msg):
    """Render metadata badges for a message (model, usage, errors, etc.)."""
    badges = []
    provider = msg.get("provider", "")
    model = msg.get("model", "")
    api = msg.get("api", "")
    stop = msg.get("stopReason", "")
    error = msg.get("errorMessage", "")
    usage = msg.get("usage", {})

    if provider or model:
        badges.append(f'<span class="badge badge-model">{escape(provider)}/{escape(model)}</span>')
    if api:
        badges.append(f'<span class="badge badge-api">{escape(api)}</span>')
    if stop:
        cls = "badge-error" if stop == "error" else "badge-stop"
        badges.append(f'<span class="badge {cls}">stop: {escape(stop)}</span>')
    if error:
        badges.append(f'<span class="badge badge-error">{escape(error)}</span>')
    if usage:
        total = usage.get("totalTokens", 0)
        inp = usage.get("input", 0)
        out = usage.get("output", 0)
        cache_r = usage.get("cacheRead", 0)
        cache_w = usage.get("cacheWrite", 0)
        cost = usage.get("cost", {}).get("total", 0)
        if total > 0:
            parts = [f"total={total}"]
            if inp: parts.append(f"in={inp}")
            if out: parts.append(f"out={out}")
            if cache_r: parts.append(f"cacheR={cache_r}")
            if cache_w: parts.append(f"cacheW={cache_w}")
            if cost: parts.append(f"cost=${cost:.4f}")
            badges.append(f'<span class="badge badge-usage">{" ".join(parts)}</span>')
    return " ".join(badges)

def render_tool_result_meta(msg):
    """Render toolResult metadata badges."""
    badges = []
    tool_name = msg.get("toolName", "")
    tool_call_id = msg.get("toolCallId", "")
    is_error = msg.get("isError", False)
    details = msg.get("details", {})

    if tool_name:
        badges.append(f'<span class="badge badge-tool">{escape(tool_name)}</span>')
    if tool_call_id:
        badges.append(f'<span class="badge badge-id">{escape(tool_call_id[:20])}</span>')
    if is_error:
        badges.append(f'<span class="badge badge-error">ERROR</span>')

    # Show relevant details
    if isinstance(details, dict):
        for key in ["query", "provider", "tookMs", "count", "channel", "to", "status", "error"]:
            val = details.get(key)
            if val is not None:
                badges.append(f'<span class="badge badge-detail">{escape(key)}={escape(str(val)[:80])}</span>')

    return " ".join(badges)

def render_content(content):
    """Render message content blocks to HTML."""
    if not content or content == []:
        return '<span class="empty">(empty)</span>'
    if isinstance(content, str):
        return f'<div class="text-block">{escape(content)}</div>'
    if not isinstance(content, list):
        return f'<pre>{escape(json.dumps(content, ensure_ascii=False, indent=2))}</pre>'

    parts = []
    for block in content:
        btype = block.get("type", "")

        if btype == "thinking":
            thinking = block.get("thinking", "")
            parts.append(f'<details class="thinking"><summary>Thinking ({len(thinking)} chars)</summary><pre>{escape(thinking)}</pre></details>')

        elif btype == "text":
            text = block.get("text", "")
            # Highlight GOOGL alert text
            extra_cls = " alert-text" if "GOOGL" in text and "300" in text and len(text) < 100 else ""
            parts.append(f'<div class="text-block{extra_cls}">{escape(text)}</div>')

        elif btype == "toolCall":
            name = block.get("name", "?")
            call_id = block.get("id", "")
            args = block.get("arguments", {})
            args_str = json.dumps(args, ensure_ascii=False, indent=2)
            is_message_send = name == "message" and args.get("action") == "send"
            border_cls = " message-send" if is_message_send else ""
            parts.append(
                f'<div class="tool-call{border_cls}">'
                f'<span class="tool-label">Tool Call: <b>{escape(name)}</b></span>'
                f'{f" <span class=badge-id>{escape(call_id[:20])}</span>" if call_id else ""}'
                f'<pre>{escape(args_str)}</pre>'
                f'</div>'
            )

        else:
            parts.append(f'<div class="unknown-block"><span class="tool-label">{escape(btype)}</span><pre>{escape(json.dumps(block, ensure_ascii=False)[:1000])}</pre></div>')

    return "\n".join(parts)

def render_app():
    """Generate a standalone HTML app with drag-and-drop support."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>OpenClaw Session Viewer</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }
h1 { color: #58a6ff; margin-bottom: 10px; font-size: 16px; }
h2 { color: #8b949e; margin-bottom: 20px; font-size: 13px; font-weight: normal; }

#drop-zone {
  border: 2px dashed #30363d; border-radius: 12px; padding: 60px 40px;
  text-align: center; color: #8b949e; font-size: 15px; margin: 40px auto;
  max-width: 600px; transition: all 0.2s;
}
#drop-zone.drag-over { border-color: #58a6ff; background: #0d2240; color: #58a6ff; }
#drop-zone p { margin: 8px 0; }
#drop-zone .hint { font-size: 12px; color: #484f58; }
#file-input { display: none; }
#drop-zone .browse { color: #58a6ff; cursor: pointer; text-decoration: underline; }

#viewer { display: none; }
#back-btn {
  background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
  padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 12px;
  margin-bottom: 12px;
}
#back-btn:hover { background: #30363d; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
tr { border-bottom: 1px solid #21262d; vertical-align: top; }
td { padding: 8px 10px; }
th { padding: 8px 10px; text-align: left; color: #8b949e; font-size: 11px; border-bottom: 2px solid #21262d; }
.ln { color: #484f58; width: 40px; text-align: right; font-size: 11px; user-select: none; }
.time { color: #8b949e; width: 70px; font-size: 11px; white-space: nowrap; }
.role { width: 100px; font-size: 11px; font-weight: bold; white-space: nowrap; }

.row-user td { background: #0d2240; }
.row-user .role { color: #58a6ff; }
.row-user.heartbeat td { background: #1a1a0d; }
.row-user.heartbeat .role { color: #d29922; }
.row-user.system-event td { background: #1a1520; }
.row-user.system-event .role { color: #bc8cff; }

.row-assistant td { background: #0d1117; }
.row-assistant .role { color: #3fb950; }

.row-tool-result td { background: #161b22; }
.row-tool-result .role { color: #bc8cff; }

.row-model td { background: #1a1220; }
.row-model .role { color: #bc8cff; }

.row-session td { background: #1a2a1a; text-align: center; color: #3fb950; font-weight: bold; }
.row-meta td { background: #161b22; color: #484f58; }
.row-meta .role { color: #484f58; }
.row-error td { background: #2a1010; }
.row-error .role { color: #f85149; }

.meta-line { margin-bottom: 4px; }

.text-block { white-space: pre-wrap; word-break: break-word; padding: 4px 0; line-height: 1.5; }
.text-block.alert-text { color: #f85149; font-weight: bold; background: #2a1010; padding: 4px 8px; border-radius: 4px; }
.empty { color: #484f58; font-style: italic; }

details.thinking { margin: 4px 0; }
details.thinking summary { cursor: pointer; color: #d29922; font-size: 12px; padding: 2px 0; }
details.thinking pre { color: #8b949e; font-size: 12px; padding: 8px; margin-top: 4px; background: #0d1117; border-radius: 4px; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; }

.tool-call { margin: 4px 0; padding: 6px 10px; background: #1a1a2e; border-left: 3px solid #58a6ff; border-radius: 4px; }
.tool-call.message-send { border-left-color: #f85149; background: #2a1a1a; }
.tool-call .tool-label { color: #58a6ff; font-size: 12px; }
.tool-call.message-send .tool-label { color: #f85149; }
.tool-call pre { font-size: 12px; color: #c9d1d9; margin-top: 4px; white-space: pre-wrap; word-break: break-word; }

.tool-result { margin: 4px 0; padding: 6px 10px; background: #1a1a2e; border-left: 3px solid #bc8cff; border-radius: 4px; }
.tool-result .tool-label { color: #bc8cff; font-size: 12px; }
.tool-result pre { font-size: 12px; color: #8b949e; margin-top: 4px; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; }

pre { font-family: "SF Mono", "Fira Code", monospace; }

.badge { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px; margin: 1px 2px; vertical-align: middle; }
.badge-model { background: #1f2a3a; color: #58a6ff; border: 1px solid #30363d; }
.badge-api { background: #1a1a2e; color: #bc8cff; border: 1px solid #30363d; }
.badge-stop { background: #1a2a1a; color: #3fb950; border: 1px solid #30363d; }
.badge-error { background: #2a1010; color: #f85149; border: 1px solid #f8514966; }
.badge-usage { background: #161b22; color: #8b949e; border: 1px solid #30363d; }
.badge-tool { background: #1a1a2e; color: #bc8cff; border: 1px solid #30363d; font-weight: bold; }
.badge-id { color: #484f58; font-size: 9px; }
.badge-detail { background: #161b22; color: #8b949e; border: 1px solid #21262d; }
</style>
</head>
<body>

<div id="drop-zone">
  <p>Drop a <b>.jsonl</b> session file here</p>
  <p>or <span class="browse" onclick="document.getElementById('file-input').click()">browse</span></p>
  <p class="hint">~/.openclaw/agents/main/sessions/*.jsonl</p>
  <input type="file" id="file-input" accept=".jsonl,.jsonl.reset">
</div>

<div id="viewer">
  <button id="back-btn" onclick="showDrop()">Drop another file</button>
  <h1>Session Viewer</h1>
  <h2 id="session-title"></h2>
  <table>
    <thead><tr><th class="ln">#</th><th class="time">Time</th><th class="role">Role</th><th>Content</th></tr></thead>
    <tbody id="session-body"></tbody>
  </table>
</div>

<script>
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const viewer = document.getElementById('viewer');
const tbody = document.getElementById('session-body');
const title = document.getElementById('session-title');

function showDrop() { dropZone.style.display = ''; viewer.style.display = 'none'; }

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) loadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) loadFile(fileInput.files[0]); });

function loadFile(file) {
  const reader = new FileReader();
  reader.onload = () => renderSession(file.name, reader.result);
  reader.readAsText(file);
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function tsLocal(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleTimeString('en-US', {hour12:false}); } catch { return ts.slice(11,19); }
}

function badge(cls, text) { return '<span class="badge badge-' + cls + '">' + esc(text) + '</span>'; }

function renderMeta(msg) {
  let b = [];
  if (msg.provider || msg.model) b.push(badge('model', (msg.provider||'') + '/' + (msg.model||'')));
  if (msg.api) b.push(badge('api', msg.api));
  if (msg.stopReason) b.push(badge(msg.stopReason === 'error' ? 'error' : 'stop', 'stop: ' + msg.stopReason));
  if (msg.errorMessage) b.push(badge('error', msg.errorMessage));
  const u = msg.usage;
  if (u && u.totalTokens > 0) {
    let p = ['total=' + u.totalTokens];
    if (u.input) p.push('in=' + u.input);
    if (u.output) p.push('out=' + u.output);
    if (u.cacheRead) p.push('cacheR=' + u.cacheRead);
    if (u.cacheWrite) p.push('cacheW=' + u.cacheWrite);
    b.push(badge('usage', p.join(' ')));
  }
  return b.join(' ');
}

function renderToolMeta(msg) {
  let b = [];
  if (msg.toolName) b.push(badge('tool', msg.toolName));
  if (msg.toolCallId) b.push('<span class="badge-id">' + esc(msg.toolCallId.slice(0,20)) + '</span>');
  if (msg.isError) b.push(badge('error', 'ERROR'));
  const d = msg.details;
  if (d && typeof d === 'object') {
    for (const k of ['query','provider','tookMs','count','channel','to','status','error']) {
      if (d[k] !== undefined) b.push(badge('detail', k + '=' + String(d[k]).slice(0,80)));
    }
  }
  return b.join(' ');
}

function renderContent(content) {
  if (!content || (Array.isArray(content) && content.length === 0)) return '<span class="empty">(empty)</span>';
  if (typeof content === 'string') return '<div class="text-block">' + esc(content) + '</div>';
  if (!Array.isArray(content)) return '<pre>' + esc(JSON.stringify(content, null, 2)) + '</pre>';

  return content.map(block => {
    const t = block.type || '';
    if (t === 'thinking') {
      const th = block.thinking || '';
      return '<details class="thinking"><summary>Thinking (' + th.length + ' chars)</summary><pre>' + esc(th) + '</pre></details>';
    }
    if (t === 'text') {
      const txt = block.text || '';
      const isAlert = txt.includes('GOOGL') && txt.includes('300') && txt.length < 100;
      return '<div class="text-block' + (isAlert ? ' alert-text' : '') + '">' + esc(txt) + '</div>';
    }
    if (t === 'toolCall') {
      const name = block.name || '?';
      const args = JSON.stringify(block.arguments || {}, null, 2);
      const isSend = name === 'message' && block.arguments && block.arguments.action === 'send';
      return '<div class="tool-call' + (isSend ? ' message-send' : '') + '">' +
        '<span class="tool-label">Tool Call: <b>' + esc(name) + '</b></span>' +
        (block.id ? ' <span class="badge-id">' + esc(block.id.slice(0,20)) + '</span>' : '') +
        '<pre>' + esc(args) + '</pre></div>';
    }
    return '<div class="unknown-block"><span class="tool-label">' + esc(t) + '</span><pre>' + esc(JSON.stringify(block).slice(0,1000)) + '</pre></div>';
  }).join('\\n');
}

function renderSession(filename, text) {
  const lines = text.trim().split('\\n');
  const entries = [];
  for (let i = 0; i < lines.length; i++) {
    try { entries.push([i + 1, JSON.parse(lines[i])]); } catch {}
  }

  title.textContent = filename + ' — ' + entries.length + ' entries';
  let html = '';

  for (const [ln, obj] of entries) {
    const ts = obj.timestamp || '';
    const time = tsLocal(ts);
    const etype = obj.type || '';
    const msg = obj.message || {};
    const role = msg.role || '';
    const content = msg.content;

    if (etype === 'session') {
      html += '<tr class="row-session"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td colspan="2" class="session-start">Session Start ' +
        badge('detail', 'id=' + (obj.id||'').slice(0,12)) + ' ' + badge('detail', 'v' + (obj.version||'')) + ' ' + badge('detail', 'cwd=' + (obj.cwd||'')) + '</td></tr>';
      continue;
    }
    if (etype === 'model_change') {
      html += '<tr class="row-meta"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">system</td><td>Model change: <b>' + esc((obj.provider||'') + '/' + (obj.modelId||'')) + '</b></td></tr>';
      continue;
    }
    if (etype === 'thinking_level_change') {
      html += '<tr class="row-meta"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">system</td><td>Thinking level: <b>' + esc(obj.thinkingLevel||'') + '</b></td></tr>';
      continue;
    }
    if (etype === 'custom') {
      const ct = obj.customType || '';
      const data = obj.data || {};
      if (ct === 'model-snapshot') {
        html += '<tr class="row-model"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">model</td><td>Model: <b>' + esc((data.provider||'') + '/' + (data.modelId||'')) + '</b> ' + badge('api', data.modelApi||'') + '</td></tr>';
      } else if (ct === 'openclaw:prompt-error') {
        html += '<tr class="row-error"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">error</td><td>Prompt error: <pre>' + esc(JSON.stringify(data).slice(0,500)) + '</pre></td></tr>';
      } else {
        html += '<tr class="row-meta"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">custom</td><td>' + esc(ct || '(event)') + '</td></tr>';
      }
      continue;
    }
    if (etype !== 'message') {
      html += '<tr class="row-meta"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">' + esc(etype) + '</td><td><pre>' + esc(JSON.stringify(obj).slice(0,500)) + '</pre></td></tr>';
      continue;
    }

    const meta = renderMeta(msg);
    const rendered = renderContent(content);

    if (role === 'user') {
      const preview = JSON.stringify(content || '').slice(0, 200);
      const isHb = preview.includes('HEARTBEAT');
      const isQ = preview.includes('[Queued messages');
      const isSys = preview.includes('System:');
      let cls = 'row-user', label = 'user';
      if (isHb) { cls += ' heartbeat'; label = 'heartbeat'; }
      else if (isQ) { cls += ' queued'; label = 'user (queued)'; }
      else if (isSys) { cls += ' system-event'; label = 'system event'; }
      html += '<tr class="' + cls + '"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">' + label + '</td><td>' + (meta ? meta + '<br>' : '') + rendered + '</td></tr>';
    } else if (role === 'assistant') {
      html += '<tr class="row-assistant"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">assistant</td><td><div class="meta-line">' + meta + '</div>' + rendered + '</td></tr>';
    } else if (role === 'toolResult') {
      const tmeta = renderToolMeta(msg);
      html += '<tr class="row-tool-result"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">toolResult</td><td><div class="meta-line">' + tmeta + '</div>' + rendered + '</td></tr>';
    } else {
      html += '<tr class="row-other"><td class="ln">' + ln + '</td><td class="time">' + time + '</td><td class="role">' + esc(role || etype) + '</td><td>' + (meta ? meta + '<br>' : '') + rendered + '</td></tr>';
    }
  }

  tbody.innerHTML = html;
  dropZone.style.display = 'none';
  viewer.style.display = '';
  window.scrollTo(0, 0);
}
</script>
</body>
</html>"""

def render_session(jsonl_path):
    with open(jsonl_path) as f:
        lines = f.readlines()

    entries = []
    for i, line in enumerate(lines):
        try:
            entries.append((i + 1, json.loads(line)))
        except:
            pass

    session_name = os.path.basename(jsonl_path)
    rows = []

    for line_num, obj in entries:
        ts = obj.get("timestamp", "")
        etype = obj.get("type", "")
        msg = obj.get("message", {})
        role = msg.get("role", "")
        content = msg.get("content", "")

        time_str = ts_to_local(ts)

        if etype == "session":
            ver = obj.get("version", "")
            sid = obj.get("id", "")
            cwd = obj.get("cwd", "")
            rows.append(f'<tr class="row-session"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td colspan="2" class="session-start">Session Start <span class="badge badge-detail">id={escape(sid[:12])}</span> <span class="badge badge-detail">v{ver}</span> <span class="badge badge-detail">cwd={escape(cwd)}</span></td></tr>')
            continue

        if etype == "model_change":
            provider = obj.get("provider", "")
            model_id = obj.get("modelId", "")
            rows.append(f'<tr class="row-meta"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">system</td><td>Model change: <b>{escape(provider)}/{escape(model_id)}</b></td></tr>')
            continue

        if etype == "thinking_level_change":
            level = obj.get("thinkingLevel", "")
            rows.append(f'<tr class="row-meta"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">system</td><td>Thinking level: <b>{escape(level)}</b></td></tr>')
            continue

        if etype == "custom":
            ct = obj.get("customType", "")
            data = obj.get("data", {})
            if ct == "model-snapshot":
                model_id = data.get("modelId", "")
                provider = data.get("provider", "")
                model_api = data.get("modelApi", "")
                rows.append(f'<tr class="row-model"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">model</td><td>Model: <b>{escape(provider)}/{escape(model_id)}</b> <span class="badge badge-api">{escape(model_api)}</span></td></tr>')
            elif ct == "openclaw:prompt-error":
                rows.append(f'<tr class="row-error"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">error</td><td>Prompt error: <pre>{escape(json.dumps(data, ensure_ascii=False)[:500])}</pre></td></tr>')
            else:
                rows.append(f'<tr class="row-meta"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">custom</td><td>{escape(ct) or "(event)"} <pre>{escape(json.dumps(data, ensure_ascii=False)[:300])}</pre></td></tr>')
            continue

        if etype != "message":
            rows.append(f'<tr class="row-meta"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">{escape(etype)}</td><td><pre>{escape(json.dumps(obj, ensure_ascii=False)[:500])}</pre></td></tr>')
            continue

        # Messages
        meta = render_meta_badges(msg)

        if role == "user":
            rendered = render_content(content)
            text_preview = json.dumps(content, ensure_ascii=False)[:200] if content else ""
            is_heartbeat = "HEARTBEAT" in text_preview
            is_queued = "[Queued messages" in text_preview
            is_system = "System:" in text_preview
            if is_heartbeat:
                extra_class, label = " heartbeat", "heartbeat"
            elif is_queued:
                extra_class, label = " queued", "user (queued)"
            elif is_system:
                extra_class, label = " system-event", "system event"
            else:
                extra_class, label = "", "user"
            rows.append(f'<tr class="row-user{extra_class}"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">{label}</td><td>{meta + "<br>" if meta else ""}{rendered}</td></tr>')

        elif role == "assistant":
            rendered = render_content(content)
            rows.append(f'<tr class="row-assistant"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">assistant</td><td><div class="meta-line">{meta}</div>{rendered}</td></tr>')

        elif role == "toolResult":
            tool_meta = render_tool_result_meta(msg)
            rendered = render_content(content)
            rows.append(f'<tr class="row-tool-result"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">toolResult</td><td><div class="meta-line">{tool_meta}</div>{rendered}</td></tr>')

        else:
            rendered = render_content(content)
            rows.append(f'<tr class="row-other"><td class="ln">{line_num}</td><td class="time">{time_str}</td><td class="role">{escape(role or etype)}</td><td>{meta + "<br>" if meta else ""}{rendered}</td></tr>')

    table_rows = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Session: {escape(session_name)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
h1 {{ color: #58a6ff; margin-bottom: 10px; font-size: 16px; }}
h2 {{ color: #8b949e; margin-bottom: 20px; font-size: 13px; font-weight: normal; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
tr {{ border-bottom: 1px solid #21262d; vertical-align: top; }}
td {{ padding: 8px 10px; }}
.ln {{ color: #484f58; width: 40px; text-align: right; font-size: 11px; user-select: none; }}
.time {{ color: #8b949e; width: 70px; font-size: 11px; white-space: nowrap; }}
.role {{ width: 100px; font-size: 11px; font-weight: bold; white-space: nowrap; }}

.row-user td {{ background: #0d2240; }}
.row-user .role {{ color: #58a6ff; }}
.row-user.heartbeat td {{ background: #1a1a0d; }}
.row-user.heartbeat .role {{ color: #d29922; }}
.row-user.queued td {{ background: #0d2240; }}
.row-user.system-event td {{ background: #1a1520; }}
.row-user.system-event .role {{ color: #bc8cff; }}

.row-assistant td {{ background: #0d1117; }}
.row-assistant .role {{ color: #3fb950; }}

.row-tool-result td {{ background: #161b22; }}
.row-tool-result .role {{ color: #bc8cff; }}

.row-model td {{ background: #1a1220; }}
.row-model .role {{ color: #bc8cff; }}

.row-session td {{ background: #1a2a1a; text-align: center; color: #3fb950; font-weight: bold; }}
.row-meta td {{ background: #161b22; color: #484f58; }}
.row-meta .role {{ color: #484f58; }}
.row-error td {{ background: #2a1010; }}
.row-error .role {{ color: #f85149; }}

.meta-line {{ margin-bottom: 4px; }}

.text-block {{ white-space: pre-wrap; word-break: break-word; padding: 4px 0; line-height: 1.5; }}
.text-block.alert-text {{ color: #f85149; font-weight: bold; background: #2a1010; padding: 4px 8px; border-radius: 4px; }}
.empty {{ color: #484f58; font-style: italic; }}

.thinking {{ margin: 4px 0; }}
.thinking summary {{ cursor: pointer; color: #d29922; font-size: 12px; padding: 2px 0; }}
.thinking pre {{ color: #8b949e; font-size: 12px; padding: 8px; margin-top: 4px; background: #0d1117; border-radius: 4px; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; }}

.tool-call {{ margin: 4px 0; padding: 6px 10px; background: #1a1a2e; border-left: 3px solid #58a6ff; border-radius: 4px; }}
.tool-call.message-send {{ border-left-color: #f85149; background: #2a1a1a; }}
.tool-call .tool-label {{ color: #58a6ff; font-size: 12px; }}
.tool-call.message-send .tool-label {{ color: #f85149; }}
.tool-call pre {{ font-size: 12px; color: #c9d1d9; margin-top: 4px; white-space: pre-wrap; word-break: break-word; }}

.tool-result {{ margin: 4px 0; padding: 6px 10px; background: #1a1a2e; border-left: 3px solid #bc8cff; border-radius: 4px; }}
.tool-result .tool-label {{ color: #bc8cff; font-size: 12px; }}
.tool-result pre {{ font-size: 12px; color: #8b949e; margin-top: 4px; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; }}

.unknown-block {{ margin: 4px 0; }}
.unknown-block .tool-label {{ color: #f85149; font-size: 12px; }}

pre {{ font-family: "SF Mono", "Fira Code", monospace; }}

.badge {{ display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px; margin: 1px 2px; vertical-align: middle; }}
.badge-model {{ background: #1f2a3a; color: #58a6ff; border: 1px solid #30363d; }}
.badge-api {{ background: #1a1a2e; color: #bc8cff; border: 1px solid #30363d; }}
.badge-stop {{ background: #1a2a1a; color: #3fb950; border: 1px solid #30363d; }}
.badge-error {{ background: #2a1010; color: #f85149; border: 1px solid #f8514966; }}
.badge-usage {{ background: #161b22; color: #8b949e; border: 1px solid #30363d; }}
.badge-tool {{ background: #1a1a2e; color: #bc8cff; border: 1px solid #30363d; font-weight: bold; }}
.badge-id {{ color: #484f58; font-size: 9px; }}
.badge-detail {{ background: #161b22; color: #8b949e; border: 1px solid #21262d; }}
</style>
</head>
<body>
<h1>Session Viewer</h1>
<h2>{escape(session_name)} &mdash; {len(entries)} entries</h2>
<table>
<thead><tr><th class="ln">#</th><th class="time">Time</th><th class="role">Role</th><th>Content</th></tr></thead>
<tbody>
{table_rows}
</tbody>
</table>
</body>
</html>"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <session.jsonl> [output.html]")
        print(f"\nAvailable sessions:")
        sessions_dir = os.path.expanduser("~/.openclaw/agents/main/sessions")
        if os.path.isdir(sessions_dir):
            for f in sorted(os.listdir(sessions_dir)):
                if f.endswith(".jsonl") or f.endswith(".jsonl.reset"):
                    fpath = os.path.join(sessions_dir, f)
                    size = os.path.getsize(fpath)
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
                    print(f"  {f}  ({size/1024:.0f}KB, {mtime})")
        sys.exit(1)

    input_path = sys.argv[1]

    if input_path == "--app":
        output_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/session-viewer.html"
        html_content = render_app()
        with open(output_path, "w") as f:
            f.write(html_content)
        print(f"App: file://{os.path.abspath(output_path)}")
        os.system(f'open "{output_path}"')
        sys.exit(0)

    if not os.path.exists(input_path):
        sessions_dir = os.path.expanduser("~/.openclaw/agents/main/sessions")
        matches = [f for f in os.listdir(sessions_dir) if f.startswith(input_path) and (".jsonl" in f)]
        if matches:
            input_path = os.path.join(sessions_dir, sorted(matches)[0])
        else:
            print(f"File not found: {input_path}")
            sys.exit(1)

    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.split(".jsonl")[0] + ".html"

    html_content = render_session(input_path)
    with open(output_path, "w") as f:
        f.write(html_content)

    print(f"Rendered {input_path}")
    print(f"Output: {output_path}")
    print(f"Open: file://{os.path.abspath(output_path)}")
