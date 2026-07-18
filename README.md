# Discord Chat Agent → n8n → Obsidian

## What this lets you do

Message an AI agent from any Discord channel and have it do research work for you, hands-free:

- **Ask questions that need current information** — the agent searches the web, reads the most relevant pages, and writes up what it finds with source links.
- **Summarize YouTube videos** — send a link; the agent fetches the transcript and produces a structured summary of the key points.
- **Summarize Facebook videos** — same flow; the video's audio is downloaded and transcribed automatically (public videos work out of the box; private ones need a one-time cookies setup).
- **Build a knowledge base automatically** — every result is saved as a dated markdown note in your Obsidian vault, complete with YAML frontmatter (title, date, sources, tags), ready to link and search like any other note.
- **Stay informed without watching n8n** — the agent replies in Discord twice: once immediately to confirm it received your request, and again when the task is complete, with the key takeaway and the saved note's location.
- **Ask follow-ups** — the agent remembers recent conversation per channel, so "now condense that into three bullet points" works.

Example messages:

```
@YourBot what's the latest news on solid state batteries? Save a research note.
@YourBot summarize https://www.youtube.com/watch?v=xxxx
@YourBot summarize this Facebook video and pull out the main arguments: https://www.facebook.com/watch?v=xxxx
```

## How it works

Send an instruction to the AI agent from Discord. The agent acknowledges the request, does the work — web search, page reading, video transcription — saves a markdown summary into your Obsidian vault, and replies in Discord when done.

```
Discord message ("@Bot summarize https://youtube.com/...")
      │
      ▼
[1] discord-n8n-bridge  ──POST──▶  [2] n8n workflow (discord-ai-agent-obsidian.json)
    (Node.js bot)                       │  ├─ posts "Request received" to Discord
                                        │  ├─ AI Agent + tools:
                                        │  │    • web_search (SerpAPI)
                                        │  │    • fetch_webpage
                                        │  │    • get_video_transcript ──▶ [3] transcript-service
                                        │  │                                  (yt-dlp + Whisper)
                                        │  ├─ writes markdown note ──▶ Obsidian vault (mounted folder)
                                        │  └─ posts completion + note path to Discord
```

All three components run as containers in one `docker-compose.yml` on the same Docker network.

---

## Project layout

```
Discord-Chat-Agent/
├── README.md                        ← this file
├── docker-compose.yml               ← you create this (template below)
├── discord-ai-agent-obsidian.json   ← the n8n workflow (imported via n8n UI)
├── discord-n8n-bridge/
│   └── src/                         ← bot.js, package.json, .env.example
│                                      (+ Dockerfile — create it, step 2.2)
└── transcript-service/
    └── src/                         ← app.py, Dockerfile, requirements.txt
```

> The loose `bot.js`, `README.md`, `transcript-app.py`, `transcript-service-README.md`
> files sitting next to the `src/` folders are duplicates of the files inside `src/`
> — safe to delete.

---

## Prerequisites

