"""
BreakPointBot - Discord break & lunch timer bot
Author: Christofer Lindholm DE25
"""

from __future__ import annotations
import discord
from discord import app_commands
import asyncio
import datetime
import os
import re
import base64
import sys
import subprocess
from dotenv import load_dotenv
import aiohttp
from bs4 import BeautifulSoup

load_dotenv()
TOKEN             = os.getenv("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
REPO_DIR          = os.path.dirname(os.path.abspath(__file__))

# ─── ANSI Colors (used inside ```ansi code blocks) ─────────────────────────
E   = "\u001b"
R   = f"{E}[0m"
DIM = f"{E}[2m"
GN  = f"{E}[1;32m"
YL  = f"{E}[1;33m"   # orange/yellow — price
RD  = f"{E}[1;31m"
CY  = f"{E}[1;36m"
MG  = f"{E}[1;35m"
WH  = f"{E}[1;37m"   # bold white   — dish name
NW  = f"{E}[37m"     # normal white — ingredients
DGR = f"{E}[2;30m"

ANSI_RE = re.compile(r"\u001b\[[0-9;]*m")

def vlen(s: str) -> int:
    """Visual length of string — strips ANSI codes before measuring."""
    return len(ANSI_RE.sub("", s))


# ─── Box Drawing ───────────────────────────────────────────────────────────
# W = inner width (between the two │ borders)
# All border characters share one color so nothing bleeds.

W = 30  # safe for mobile Discord

def box_top(a: str, w: int = W) -> str:
    return f"{a}╔{'═' * w}╗{R}"

def box_sep(a: str, w: int = W) -> str:
    return f"{a}╠{'═' * w}╣{R}"

def box_bot(a: str, w: int = W) -> str:
    return f"{a}╚{'═' * w}╝{R}"

def box_empty(a: str, w: int = W) -> str:
    return f"{a}║{' ' * w}║{R}"

def box_line(content: str, a: str, w: int = W) -> str:
    """Pad content to visual width w, then wrap in border."""
    pad = max(0, w - vlen(content))
    return f"{a}║{R}{content}{' ' * pad}{a}║{R}"


# ─── Helpers ───────────────────────────────────────────────────────────────

BAR_W = 18  # visual width of the filled/empty segment

def progress_bar(elapsed: float, total: float) -> str:
    pct    = min(elapsed / total, 1.0)
    filled = round(pct * BAR_W)
    empty  = BAR_W - filled
    color  = GN if pct < 0.5 else (YL if pct < 0.75 else RD)
    bar    = f"{color}{'█' * filled}{DGR}{'░' * empty}{R}"
    return f"{bar} {WH}{int(pct * 100):3d}%{R}"   # visual: BAR_W + 5 = 23


def fmt_time(seconds: int) -> str:
    m, s = divmod(max(seconds, 0), 60)
    return f"{m:02d}:{s:02d}"


def build_timer_msg(kind: str, remaining: int, total: int, end_time: datetime.datetime) -> str:
    elapsed  = total - remaining
    a        = MG if kind == "LUNCH" else CY
    label    = "LUNCH BREAK" if kind == "LUNCH" else "BREAK TIME"
    t_str    = fmt_time(remaining)
    end_str  = end_time.strftime("%H:%M")
    bar      = progress_bar(elapsed, total)

    return "\n".join([
        "```ansi",
        box_top(a),
        box_empty(a),
        box_line(f"  {WH}BREAKPOINTBOT{R}", a),
        box_empty(a),
        box_sep(a),
        box_line(f"  {a}{label}{R}", a),
        box_empty(a),
        box_line(f"  {WH}{t_str}{R}  remaining", a),
        box_line(f"  {DIM}ends at {end_str}{R}", a),
        box_empty(a),
        box_sep(a),
        box_line(f"  {bar}", a),
        box_empty(a),
        box_bot(a),
        "```",
    ])


def build_done_msg(kind: str, mention: str | None) -> str:
    a     = MG if kind == "LUNCH" else CY
    label = "LUNCH IS OVER!" if kind == "LUNCH" else "BREAK IS OVER!"

    msg = "\n".join([
        "```ansi",
        box_top(a),
        box_empty(a),
        box_line(f"  {WH}BREAKPOINTBOT{R}", a),
        box_empty(a),
        box_sep(a),
        box_empty(a),
        box_line(f"  {YL}{label}{R}", a),
        box_line(f"  {DIM}Back to class.{R}", a),
        box_empty(a),
        box_bot(a),
        "```",
    ])
    if mention:
        msg += f"\n{mention}"
    return msg


# ─── Swedish date helpers ──────────────────────────────────────────────────

DAYS_SV = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
MONTHS_SV = {
    1: "januari", 2: "februari", 3: "mars",    4: "april",
    5: "maj",     6: "juni",     7: "juli",     8: "augusti",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}

def date_sv(d: datetime.date) -> str:
    return f"{DAYS_SV[d.weekday()]} {d.day} {MONTHS_SV[d.month]}"

def today_sv() -> str:
    return date_sv(datetime.date.today())

def get_target_date(offset: int) -> datetime.date | None:
    """Return today + offset days if it falls Mon–Fri of the current week, else None."""
    today  = datetime.date.today()
    target = today + datetime.timedelta(days=offset)
    # Must be a weekday
    if target.weekday() > 4:
        return None
    # Must be within current week (Mon–Fri)
    week_mon = today - datetime.timedelta(days=today.weekday())
    week_fri = week_mon + datetime.timedelta(days=4)
    if target < week_mon or target > week_fri:
        return None
    return target

ALWAYS_RE = re.compile(r"serveras hela veckan", re.IGNORECASE)

# ─── Menu Cache ────────────────────────────────────────────────────────────
# key: (date_str, "dalanissen"|"livet")  value: (cached_at, data)
_menu_cache: dict[tuple, tuple[datetime.datetime, object]] = {}
_CACHE_TTL  = datetime.timedelta(days=7)


def _cache_get(key: tuple) -> object | None:
    entry = _menu_cache.get(key)
    if entry and datetime.datetime.now() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: tuple, data: object) -> None:
    _menu_cache[key] = (datetime.datetime.now(), data)


