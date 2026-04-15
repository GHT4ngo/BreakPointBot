BreakPointBot
=============
A Discord bot for tracking class breaks and lunch, with live countdown
timers and daily lunch menus from Dalanissen and Livet Restaurant Solna.


SETUP
-----
1. Install dependencies:
      pip install -r requirements.txt

2. Create a .env file in this folder:
      DISCORD_TOKEN=your_bot_token_here
      ANTHROPIC_API_KEY=your_anthropic_key_here

   ANTHROPIC_API_KEY is used to OCR the Livet weekly menu image.
   You can get a key at https://console.anthropic.com

3. Discord Developer Portal (discord.com/developers/applications):
   - Create an application and add a Bot
   - Under Bot > Privileged Gateway Intents, enable:
       Message Content Intent
   - Under OAuth2 > URL Generator, select scopes:
       bot, applications.commands
   - Select permissions:
       Send Messages, Manage Messages, Read Message History
   - Copy the generated URL and open it to invite the bot to your server

4. Run the bot:
      python bot.py


COMMANDS
--------
/break [minutes]
    Start a break timer (default: 10 minutes).
    Clears all previous bot messages in the channel, then posts a live
    countdown with a progress bar. Bar turns green > yellow > red.

/lunch [minutes]
    Start a lunch timer (default: 60 minutes).
    Same as /break, but first posts today's lunch menu from both
    restaurants. The menu is automatically removed when the bar hits red.

/stop
    Cancel the active timer and clear bot messages from the channel.

/menu [restaurant] [day]
    Send today's lunch menu to your DMs.
    Options:
      restaurant  dalanissen | livet  (default: both)
      day         -4 to +4            (days within the current Mon-Fri week)
    Examples:
      /menu                   -> both restaurants today, sent to DMs
      /menu restaurant:livet  -> only Livet, sent to DMs
      /menu day:1             -> tomorrow's menu, sent to DMs

/ping
    Toggle @mention when a timer ends. Off by default.

/lock
    (Admin only) Lock the channel so non-bot messages are automatically
    deleted. Run again to unlock. Requires Manage Channels permission.

/help
    Show all available commands (visible only to you).


RESTAURANTS
-----------
Dalanissen       https://www.dalanisse.se/lunchmeny/
                 Menu scraped directly from the website.
                 Shows today's dishes + "Serveras hela veckan" section.

Livet Restaurant https://www.livetbrand.com/har-finns-livet/livet-restaurant-solna/
Solna            Menu is published as a weekly image.
                 Read via Claude vision (Anthropic API).


TIMER BEHAVIOUR
---------------
- Updates every 20 seconds
- Progress bar:  green (0-50%) -> yellow (50-75%) -> red (75-100%)
- On /lunch: menu posts above the timer; deleted automatically when bar
  turns red so the channel stays clean
- When done: shows "BREAK IS OVER! / Back to class."
- Starting a new /break or /lunch purges all previous bot messages first


MENU CACHE
----------
Fetched menus are cached in memory keyed on (date, restaurant).
The first /menu or /lunch call of the day hits the websites; all
subsequent requests that day return the cached result instantly.
Entries expire after 7 days. The cache resets on bot restart.


FILES
-----
bot.py            Main bot (all logic)
requirements.txt  Python dependencies
.env              Your tokens (not committed to git -- keep private!)
debug_menu.py     Dev utility: test menu scraping without running the bot


REQUIREMENTS
------------
Python 3.11+
discord.py >= 2.3
aiohttp
beautifulsoup4
anthropic
python-dotenv
