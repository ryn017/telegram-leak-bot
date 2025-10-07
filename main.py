#!/usr/bin/env python3
"""
main.py - Leak-Lookup Telegram bot (Advanced)
- Send an email to the bot and it replies with breach details (sites, dates, data types).
- Uses LEAKLOOKUP_KEY and TELEGRAM_TOKEN from environment (.env when testing locally).
Note: Fill .env locally with your tokens; DO NOT commit secrets to a public repo.
"""
import os, time, requests, logging, json, re
from telegram.constants import ParseMode
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# load .env (if present locally)
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
LEAKLOOKUP_KEY = os.getenv("LEAKLOOKUP_KEY")
LEAKLOOKUP_BASE = os.getenv("LEAKLOOKUP_BASE", "https://leak-lookup.com/api/search")

if not TELEGRAM_TOKEN:
    raise SystemExit("Set TELEGRAM_TOKEN in environment (.env) before running.")
if not LEAKLOOKUP_KEY:
    print("Warning: LEAKLOOKUP_KEY not set. The bot may not return results until key is configured.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leaklookup-bot")

HEADERS = {"Accept":"application/json"}
# Some Leak-Lookup setups prefer key param; adjust according to provider docs
PARAM_KEY_NAME = os.getenv("LEAKLOOKUP_PARAM_NAME", "key")  # sometimes 'key' or 'api_key'

# helper: call leak-lookup API
# --- leak-lookup query helper (replace the old function with this) ---
LEAKLOOKUP_KEY = os.getenv("LEAKLOOKUP_KEY")

def leaklookup_query(email):
    """
    Query Leak-Lookup API and return (data, error)
    - returns (data_dict, None) on success
    - returns (None, error_message) on failure
    """
    url = "https://leak-lookup.com/api/search"
    # if your provider expects a different param name, change "key" -> "api_key"
    params = {
        "key": LEAKLOOKUP_KEY,
        "type": "email",
        "query": email
    }

    if not LEAKLOOKUP_KEY:
        return None, "No API key set (LEAKLOOKUP_KEY missing)"

    try:
        r = requests.get(url, params=params, timeout=15)
    except Exception as e:
        return None, f"Request failed: {e}"

    # Non-200 HTTP status
    if r.status_code != 200:
        # Return first part of body so we don't flood things
        return None, f"HTTP {r.status_code}: {r.text[:400]}"

    # Parse JSON safely
    try:
        data = r.json()
    except Exception as e:
        return None, f"Invalid JSON response: {e} - {r.text[:300]}"

    # API-level error field (if provider uses it)
    if isinstance(data, dict) and data.get("error"):
        msg = data.get("message", "Unknown API error")
        return None, f"API error: {msg}"

    # Success — return parsed JSON
    return data, None
# --- end leak-lookup helper ---

# friendly formatting helpers
def fmt_breach_item(item):
    # item may vary; try common keys
    name = item.get("source") or item.get("site") or item.get("domain") or item.get("Name") or "unknown"
    date = item.get("date") or item.get("BreachDate") or item.get("created_at") or item.get("publish_date") or ""
    data_classes = item.get("data", []) or item.get("DataClasses", []) or item.get("types", [])
    if isinstance(data_classes, dict):
        # some providers return dict of fields
        data_classes = list(data_classes.keys())
    # ensure list of strings
    data_classes = [str(x) for x in (data_classes or [])]
    return {"name": name, "date": date, "data": data_classes, "raw": item}

def summarize_results(resp_json):
    # normalize common structures
    results = []
    if isinstance(resp_json, dict):
        # try a few keys
        for key in ("results","data","items","matches","breaches"):
            if key in resp_json and isinstance(resp_json[key], list):
                for it in resp_json[key]:
                    results.append(fmt_breach_item(it))
                break
        else:
            # maybe top-level is a mapping of site->list
            # e.g., { "site": [...] }
            for k,v in resp_json.items():
                if isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict):
                            results.append(fmt_breach_item(it))
    elif isinstance(resp_json, list):
        for it in resp_json:
            if isinstance(it, dict):
                results.append(fmt_breach_item(it))
    return results

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 LeakLookup Bot ready. Send an email address (plain text) to check breaches. Only check emails you own or have permission for.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start - start\n/help - help\n/add email - add to track (not implemented here)\nJust send an email to check once.")

def is_likely_email(s):
    s = s.strip()
    return "@" in s and "." in s.split("@")[-1]

async def handle_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    chat_id = update.effective_chat.id
    if not is_likely_email(txt):
        await update.message.reply_text("That doesn't look like an email address. Send like: user@example.com")
        return
    email = txt.lower()

# --- TEST MODE SNIPPET: remove after testing ---
if "breach-test" in email:
    await update.message.reply_text(
        f"⚠️ (SIMULATED) Leak report for `{email}`:\n• site: example-breach.com\n• date: 2020-01-01\n• data exposed: emails, passwords",
        parse_mode=ParseMode.MARKDOWN
    )
    return
# --- end test snippet ---


await update.message.reply_text(f"🔍 Checking leaks for: {email} ...")
await update.message.reply_text(f"🔍 Checking leaks for: {email} ...")
resp, err = leaklookup_query(email)
if err:
    await update.message.reply_text(f"❌ API error: {err}")
    return
    if err:
        await update.message.reply_text(f"❌ API error: {err}")
        return
    # summarize results
    results = summarize_results(resp)
    if not results:
        await update.message.reply_text(f"✅ No public results found for `{email}` (via Leak-Lookup).", parse_mode=ParseMode.MARKDOWN)
        return
    # build reply message with details
    lines = [f"⚠️ Leak report for `{email}`\nFound {len(results)} item(s):\n"]
    for r in results[:12]:
        lines.append(f"*Site:* {r['name']}  \n*Date:* {r['date'] or 'unknown'}  \n*Data exposed:* {', '.join(r['data']) if r['data'] else 'unknown'}\n")
    lines.append("\n_Suggested actions:_ Change passwords, enable app-based 2FA, check financial accounts if payment data exposed.")
    msg = "\n".join(lines)
    # send in chunks if long
    try:
        for chunk in [msg[i:i+3000] for i in range(0, len(msg), 3000)]:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.exception("Failed sending message")
        await update.message.reply_text("Error sending long reply; try tracking fewer results.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_check))
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == '__main__':
    main()
import threading
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Run flask in a separate thread
threading.Thread(target=run_flask).start()

# Your bot code
import telebot
bot = telebot.TeleBot("YOUR_TOKEN")

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Bot is working!")

bot.polling()