async def cached_dalanisse(target_date: datetime.date) -> dict:
    key = (date_sv(target_date), "dalanissen")
    hit = _cache_get(key)
    if hit is not None:
        return hit
    data = await scrape_dalanisse(target_date)
    _cache_set(key, data)
    return data


async def cached_livet(target_date: datetime.date) -> list:
    key = (date_sv(target_date), "livet")
    hit = _cache_get(key)
    if hit is not None:
        return hit
    data = await scrape_livet(target_date)
    _cache_set(key, data)
    return data


WRAP_WIDTH = 34  # chars per line, safe for mobile Discord

def wrap_text(text: str, width: int = WRAP_WIDTH) -> list[str]:
    """Word-wrap a string to width characters per line."""
    words  = text.split()
    lines  = []
    cur    = ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines or [""]


# ─── Web Scraping ──────────────────────────────────────────────────────────

DALANISSE_URL = "https://www.dalanisse.se/lunchmeny/"
LIVET_BASE    = "https://www.livetbrand.com"
LIVET_URL     = f"{LIVET_BASE}/har-finns-livet/livet-restaurant-solna/"


async def fetch_html(url: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0 (BreakPointBot/1.0)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return None


async def scrape_dalanisse(target_date: datetime.date | None = None) -> dict:
    """
    Parse the Dal & Nisse menu table.

    Structure on the page:
        <th class="menu_header">  day heading (e.g. "Onsdag 15 april")
        <td class="td_title">     dish name
        <td class="td_dbsk">      (empty, hidden column)
        <td class="td_price">     price (e.g. "155 kr")
        ... repeats per dish ...
        <th class="menu_header">  next day  (or "Serveras hela veckan")

    Returns { 'date', 'today': [dish  price, ...], 'always': [...] }
    """
    if target_date is None:
        target_date = datetime.date.today()
    html = await fetch_html(DALANISSE_URL)
    if not html:
        return {"date": date_sv(target_date), "today": ["Could not reach Dalanissen."], "always": []}

    soup      = BeautifulSoup(html, "html.parser")
    today_str = date_sv(target_date)

    table = soup.find("table")
    if not table:
        return {"date": today_str, "today": ["Menu table not found on page."], "always": []}

    today_items  = []
    always_items = []
    section      = None   # "today" | "always" | None
    pending_title = None  # buffer dish name until we see the price

    for cell in table.find_all(["th", "td"]):
        classes = cell.get("class", [])
        text    = cell.get_text(strip=True)

        if "menu_header" in classes:
            if today_str.lower() in text.lower():
                section = "today"
            elif ALWAYS_RE.search(text):
                section = "always"
            elif section == "today":
                # Hit next weekday — done collecting today
                section = None
            # (once we enter "always" we keep going until end of table)

        elif "td_title" in classes and text:
            pending_title = text

        elif "td_price" in classes and pending_title:
            combined = f"{pending_title}  {text}" if text else pending_title
            if section == "today":
                today_items.append(combined)
            elif section == "always":
                always_items.append(combined)
            pending_title = None

    if not today_items:
        today_items = [f"Ingen meny hittad for {today_str}."]

    return {"date": today_str, "today": today_items, "always": always_items}


async def _fetch_image_bytes(url: str) -> tuple[bytes, str] | None:
    """Download an image; return (bytes, content_type) or None."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    ct   = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
                    return data, ct
    except Exception:
        pass
    return None


def _clean_ocr(lines: list[str]) -> list[str]:
    """Strip Claude markdown/preamble from OCR output."""
    out = []
    for line in lines:
        # Remove markdown headers and bold
        line = re.sub(r"^#+\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        out.append(line)
    # Drop leading non-dish lines (Claude sometimes adds intro sentences)
    preamble_re = re.compile(
        r"^(i |here |the menu|below|the following|unfortunately|i don|i can)",
        re.IGNORECASE,
    )
    while out and preamble_re.match(out[0].strip()):
        out.pop(0)
    return out


async def _ocr_image(img_bytes: bytes, content_type: str, date_str: str) -> list[str]:
    """Send image to Claude vision and return cleaned menu lines for the given date."""
    import anthropic as _anthropic
    client  = _anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    img_b64 = base64.standard_b64encode(img_bytes).decode()
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": content_type, "data": img_b64},
                },
                {
                    "type": "text",
                    "text": (
                        f"Swedish weekly lunch menu image for Livet Restaurant Solna.\n"
                        f"Output ONLY dishes listed under '{date_str}'. "
                        f"No other days. No explanations. No markdown.\n"
                        f"Format each dish as:\n"
                        f"Dish Name\n"
                        f"  Main ingredients\n"
                        f"  XX kr\n\n"
                        f"Start your response with the first dish name."
                    ),
                },
            ],
        }],
    )
    return _clean_ocr(message.content[0].text.strip().split("\n"))


async def scrape_livet(target_date: datetime.date | None = None) -> list[str]:
    """
    Livet shows the weekly menu as two images (Swedish + English).
    We look for the image whose filename contains 'svenska' and OCR it,
    filtering to only return dishes for target_date.
    Falls back to a link if anything fails.
    """
    if target_date is None:
        target_date = datetime.date.today()
    d_str = date_sv(target_date)

    if not ANTHROPIC_API_KEY:
        return ["ANTHROPIC_API_KEY not set.", LIVET_URL]

    html = await fetch_html(LIVET_URL)
    if not html:
        return ["Could not reach Livet Restaurant.", LIVET_URL]

    soup = BeautifulSoup(html, "html.parser")

    # Target the Swedish menu image (filename contains 'svenska')
    menu_img_url = None
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "svenska" in src.lower() or "rattad" in src.lower():
            menu_img_url = src
            break

    # Fallback: any non-logo image
    if not menu_img_url:
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and not any(skip in src.lower() for skip in [".svg", "logo", "icon"]):
                menu_img_url = src
                break

    if not menu_img_url:
        return ["Menu image not found on Livet's page.", LIVET_URL]

    # Normalize URL — strip resize params so we get full resolution
    if menu_img_url.startswith("/"):
        menu_img_url = LIVET_BASE + menu_img_url
    menu_img_url = menu_img_url.split("?")[0]

    result = await _fetch_image_bytes(menu_img_url)
    if not result:
        return ["Could not download Livet menu image.", LIVET_URL]

    img_bytes, content_type = result
    try:
        return await _ocr_image(img_bytes, content_type, d_str)
    except Exception as e:
        return [f"Vision error: {e}", LIVET_URL]


_PRICE_RE = re.compile(r"\d+\s*kr", re.IGNORECASE)


def _dn_items(items: list[str]) -> list[str]:
    """Render Dalanissen dish items. Bold dish, normal ingredients, orange price."""
    out = []
    for item in items:
        dish, price = item.rsplit("  ", 1) if "  " in item else (item, "")
        wrapped = wrap_text(dish)
        for i, line in enumerate(wrapped):
            out.append(f"{WH}{line}{R}" if i == 0 else f"  {NW}{line}{R}")
        if price:
            out.append(f"  {YL}{price}{R}")
        out.append("")
    return out


def _livet_lines(livet: list[str]) -> list[str]:
    """Render Livet OCR lines with wrapping. Bold dish name, normal ingredients, orange price.

    Price lines may or may not be indented depending on what Claude returns,
    so we check the price regex first before checking indentation.
    """
    out = []
    for raw in livet:
        stripped = raw.strip()
        if raw == "":
            out.append("")
        elif _PRICE_RE.search(stripped):
            # Price — always orange, always indented in display
            out.append(f"  {YL}{stripped}{R}")
        elif raw.startswith((" ", "\t")):
            # Indented non-price line = ingredients
            wrapped = wrap_text(stripped, WRAP_WIDTH - 2)
            for line in wrapped:
                out.append(f"  {NW}{line}{R}")
        else:
            # Dish name — bold first line, normal for wrapped continuation
            wrapped = wrap_text(raw, WRAP_WIDTH)
            for i, line in enumerate(wrapped):
                out.append(f"{WH if i == 0 else NW}{line}{R}")
    return out


def _build_dn_block(dn: dict) -> list[str]:
    lines = [
        f"{MG}DALANISSEN{R}",
        f"{YL}155 kr / r\u00e4tt{R}",
        "",
        f"{WH}{dn['date']}{R}",
        f"{MG}──────────────────────────{R}",
        "",
    ]
    lines += _dn_items(dn["today"])
    if dn["always"]:
        lines += [f"{MG}── Serveras hela veckan ──{R}", ""]
        lines += _dn_items(dn["always"])
    return lines


def _build_livet_block(livet: list[str], date_str: str) -> list[str]:
    lines = [
        f"{CY}LIVET RESTAURANT SOLNA{R}",
        f"{YL}129 kr / r\u00e4tt{R}",
        "",
        f"{WH}{date_str}{R}",
        f"{CY}──────────────────────────{R}",
        "",
    ]
    lines += _livet_lines(livet)
    return lines


def build_menu_dalanissen(dn: dict) -> str:
    return "```ansi\n" + "\n".join(_build_dn_block(dn)) + "\n```"


def build_menu_livet(livet: list[str], date_str: str) -> str:
    return "```ansi\n" + "\n".join(_build_livet_block(livet, date_str)) + "\n```"


def build_combined_menu(dn: dict, livet: list[str]) -> list[str]:
    """Return [one_msg] if it fits in 2000 chars, else [dn_msg, livet_msg]."""
    separator = ["", f"{DGR}────────────────────────────{R}", ""]
    inner = _build_dn_block(dn) + separator + _build_livet_block(livet, dn["date"])
    combined = "```ansi\n" + "\n".join(inner) + "\n```"
    if len(combined) <= 2000:
        return [combined]
    return [build_menu_dalanissen(dn), build_menu_livet(livet, dn["date"])]


# ─── Bot Setup ─────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True


class BreakPointBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.active_timers: dict  = {}   # channel_id -> {task, message}
        self.locked_channels: set = set()
        self.ping_enabled: dict   = {}   # guild_id -> bool

    async def setup_hook(self):
        await self.tree.sync()
        print("Commands synced.")

    async def on_ready(self):
        print(f"BreakPointBot online as {self.user}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="the clock",
            )
        )

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id in self.locked_channels:
            try:
                await message.delete()
            except discord.Forbidden:
                pass


bot = BreakPointBot()


# ─── Timer Background Task ─────────────────────────────────────────────────

async def _delete_messages(msgs: list[discord.Message]) -> None:
    for m in msgs:
        try:
            await m.delete()
        except discord.HTTPException:
            pass


async def _auto_delete(msg: discord.Message, delay: int = 30) -> None:
    """Delete a message after delay seconds, silently ignore errors."""
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except discord.HTTPException:
        pass


async def run_timer(
    channel: discord.TextChannel,
    message: discord.Message,
    kind: str,
    channel_id: int,
    start_time: datetime.datetime,
    mention: str | None,
    menu_messages: list[discord.Message] | None = None,
):
    UPDATE_INTERVAL = 20  # seconds between edits
    menu_deleted = False

    while True:
        await asyncio.sleep(UPDATE_INTERVAL)

        timer = bot.active_timers.get(channel_id)
        if not timer:
            return

        now        = datetime.datetime.now()
        end_time   = timer["end_time"]
        total_secs = max((end_time - start_time).total_seconds(), 1)
        elapsed    = (now - start_time).total_seconds()
        remaining  = (end_time - now).total_seconds()

        # Delete menu when bar turns red (75% elapsed)
        if not menu_deleted and menu_messages and elapsed / total_secs >= 0.75:
            await _delete_messages(menu_messages)
            menu_deleted = True

        if remaining <= 0:
            break

        try:
            await message.edit(
                content=build_timer_msg(kind, int(remaining), int(total_secs), end_time)
            )
        except (discord.NotFound, discord.HTTPException):
            return

    try:
        await message.edit(content=build_done_msg(kind, mention))
    except (discord.NotFound, discord.HTTPException):
        pass

    bot.active_timers.pop(channel_id, None)


# ─── Slash Commands ────────────────────────────────────────────────────────

@bot.tree.command(name="break", description="Start a break timer (default 10 min)")
@app_commands.describe(
    minutes="Break length in minutes (default: 10)",
    end="End time as HH:MM, e.g. 14:30 — overrides minutes",
)
async def cmd_break(interaction: discord.Interaction, minutes: int = 10, end: str = None):
    await _start_timer(interaction, "BREAK", minutes, end)


@bot.tree.command(name="lunch", description="Start a lunch timer (default 60 min)")
@app_commands.describe(
    minutes="Lunch length in minutes (default: 60)",
    end="End time as HH:MM, e.g. 12:00 — overrides minutes",
)
async def cmd_lunch(interaction: discord.Interaction, minutes: int = 60, end: str = None):
    await _start_timer(interaction, "LUNCH", minutes, end)


async def _purge_channel(channel: discord.TextChannel) -> None:
    """Bulk-delete bot messages in channel. Silently handles errors."""
    try:
        await channel.purge(limit=100, check=lambda m: m.author == bot.user)
    except (discord.Forbidden, discord.HTTPException):
        pass


def _parse_end_time(end_str: str) -> datetime.datetime | None:
    """Parse HH:MM (or H:MM) into a datetime today. Returns tomorrow's time if already past."""
    for fmt in ("%H:%M", "%H.%M"):
        try:
            t = datetime.datetime.strptime(end_str.strip(), fmt)
            now = datetime.datetime.now()
            end = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if end <= now:
                end += datetime.timedelta(days=1)
            return end
        except ValueError:
            continue
    return None


async def _start_timer(interaction: discord.Interaction, kind: str, minutes: int, end: str | None = None):
    now = datetime.datetime.now()

    if end is not None:
        end_time = _parse_end_time(end)
        if end_time is None:
            await interaction.response.send_message(
                f"```ansi\n{RD}[ ERROR ]{R}  Invalid time — use HH:MM, e.g. 14:30.\n```",
                ephemeral=True,
            )
            return
        total_secs = int((end_time - now).total_seconds())
        if total_secs < 60:
            await interaction.response.send_message(
                f"```ansi\n{RD}[ ERROR ]{R}  End time must be at least 1 minute from now.\n```",
                ephemeral=True,
            )
            return
    else:
        if minutes < 1 or minutes > 480:
            await interaction.response.send_message(
                f"```ansi\n{RD}[ ERROR ]{R}  Duration must be 1-480 minutes.\n```",
                ephemeral=True,
            )
            return
        total_secs = minutes * 60
        end_time   = now + datetime.timedelta(seconds=total_secs)

    start_time = now
    ping_on    = bot.ping_enabled.get(interaction.guild_id, False)
    mention    = "@everyone" if ping_on else None

    # Cancel existing task (messages cleared by purge below)
    existing = bot.active_timers.pop(interaction.channel_id, None)
    if existing:
        existing["task"].cancel()

    # Defer EPHEMERALLY — the "thinking..." is private to the user so
    # channel.purge() won't touch it and followup won't 404.
    await interaction.response.defer(ephemeral=True)
    await _purge_channel(interaction.channel)

    menu_messages: list[discord.Message] = []

    if kind == "LUNCH":
        target = datetime.date.today()
        dn, livet = await asyncio.gather(cached_dalanisse(target), cached_livet(target))
        for content in build_combined_menu(dn, livet):
            m = await interaction.channel.send(content=content)
            menu_messages.append(m)

    # Use channel.send() (not followup) — followup references the original
    # deferred message which may have been purged on retry.
    timer_msg = await interaction.channel.send(
        content=build_timer_msg(kind, total_secs, total_secs, end_time)
    )

    # Dismiss the ephemeral interaction response
    try:
        await interaction.delete_original_response()
    except discord.HTTPException:
        pass

    task = asyncio.create_task(
        run_timer(interaction.channel, timer_msg, kind, interaction.channel_id, start_time, mention, menu_messages)
    )
    bot.active_timers[interaction.channel_id] = {
        "task": task,
        "message": timer_msg,
        "menu_messages": menu_messages,
        "end_time": end_time,
    }


@bot.tree.command(name="menu", description="Show lunch menu (default: both restaurants, today)")
@app_commands.describe(
    restaurant="Which restaurant to show (default: both)",
    day="Day offset within this week: 0=today, +1=tomorrow, -1=yesterday",
)
@app_commands.choices(restaurant=[
    app_commands.Choice(name="Dalanissen",             value="dalanissen"),
    app_commands.Choice(name="Livet Restaurant Solna", value="livet"),
])
async def cmd_menu(
    interaction: discord.Interaction,
    restaurant: str = "both",
    day: int = 0,
):
    if day < -4 or day > 4:
        await interaction.response.send_message(
            f"```ansi\n{RD}[ MENU ]{R}  Day offset must be between -4 and +4.\n```",
            ephemeral=True,
        )
        return

    target = get_target_date(day)
    if target is None:
        await interaction.response.send_message(
            f"```ansi\n{YL}[ MENU ]{R}  Please choose a menu within this week (Mon-Fri).\n```",
            ephemeral=True,
        )
        return

    # Always defer; "thinking..." stays hidden while we fetch
    await interaction.response.defer(ephemeral=True)

    # Fetch whichever restaurants are needed
    dn    = await cached_dalanisse(target) if restaurant in ("both", "dalanissen") else None
    livet = await cached_livet(target)     if restaurant in ("both", "livet")      else None

    if restaurant == "both":
        messages = build_combined_menu(dn, livet)
    elif restaurant == "dalanissen":
        messages = [build_menu_dalanissen(dn)]
    else:
        messages = [build_menu_livet(livet, date_sv(target))]

    # Always send menu via DM
    try:
        dm = await interaction.user.create_dm()
        for content in messages:
            await dm.send(content=content)
        # Post a brief ack in the channel, then auto-delete it after 30 s
        ack = await interaction.channel.send(
            f"```ansi\n{CY}[ MENU ]{R}  Sent to your DMs.\n```"
        )
        asyncio.create_task(_auto_delete(ack, 30))
        # Dismiss the ephemeral deferred interaction silently
        await interaction.followup.send(content="\u200b", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            f"```ansi\n{RD}[ MENU ]{R}  Could not DM you — enable DMs from server members.\n```",
            ephemeral=True,
        )


@bot.tree.command(name="ping", description="Toggle pings when a timer ends")
async def cmd_ping(interaction: discord.Interaction):
    gid       = interaction.guild_id
    new_state = not bot.ping_enabled.get(gid, False)
    bot.ping_enabled[gid] = new_state
    state_str = f"{GN}ON{R} — will ping @everyone" if new_state else f"{RD}OFF{R}"
    await interaction.response.send_message(
        f"```ansi\n{CY}[ BreakPointBot ]{R}  Pings are now {state_str}\n```",
        ephemeral=True,
    )


@bot.tree.command(name="lock", description="Lock this channel — only bot posts allowed (admin)")
@app_commands.checks.has_permissions(manage_channels=True)
async def cmd_lock(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in bot.locked_channels:
        bot.locked_channels.discard(cid)
        state = f"{RD}UNLOCKED{R}"
    else:
        bot.locked_channels.add(cid)
        state = f"{GN}LOCKED{R}"
    await interaction.response.send_message(
        f"```ansi\n{CY}[ BreakPointBot ]{R}  Channel is now {state}\n```",
        ephemeral=True,
    )


@bot.tree.command(name="extend", description="Add or remove minutes from the active timer")
@app_commands.describe(minutes="Minutes to add (e.g. 5) or remove (e.g. -5)")
async def cmd_extend(interaction: discord.Interaction, minutes: int):
    timer = bot.active_timers.get(interaction.channel_id)
    if not timer:
        await interaction.response.send_message(
            f"```ansi\n{YL}[ BreakPointBot ]{R}  No active timer in this channel.\n```",
            ephemeral=True,
        )
        return

    new_end = timer["end_time"] + datetime.timedelta(minutes=minutes)
    if new_end <= datetime.datetime.now() + datetime.timedelta(seconds=30):
        await interaction.response.send_message(
            f"```ansi\n{RD}[ ERROR ]{R}  Can't reduce timer past the current time.\n```",
            ephemeral=True,
        )
        return

    timer["end_time"] = new_end
    sign = "+" if minutes >= 0 else ""
    await interaction.response.send_message(
        f"```ansi\n{CY}[ BreakPointBot ]{R}  Timer {sign}{minutes} min — ends at {new_end.strftime('%H:%M')}.\n```",
        ephemeral=True,
    )


@bot.tree.command(name="stop", description="Cancel the active timer in this channel")
async def cmd_stop(interaction: discord.Interaction):
    existing = bot.active_timers.pop(interaction.channel_id, None)
    if not existing:
        await interaction.response.send_message(
            f"```ansi\n{YL}[ BreakPointBot ]{R}  No active timer here.\n```",
            ephemeral=True,
        )
        return
    existing["task"].cancel()
    await _purge_channel(interaction.channel)
    await interaction.response.send_message(
        f"```ansi\n{RD}[ timer stopped ]{R}\n```", ephemeral=True
    )


@bot.tree.command(name="help", description="Show all BreakPointBot commands")
async def cmd_help(interaction: discord.Interaction):
    def row(cmd: str, args: str, desc: str) -> str:
        return f"  {CY}{cmd}{R} {DIM}{args}{R}\n  {NW}{desc}{R}\n"

    lines = [
        "```ansi",
        f"{MG}BREAKPOINTBOT{R}  {DIM}-- commands --{R}",
        f"{MG}──────────────────────────────{R}",
        "",
        row("/break", "[minutes] [end]",
            "Start a break timer (default 10 min).\n"
            "  Use end: to set a stop time, e.g. end:14:30."),
        row("/lunch", "[minutes] [end]",
            "Start a lunch timer (default 60 min).\n"
            "  Posts today's lunch menu above the timer.\n"
            "  Use end: to set a stop time, e.g. end:12:00."),
        row("/extend", "<minutes>",
            "Add or remove minutes from the active timer.\n"
            "  e.g. /extend 5  or  /extend -5"),
        row("/stop", "",
            "Cancel the active timer and clear bot messages."),
        row("/menu", "[restaurant] [day]",
            "Send today's lunch menu to your DMs.\n"
            "  restaurant: dalanissen | livet (default: both)\n"
            "  day: -4 to +4 within this week (0 = today)"),
        row("/ping", "",
            "Toggle @everyone ping when a timer ends."),
        row("/lock", "",
            "Lock this channel (admin) -- auto-deletes non-bot messages."),
        row("/update", "",
            "Pull latest code from GitHub and restart (admin)."),
        row("/help", "",
            "Show this message."),
        "```",
    ]
    await interaction.response.send_message(
        "\n".join(lines), ephemeral=True
    )


@cmd_lock.error
async def lock_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "You need **Manage Channels** permission to use this.", ephemeral=True
    )


@bot.tree.command(name="update", description="Pull latest code from GitHub and restart (admin)")
@app_commands.checks.has_permissions(manage_guild=True)
async def cmd_update(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip() or "No output."
        ok = result.returncode == 0
    except FileNotFoundError:
        await interaction.followup.send(
            f"```ansi\n{RD}[ UPDATE ]{R}  git is not installed.\n```", ephemeral=True
        )
        return
    except Exception as e:
        await interaction.followup.send(
            f"```ansi\n{RD}[ UPDATE ]{R}  {e}\n```", ephemeral=True
        )
        return

    status = GN if ok else RD
    label  = "Update successful — restarting…" if ok else "Update failed."
    await interaction.followup.send(
        f"```ansi\n{status}[ UPDATE ]{R}  {label}\n\n{DIM}{output}{R}\n```",
        ephemeral=True,
    )

    if ok:
        # Small delay so the message is delivered before the process exits
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)


@cmd_update.error
async def update_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "You need **Manage Server** permission to use this.", ephemeral=True
    )


# ─── Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not found in .env")
    bot.run(TOKEN)
