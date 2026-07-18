// Discord → n8n bridge bot
// Forwards Discord messages to your n8n webhook as:
//   { content, channelId, author, authorId, guildId, messageId }
//
// Trigger modes (set TRIGGER_MODE in .env):
//   mention  - only messages that @mention the bot (default, recommended)
//   prefix   - only messages starting with PREFIX (e.g. !agent)
//   all      - every message in the allowed channel(s)

require('dotenv').config();
const { Client, GatewayIntentBits, Partials } = require('discord.js');

const {
  DISCORD_BOT_TOKEN,
  N8N_WEBHOOK_URL,
  TRIGGER_MODE = 'mention',
  PREFIX = '!agent',
  CHANNEL_IDS = '', // optional comma-separated allow-list of channel IDs
} = process.env;

if (!DISCORD_BOT_TOKEN || !N8N_WEBHOOK_URL) {
  console.error('Missing DISCORD_BOT_TOKEN or N8N_WEBHOOK_URL in .env');
  process.exit(1);
}

const allowedChannels = CHANNEL_IDS.split(',').map((s) => s.trim()).filter(Boolean);

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent, // must also be enabled in the Developer Portal
  ],
  partials: [Partials.Channel],
});

client.once('ready', () => {
  console.log(`Bridge bot logged in as ${client.user.tag}`);
  console.log(`Trigger mode: ${TRIGGER_MODE}${TRIGGER_MODE === 'prefix' ? ` (prefix: ${PREFIX})` : ''}`);
  if (allowedChannels.length) console.log(`Restricted to channels: ${allowedChannels.join(', ')}`);
});

client.on('messageCreate', async (message) => {
  try {
    // Never react to bots (including ourselves) — avoids loops with n8n's replies
    if (message.author.bot) return;

    // Optional channel allow-list
    if (allowedChannels.length && !allowedChannels.includes(message.channelId)) return;

    // Decide whether this message is for the agent, and extract the instruction
    let content = message.content ?? '';
    if (TRIGGER_MODE === 'mention') {
      if (!message.mentions.has(client.user)) return;
      content = content.replace(new RegExp(`<@!?${client.user.id}>`, 'g'), '').trim();
    } else if (TRIGGER_MODE === 'prefix') {
      if (!content.startsWith(PREFIX)) return;
      content = content.slice(PREFIX.length).trim();
    }
    if (!content) return;

    const payload = {
      content,
      channelId: message.channelId,
      author: message.author.username,
      authorId: message.author.id,
      guildId: message.guildId,
      messageId: message.id,
    };

    const res = await fetch(N8N_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      await message.react('📨').catch(() => {});
      console.log(`Forwarded message ${message.id} from ${payload.author}`);
    } else {
      console.error(`n8n webhook returned ${res.status} ${res.statusText}`);
      await message.react('⚠️').catch(() => {});
    }
  } catch (err) {
    console.error('Failed to forward message:', err);
    await message.react('⚠️').catch(() => {});
  }
});

client.login(DISCORD_BOT_TOKEN);
