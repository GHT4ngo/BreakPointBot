# BreakPointBot

A Discord bot for tracking class breaks and lunch, with live countdown timers and daily lunch menus from Dalanissen and Livet Restaurant Solna.

**Invite the bot directly to your server:**
[Invite BreakPointBot](https://discord.com/oauth2/authorize?client_id=1493836495038054481)

The bot runs 24/7 on a hosted server — no installation needed to use it.

---

## Commands

| Command | Description |
|---------|-------------|
| `/break [minutes] [end]` | Start a break timer (default: 10 min). Use `end:HH:MM` to set a stop time instead of a duration. |
| `/lunch [minutes] [end]` | Start a lunch timer (default: 60 min). Posts today's lunch menu above the timer. Use `end:HH:MM` to set a stop time. |
| `/extend <minutes>` | Add or remove minutes from the active timer. Use positive (`5`) to add or negative (`-5`) to cut time. |
| `/stop` | Cancel the active timer and clear bot messages from the channel. |
| `/menu [restaurant] [day]` | Send today's lunch menu to your DMs. |
| `/ping` | Toggle @mention when a timer ends. Off by default. |
| `/lock` | *(Admin only)* Lock the channel so non-bot messages are automatically deleted. Run again to unlock. Requires Manage Channels permission. |
| `/update` | *(Admin only)* Pull latest code from GitHub and restart the bot. Requires Manage Server permission. |
| `/help` | Show all available commands (visible only to you). |

### `/break` and `/lunch` options

| Option | Example | Description |
|--------|---------|-------------|
| `minutes` | `/break minutes:15` | Duration in minutes (default: 10 for break, 60 for lunch) |
| `end` | `/break end:14:30` | Set an exact stop time — overrides minutes |

**Examples:**
```
/break                   → 10 minute break
/break minutes:15        → 15 minute break
/break end:14:30         → break ends at 14:30
/lunch end:12:00         → lunch ends at 12:00
/extend 5                → add 5 minutes to the running timer
/extend -10              → cut 10 minutes from the running timer
```

### `/menu` options

| Option | Values | Default |
|--------|--------|---------|
| `restaurant` | `dalanissen` \| `livet` | both |
| `day` | `-4` to `+4` | today |

**Examples:**
```
/menu                    → both restaurants, today, sent to DMs
/menu restaurant:livet   → only Livet, sent to DMs
/menu day:1              → tomorrow's menu, sent to DMs
```

---

## Restaurants

**Dalanissen** — [dalanisse.se/lunchmeny](https://www.dalanisse.se/lunchmeny/)
Menu scraped directly from the website. Shows today's dishes + "Serveras hela veckan" section.

**Livet Restaurant Solna** — [livetbrand.com](https://www.livetbrand.com/har-finns-livet/livet-restaurant-solna/)
Menu is published as a weekly image. Read via Claude vision (Anthropic API).

---

## Timer Behaviour

- Updates every **20 seconds**
- Progress bar: **green** (0–50%) → **yellow** (50–75%) → **red** (75–100%)
- On `/lunch`: menu posts above the timer; deleted automatically when bar turns red so the channel stays clean
- When done: shows **"BREAK IS OVER! / Back to class."**
- Starting a new `/break` or `/lunch` purges all previous bot messages first

---

## Menu Cache

Fetched menus are cached in memory keyed on `(date, restaurant)`. The first `/menu` or `/lunch` call of the day hits the websites; all subsequent requests that day return the cached result instantly. Entries expire after **7 days**. The cache resets on bot restart.

---

## Self-hosting

If you want to run your own instance of the bot:

### Requirements

- Python 3.9+
- discord.py >= 2.3
- aiohttp, beautifulsoup4, anthropic, python-dotenv

### Local setup

**1. Clone and install dependencies:**
```bash
git clone https://github.com/GHT4ngo/BreakPointBot.git
cd BreakPointBot
pip install -r requirements.txt
```

**2. Create a `.env` file:**
```
DISCORD_TOKEN=your_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```
`ANTHROPIC_API_KEY` is used to OCR the Livet weekly menu image. Get a key at [console.anthropic.com](https://console.anthropic.com).

**3. Discord Developer Portal** ([discord.com/developers/applications](https://discord.com/developers/applications)):
- Create an application and add a Bot
- Under **Bot > Privileged Gateway Intents**, enable **Message Content Intent**
- Under **OAuth2 > URL Generator**, select scopes: `bot`, `applications.commands`
- Select permissions: Send Messages, Manage Messages, Read Message History

**4. Run:**
```bash
python bot.py
```

### Hosting on a server (24/7)

To keep the bot online without leaving your computer running, host it on a server. The bot runs on Oracle Cloud Free Tier (always free).

**Set up as a systemd service on Linux:**

```bash
sudo tee /etc/systemd/system/breakpointbot.service > /dev/null << 'EOF'
[Unit]
Description=BreakPointBot Discord Bot
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/BreakPointBot
ExecStart=/bin/bash /home/opc/BreakPointBot/start.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable breakpointbot
sudo systemctl start breakpointbot
```

Create `start.sh` in the project folder:
```bash
#!/bin/bash
source /home/opc/BreakPointBot/venv/bin/activate
exec python /home/opc/BreakPointBot/bot.py
```

**Updating the bot remotely:**
Once hosted, use the `/update` Discord command (requires Manage Server permission) to pull the latest code from GitHub and restart the bot — no SSH needed.

---

## Files

| File | Description |
|------|-------------|
| `bot.py` | Main bot (all logic) |
| `start.sh` | Startup script for systemd (activates venv) |
| `requirements.txt` | Python dependencies |
| `.env` | Your tokens (not committed to git — keep private!) |
