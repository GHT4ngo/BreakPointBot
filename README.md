# BreakPointBot

A small Discord utility for coordinating breaks and lunch. I built it for a practical
classroom need after a teacher asked for an easy shared break timer.

The bot provides live countdowns, optional end notifications, and weekday lunch menus from
Dalanissen and Livet Restaurant Solna.

## Commands

| Command | Description |
|---|---|
| `/break [minutes] [end]` | Start a break timer. Defaults to 10 minutes. |
| `/lunch [minutes] [end]` | Start a lunch timer and show today's menu. Defaults to 60 minutes. |
| `/extend <minutes>` | Add or remove minutes from the active timer. |
| `/stop` | Stop the active timer and clear the bot's channel messages. |
| `/menu [restaurant] [day]` | Send a weekday lunch menu by direct message. |
| `/ping` | Admin: toggle the `@everyone` notification when a timer ends. |
| `/lock` | Admin: toggle automatic removal of non-bot messages in the channel. |
| `/help` | Show the command list. |

The `end` option accepts an exact Swedish local time:

```text
/break minutes:15
/break end:14:30
/lunch end:12:00
/extend -5
```

## Lunch menus

- Dalanissen is read directly from its public lunch-menu page.
- Livet publishes its weekly menu as an image. Reading that image requires an optional
  Anthropic API key.
- Results are cached in memory to avoid repeated requests.

Menu scraping depends on the restaurants' page structure and may need adjustment if their
websites change.

## Run locally on Linux

Requirements:

- Python 3.10 or newer
- A Discord application and bot token
- Message Content Intent enabled in the Discord Developer Portal

```bash
git clone https://github.com/GHT4ngo/BreakPointBot.git
cd BreakPointBot

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# Edit .env and add DISCORD_TOKEN.

./start.sh
```

`ANTHROPIC_API_KEY` is optional. Without it, timers and the Dalanissen menu still work, but
the Livet menu image cannot be read.

## Discord permissions

Use the Discord Developer Portal to create the bot and enable:

- Scopes: `bot`, `applications.commands`
- Permissions: View Channels, Send Messages, Manage Messages, Read Message History
- Privileged intent: Message Content Intent

The bot needs Manage Messages to clear its own previous timer/menu messages and to support
the optional `/lock` mode. Users need Manage Server for `/ping` and Manage Channels for
`/lock`.

## Optional systemd service

Create `/etc/systemd/system/breakpointbot.service`:

```ini
[Unit]
Description=BreakPointBot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/path/to/BreakPointBot
ExecStart=/path/to/BreakPointBot/start.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now breakpointbot
```

Update deployments through your normal Git/SSH workflow and restart the service with
`sudo systemctl restart breakpointbot`.

## Project structure

```text
bot.py            Discord commands, timers, menu fetching, and presentation
requirements.txt  Python dependencies
.env.example      Required and optional environment variables
start.sh          Portable Linux launcher
tests/            Offline unit tests for timer and formatting helpers
```

Run the offline test suite with:

```bash
.venv/bin/python -m unittest discover -v
```

## Project status

Complete personal utility. Kept public as a compact example of Discord commands,
asynchronous timers, web scraping, API integration, permissions, and Linux service setup.