- **Docker Desktop for Windows** (with your `D:` drive enabled under Settings → Resources → File Sharing, if listed)
- A **Discord server** you manage
- **OpenAI API key** (for the agent's chat model; also speeds up transcription if provided)
- **SerpAPI key** — free tier at https://serpapi.com (100 searches/month) — for the web search tool
- Your **Obsidian vault** path, e.g. `D:/Obsidian/MyVault`

---

## Step 1 — Discord setup (two credentials, two different things)

### 1.1 Channel webhook (lets n8n POST replies INTO the channel)
1. In Discord: your channel → ⚙️ Edit Channel → **Integrations → Webhooks → New Webhook**.
2. Name it (e.g. "AI Agent"), **Copy Webhook URL**. You'll paste this into n8n in Step 4.

### 1.2 Bot (lets the bridge READ messages FROM the channel)
1. https://discord.com/developers/applications → **New Application** → name it.
2. **Bot** tab → **Reset Token** → copy the token (needed in Step 2).
3. Same tab → enable **Message Content Intent** (under Privileged Gateway Intents). ← most-missed step; without it the bot receives empty messages.
4. **OAuth2 → URL Generator** → scope `bot` → permissions **View Channels**, **Read Message History**, **Add Reactions** → open the generated URL → invite the bot to your server.

---

## Step 2 — Prepare the two services

### 2.1 Bridge bot config
```powershell
cd "D:\Devlaps\AI-Experiments\n8n - workflows\Discord-Chat-Agent\discord-n8n-bridge\src"
copy .env.example .env
```
Edit `.env`:
```
DISCORD_BOT_TOKEN=<token from step 1.2>
N8N_WEBHOOK_URL=http://n8n:5678/webhook/discord-agent
TRIGGER_MODE=mention
```
(`http://n8n:5678/...` works because the containers share a Docker network — no IP needed.)

### 2.2 Bridge bot Dockerfile
Create `discord-n8n-bridge/src/Dockerfile` with:
```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY bot.js ./
CMD ["node", "bot.js"]
```

### 2.3 Transcript service
Nothing to edit — it's configured via environment variables in docker-compose (next step). Decide one thing now:
- **Local Whisper** (default): free, runs on your CPU, transcribes at ~10–25% of video length.
- **OpenAI API**: set `OPENAI_API_KEY` in the compose file → ~30s for a 20-min video, ≈ $0.12.

---

## Step 3 — docker-compose.yml

Create `docker-compose.yml` in the project root. **If you already run n8n via compose elsewhere, merge the `discord-bridge` and `transcript-service` blocks into that file instead** (all three must share a network). If your existing n8n runs via `docker run`, easiest is to recreate it here — mount the same data volume/folder and your workflows carry over.

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - GENERIC_TIMEZONE=Australia/Sydney   # set to your timezone
      - N8N_SECURE_COOKIE=false             # allows http://localhost login
    volumes:
      - n8n_data:/home/node/.n8n
      # ▼ Mount your Obsidian vault INTO THE N8N CONTAINER (n8n writes the notes)
      - "D:/Obsidian/MyVault:/data/obsidian-vault"

  discord-bridge:
    build: ./discord-n8n-bridge/src
    restart: unless-stopped
    env_file:
      - ./discord-n8n-bridge/src/.env
    depends_on:
      - n8n

  transcript-service:
    build: ./transcript-service/src
    restart: unless-stopped
    environment:
      - WHISPER_MODEL=base              # tiny | base | small | medium
      - MAX_DURATION_SECONDS=5400
      # - OPENAI_API_KEY=sk-...         # uncomment for fast API transcription
      # - COOKIES_FILE=/data/cookies.txt  # for private/login-gated Facebook videos
    # volumes:
    #   - ./transcript-service/cookies.txt:/data/cookies.txt:ro

volumes:
  n8n_data:
```

Then, from the project root:
```powershell
cd "D:\Devlaps\AI-Experiments\n8n - workflows\Discord-Chat-Agent"
docker compose up -d --build
```

Check all three are up: `docker compose ps` — then open n8n at http://localhost:5678.

> **Windows notes:** use forward slashes in volume paths (`D:/Obsidian/...`), and keep
> quotes around any path — your project path contains spaces. The bridge won't do
> anything visible until the workflow is active; that's expected.

---

## Step 4 — Import & configure the n8n workflow

1. In n8n: **Workflows → Add workflow → ⋯ → Import from File** → `discord-ai-agent-obsidian.json`.
2. Attach credentials (nodes with a ⚠️ need them):
   - **Acknowledge in Discord** and **Send Completion to Discord** → create a *Discord Webhook* credential → paste the webhook URL from step 1.1.
   - **OpenAI Chat Model** → your OpenAI API key.
   - **web_search** → your SerpAPI key.
3. Edit two nodes:
   - **Write to Obsidian Vault** → the path already starts with `/data/obsidian-vault/AI Summaries/` which matches the compose mount — just create an `AI Summaries` folder in your vault (or change the subfolder in the expression).
   - **get_video_transcript** → change the URL to:
     `http://transcript-service:8000/transcript?url={video_url}`
     and in the node's **Options**, set the timeout to `600000` (10 min) — local Whisper needs it for longer videos.
4. **Save** the workflow.

---

## Step 5 — Test, then go live

**Test run:**
1. Open the **Discord Message Webhook** node → it shows a *Test* URL (`/webhook-test/discord-agent`).
2. Temporarily set the bridge's `.env` → `N8N_WEBHOOK_URL=http://n8n:5678/webhook-test/discord-agent`, then `docker compose up -d discord-bridge` to restart it with the change.
3. In n8n click **Listen for test event** (or *Execute workflow*).
4. In Discord: `@YourBot summarize https://www.youtube.com/watch?v=<short video>`
5. Watch the execution light up node-by-node in n8n. The bot reacts 📨 when it forwards; you should get the "Request received" message, then the completion message, and a new `.md` file in your vault.

**Go live:**
1. Toggle the workflow **Active** (top-right in n8n).
2. Change the bridge `.env` back to the production URL (remove `-test`): `http://n8n:5678/webhook/discord-agent`, restart: `docker compose up -d discord-bridge`.

First transcript request is slow — the Whisper model downloads on first use. Warm it up with a 1-minute video.

---

## Usage examples

```
@YourBot what's the latest news on solid state batteries? Save a research note.
@YourBot summarize https://www.youtube.com/watch?v=xxxx
@YourBot summarize this Facebook video: https://www.facebook.com/watch?v=xxxx
```

Every request produces a dated note in `AI Summaries/` with YAML frontmatter (title, date, sources, tags) plus a Discord reply with the key takeaway.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Bot doesn't react at all | Message Content Intent not enabled (step 1.2.3); or bot not @mentioned; or `CHANNEL_IDS` excludes the channel. Check `docker compose logs discord-bridge`. |
| Bot reacts ⚠️ | Webhook unreachable: workflow not Active (production URL) / not listening (test URL), or wrong `N8N_WEBHOOK_URL`. |
| 📨 but nothing in Discord | Discord Webhook credential missing/wrong on the two Discord nodes. Check the execution log in n8n. |
| Agent errors mid-run | Open the execution in n8n; red node shows the cause (usually missing OpenAI/SerpAPI credential). |
| `get_video_transcript` times out | Raise the tool node's timeout; use a smaller `WHISPER_MODEL`; or set `OPENAI_API_KEY` on transcript-service. |
| Facebook video fails (422) | Private/login-gated → export a `cookies.txt` while logged into Facebook, mount it, set `COOKIES_FILE`. |
| Note not appearing in vault | Vault volume mounted on the wrong service (must be `n8n`), path typo, or `AI Summaries` folder missing. Check the **Write to Obsidian Vault** node error. |
| n8n asks about node versions on import | Fine — accept; the workflow uses broadly compatible node versions. |

Useful commands:
```powershell
docker compose logs -f discord-bridge      # watch the bot
docker compose logs -f transcript-service  # watch downloads/transcription
docker compose restart transcript-service
```

---

## Cost & performance notes

- **Chat model:** each request = one agent run on `gpt-4o` (swap the model node for a cheaper/local model if you like — Anthropic, Gemini, Ollama all drop in).
- **Search:** SerpAPI free tier = 100 searches/month; the agent may use 1–3 per research request.
- **Transcription:** local = free but CPU-bound; OpenAI API ≈ $0.006/min of video.
- **Memory:** the agent keeps short conversation memory *per Discord channel*, so follow-ups like "now make that shorter" work in the same channel.
