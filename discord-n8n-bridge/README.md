# Discord → n8n Bridge Bot

Forwards Discord messages to your n8n webhook so the "Discord AI Agent → Obsidian Notes" workflow can trigger. Payload sent: `{ content, channelId, author, authorId, guildId, messageId }` — exactly what the workflow's Normalize Input node expects.

## 1. Create the Discord bot

1. Go to https://discord.com/developers/applications → **New Application**.
2. **Bot** tab → **Reset Token** → copy it (this is `DISCORD_BOT_TOKEN`).
3. Still on the Bot tab, under *Privileged Gateway Intents*, enable **Message Content Intent**.
4. **OAuth2 → URL Generator**: check `bot` scope, then permissions **View Channels**, **Read Message History**, **Add Reactions**. Open the generated URL and invite the bot to your server.

## 2. Run the bot

```bash
cp .env.example .env   # then edit .env with your token + webhook URL
npm install
npm start
```

Mention the bot in Discord: `@YourBot summarize https://youtube.com/watch?v=...`
The bot reacts 📨 when forwarded (⚠️ if the webhook call failed).

## 3. Run alongside n8n in Docker (optional)

```dockerfile
# Dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY bot.js ./
CMD ["node", "bot.js"]
```

```yaml
# add to your docker-compose.yml next to n8n
  discord-bridge:
    build: ./discord-n8n-bridge
    restart: unless-stopped
    environment:
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
      - N8N_WEBHOOK_URL=http://n8n:5678/webhook/discord-agent
      - TRIGGER_MODE=mention
```

(Inside the compose network the bot can reach n8n by service name, e.g. `http://n8n:5678/...`.)

## Notes

- The bot ignores all bot-authored messages, so the workflow's own Discord replies can never re-trigger it (no loops).
- Test vs production webhook URLs differ in n8n: `/webhook-test/...` only works while "Listen for test event" is active; `/webhook/...` works once the workflow is **Activated**.
