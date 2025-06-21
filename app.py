import os
import logging
import gspread
from dotenv import load_dotenv
from telegram.constants import ParseMode
from oauth2client.service_account import ServiceAccountCredentials
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler, ContextTypes
)
from datetime import datetime
import json
from threading import Thread
import asyncio  # Needed for running coroutines from non-async functions

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("CancelItNowDB").sheet1

# States for ConversationHandler
NAME, COST, PRIORITY = range(3)

# Priorities with colors
priority_buttons = [
    ("🔴 High", "High"),
    ("🟡 Medium", "Medium"),
    ("🟢 Low", "Low")
]

# Main menu keyboard
main_menu_kb = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("➕ Add Subscription", callback_data="add"),
        InlineKeyboardButton("📂 View Subscriptions", callback_data="view")
    ],
    [
        InlineKeyboardButton("❌ Cancel Subscription", callback_data="cancel"),
        InlineKeyboardButton("📈 View Benefits", callback_data="benefits")
    ],
[InlineKeyboardButton("❓ Help", callback_data="help"),InlineKeyboardButton("🚧 Upcoming features", callback_data="upcoming")],
    [InlineKeyboardButton("📤 Share ", callback_data="share")]
])

def insert_row(user_id, username, name="", cost="", priority="", status="active"):
    sheet.append_row([str(user_id), username or "", name, str(cost), priority, status])

def get_user_subs(user_id):
    records = sheet.get_all_records()
    user_subs = []
    for i, row in enumerate(records):
        if str(row["user_id"]) == str(user_id) and row["status"].lower() == "active":
            row_num = i + 2  # +1 for header, +1 for 0-indexing
            user_subs.append({
                "name": row["name"],
                "cost": row["cost"],
                "priority": row["priority"],
                "row": row_num     # ✅ Store actual sheet row
            })
    return user_subs


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sheet.append_row([str(user.id), user.username or "", "", "", "", "passive"])
    await update.message.reply_text("""Why keep paying for what you don’t use?\n✨ You’re not alone — over 80% of people lose money on unused subscriptions.\nWe are here to help you flip the script.\n\n
👋 Welcome to *CancelItNowBot* — your personal assistant for cutting subscription clutter.

✅ Track everything you're paying for  
🧠 Reflect on what's *actually* worth it  
❌ Cancel wasteful services in seconds  
💰 Feel lighter — mentally and financially


Let’s turn confusion into clarity.
Let’s simplify your life.
One subscription at a time.\n

Start below 👇\n""", parse_mode=ParseMode.MARKDOWN
    )
    await update.message.reply_text("Click the button below to get started:", reply_markup=main_menu_kb)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    data = query.data

    if data == "add":
        await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="📌 What subscription do you want to add?")
        return NAME


    elif data == "view":
        subs = get_user_subs(user.id)
        if not subs:
            await query.message.reply_text("📭 No active subscriptions.")
        else:
            msg = "📋 Here’s a snapshot of your current *active* subscriptions:\n\n"
            for s in subs:
                color = "🔴" if s['priority'] == 'High' else "🟡" if s['priority'] == 'Medium' else "🟢"
                msg += (f"🔹 *{s['name']}*\n"
    			f"   💰 ₹{s['cost']} / month\n"
    			f"   🏷️ Priority: {color} {s['priority']}\n\n"
			)
            msg += f"🧘 _Review. Reflect. You’re already doing great._\n\n"

            await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

    elif data == "cancel":
        subs = get_user_subs(user.id)
        if not subs:
            await query.message.reply_text("📭 No active subscriptions to cancel.")
        else:
            kb = [[InlineKeyboardButton(f"{s['name']} | ₹{s['cost']} | {s['priority']}",
        callback_data=f"confirm_cancel:{s['row']}:{s['name']}:{s['cost']}"
    )]
    for s in subs]

            await query.message.reply_text("🔻 Select a subscription you want to cancel:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("confirm_cancel"):
        _, row_index, name, cost = data.split(":")
        context.user_data['row_index'] = int(row_index)
        context.user_data['cancel_name'] = name
        context.user_data['cancel_cost'] = cost
        context.user_data['from_cancel_flow'] = True  # Track cancel path
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Cancel", callback_data="do_cancel")],
            [InlineKeyboardButton("❌ No", callback_data="cancel_abort")],
        ])
        await query.message.reply_text(
            f"Are you sure you want to cancel '{name}' subscription?\n💸 It’s costing you ₹{cost} every month.",
            reply_markup=confirm_kb
        )

    elif data == "do_cancel":
        row = context.user_data['row_index']
        name = context.user_data['cancel_name']
        cost = int(context.user_data['cancel_cost'])
        sheet.update_cell(row, 6, "cancelled")
        await query.message.reply_text(
            f"✅ Subscription '{name}' has been cancelled.\n🎉 You just saved ₹{cost} monthly! That’s ₹{cost * 12} per year! 💰\n\n💪 _Keep going — smarter money is your new normal._",parse_mode=ParseMode.MARKDOWN
        )
        await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

    elif data == "benefits":
        subs = get_user_subs(user.id)
        if not subs:
            await query.message.reply_text("📭 No active subscriptions.")
        else:
            total = sum(int(s['cost']) for s in subs)
            count = len(subs)
            high = sum(1 for s in subs if s['priority'] == 'High')
            medium = sum(1 for s in subs if s['priority'] == 'Medium')
            low = sum(1 for s in subs if s['priority'] == 'Low')
            await query.message.reply_text(
                f"📊 Your Subscription Snapshot:\n\n"
                f"• Total Active: {count}\n"
                f"• Monthly Spend: ₹{total}\n"
                f"• Priority Breakdown:\n"
                f"🔴 High: {high}\n"
                f"🟡 Medium: {medium}\n"
                f"🟢 Low: {low}\n\n\n"
                f"💡 _Think: what can you cut to save more?_\n",parse_mode=ParseMode.MARKDOWN
            )
        await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

    elif data == "cancel_abort":
        cost = context.user_data.get("cancel_cost", "0")
        await query.message.reply_text(
        "😌 No worries.\n"
        "Your subscription is safe for now.\n\n"
        f"💡 It currently costs you *₹{cost} monthly*.\n"
        "\nTake your time to decide — I'm here whenever you're ready to optimize your expenses 💸💪",
        parse_mode=ParseMode.MARKDOWN
    )
        await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)


    elif data == "menu":

        await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

    elif data == "help":
        await query.message.reply_text(
        "🤖 *CancelItNowBot Help Guide*\n\n"
        "Here's what I can do for you:\n\n"
        "🔹 *Add Subscription* – Add a new subscription and track the recurring cost\n"
        "🔹 *View Subscriptions* – See all your active services\n"
        "🔹 *Cancel Subscription* – Cancel a subscription\n"
        "🔹 *View Benefits* – Get insights into where your money goes\n\n"
        "I'm here to simplify your digital expenses and help you cut waste! 💸",
        parse_mode=ParseMode.MARKDOWN)
        await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

    elif data == "share":
        await query.message.reply_text(
        "❤️ Love CancelItNowBot?\n\n"
        "Invite your friends to manage their subscriptions too!\n"
        "Click below to share:\n"
        "https://t.me/cancelitnowbot")
        await query.message.reply_text("📍 What would you like to do now?",reply_markup=main_menu_kb)

    elif data == "upcoming":
    	await query.message.reply_text(
        "🚀 *Coming Soon to CancelItNowBot:*\n\n"
        "🌐 *Multilanguage Support* – Use the bot in your native language!\n"
        "🧠 *Smart Recommendations* – AI will suggest what to cancel or keep\n"
        "📅 *Reminder Alerts* – Monthly nudges before recurring payments\n"
        "📊 *Monthly Summary Reports* – Track your total savings & expenses\n"
        "👥 *Referral Rewards* – Invite friends, unlock perks!\n"
        "💳 *Budget Planning Tools* – Set monthly budgets & auto warnings\n"
        "🤝 *Exclusive Discounts* – Save more with partner deals\n"
        "🔒 *Private Mode* – Keep your subscriptions 100% private\n"
        "📥 *Import from Email* – Auto-detect subscriptions from receipts\n"
        "📌 *Custom Notes* – Add notes or cancellation deadlines per subscription\n\n"
        "We're just getting started — thank you for growing with us 💚",
        parse_mode=ParseMode.MARKDOWN)
    	await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)


    return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("💰 How much does it cost you monthly?")
    return COST

