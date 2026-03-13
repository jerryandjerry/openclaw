# Bundled Skills

52 skills shipped with the OpenClaw installation. Every agent has access to these out of the box.

Skills are gated by platform, required binaries, and environment variables. An agent only sees a skill if its prerequisites are met at session start.

---

### Communication & Messaging

| Skill | Description |
|-------|-------------|
| bluebubbles | Send/manage iMessages via BlueBubbles (recommended iMessage integration) |
| discord | Discord ops via the message tool (channel=discord) |
| himalaya | CLI email management via IMAP/SMTP — list, read, write, reply, forward, search |
| imsg | iMessage/SMS CLI for listing chats, history, and sending messages via Messages.app |
| slack | Control Slack from OpenClaw — react to messages, pin/unpin items |
| voice-call | Start voice calls via the OpenClaw voice-call plugin |
| wacli | Send WhatsApp messages or search/sync WhatsApp history via wacli CLI |

### Productivity & Notes

| Skill | Description |
|-------|-------------|
| apple-notes | Manage Apple Notes via `memo` CLI (create, view, edit, delete, search) |
| apple-reminders | Manage Apple Reminders via remindctl CLI (list, add, edit, complete, delete) |
| bear-notes | Create, search, and manage Bear notes via grizzly CLI |
| notion | Notion API for creating and managing pages, databases, and blocks |
| obsidian | Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli |
| things-mac | Manage Things 3 via `things` CLI on macOS (add/update projects+todos) |
| trello | Manage Trello boards, lists, and cards via the Trello REST API |

### Image & Visual

| Skill | Description |
|-------|-------------|
| nano-banana-pro | Generate or edit images via Gemini 3 Pro Image |
| openai-image-gen | Batch-generate images via OpenAI Images API with gallery output |
| peekaboo | Capture and automate macOS UI with the Peekaboo CLI |
| camsnap | Capture frames or clips from RTSP/ONVIF cameras |
| canvas | Interactive canvas for visual output |
| gifgrep | Search GIF providers, download results, extract stills/sheets |

### Audio & Speech

| Skill | Description |
|-------|-------------|
| openai-whisper | Local speech-to-text with the Whisper CLI (no API key) |
| openai-whisper-api | Transcribe audio via OpenAI Audio Transcriptions API |
| sag | ElevenLabs text-to-speech with mac-style say UX |
| sherpa-onnx-tts | Local text-to-speech via sherpa-onnx (offline, no cloud) |
| songsee | Generate spectrograms and feature-panel visualizations from audio |
| spotify-player | Terminal Spotify playback/search via spogo or spotify_player |
| sonoscli | Control Sonos speakers (discover/status/play/volume/group) |
| blucli | BluOS CLI for discovery, playback, grouping, and volume |

### Video & Media

| Skill | Description |
|-------|-------------|
| video-frames | Extract frames or short clips from videos using ffmpeg |
| summarize | Summarize or extract text/transcripts from URLs, podcasts, and local files |

### Documents & Files

| Skill | Description |
|-------|-------------|
| nano-pdf | Edit PDFs with natural-language instructions via nano-pdf CLI |

### Development & Code

| Skill | Description |
|-------|-------------|
| coding-agent | Delegate coding tasks to Codex, Claude Code, or Pi agents via background process |
| github | GitHub operations via `gh` CLI — issues, PRs, CI runs, code review, API queries |
| gh-issues | Fetch GitHub issues, spawn sub-agents to implement fixes and open PRs |
| skill-creator | Create, edit, improve, or audit AgentSkills |
| tmux | Remote-control tmux sessions for interactive CLIs |
| mcporter | List, configure, auth, and call MCP servers/tools directly |
| session-logs | Search and analyze your own session logs using jq |
| oracle | Best practices for using the oracle CLI (prompt + file bundling) |

### AI & Search

| Skill | Description |
|-------|-------------|
| gemini | Gemini CLI for one-shot Q&A, summaries, and generation |
| clawhub | ClawHub CLI to search, install, update, and publish agent skills |
| model-usage | Summarize per-model usage/cost data from CodexBar |

### Smart Home & IoT

| Skill | Description |
|-------|-------------|
| openhue | Control Philips Hue lights and scenes via the OpenHue CLI |
| eightctl | Control Eight Sleep pods (status, temperature, alarms, schedules) |

### Web & Social

| Skill | Description |
|-------|-------------|
| xurl | Authenticated requests to the X (Twitter) API — post, reply, search, DMs, media |
| blogwatcher | Monitor blogs and RSS/Atom feeds for updates |
| goplaces | Query Google Places API for text search, place details, and reviews |
| weather | Get current weather and forecasts via wttr.in or Open-Meteo |

### Office & Workspace

| Skill | Description |
|-------|-------------|
| gog | Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs |
| 1password | Set up and use 1Password CLI — sign in, read/inject/run secrets |

### Other

| Skill | Description |
|-------|-------------|
| healthcheck | Host security hardening and risk-tolerance configuration for OpenClaw deployments |
| ordercli | Foodora-only CLI for checking past orders and active order status |

---

## Configured API Keys

The following bundled skills have API keys set in `openclaw.json`:

| Skill | Provider |
|-------|----------|
| nano-banana-pro | Google Gemini |
| openai-image-gen | OpenAI |
| openai-whisper-api | OpenAI |
| goplaces | Google Places |

---

## Notes

- All 52 bundled skills are available to every agent by default.
- Skills are gated at load time — if the required binary or env var is missing, the skill won't appear in that agent's session.
- Per-agent skills can be added to `<workspace>/skills/` for role-specific capabilities.
- Skill config and API keys live in `~/.openclaw/openclaw.json` under `skills.entries`.