async def get_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cost = int(update.message.text)
        if not str(cost).isdigit() or int(cost) <= 0 or int(cost) > 100000:
            raise ValueError
        context.user_data['cost'] = cost
        kb = [[InlineKeyboardButton(text, callback_data=f"priority:{val}")] for text, val in priority_buttons]
        await update.message.reply_text("""📊 How important is this to you?\n
_(Be honest — we won’t judge)_\n""", reply_markup=InlineKeyboardMarkup(kb),parse_mode=ParseMode.MARKDOWN)
        return PRIORITY
    except ValueError:
        await update.message.reply_text("❗ Please enter a valid monthly cost (1–100000).")
        return COST

async def get_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    priority = query.data.split(":")[1]
    context.user_data['priority'] = priority

    u = query.from_user
    insert_row(u.id, u.username, context.user_data['name'], context.user_data['cost'], priority)

    await query.message.reply_text("✅ Subscription saved successfully!")
    await query.message.reply_text("📍 What would you like to do now?", reply_markup=main_menu_kb)

    return ConversationHandler.END

from flask import Flask, request

flask_app = Flask(__name__)
bot_app = None  # Will hold the Telegram Application object

@flask_app.route('/')
def index():
    return 'CancelItNowBot is running via webhook 🎯', 200

@flask_app.route('/healthz')
def health():
    return 'I am alive', 200

@flask_app.route('/webhook', methods=['GET','POST'])
def webhook():
    if request.method == 'GET':
        return 'OK', 200  # Health check response
    print("✅ /webhook route triggered")
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return 'OK', 200
# Run bot in a background thread
def run_bot():
    global bot_app

    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(handle_buttons)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cost)],
            PRIORITY: [CallbackQueryHandler(get_priority, pattern="^priority:")]
        },
        fallbacks=[]
    )

    bot_app.add_handler(conv_handler)
    bot_app.add_handler(CallbackQueryHandler(handle_buttons))
    bot_app.add_handler(CommandHandler("menu", main_menu))

    # Register webhook with Telegram
    asyncio.run(bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"))

    print("✅ Telegram webhook registered")

def main():
    Thread(target=run_bot).start()
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()