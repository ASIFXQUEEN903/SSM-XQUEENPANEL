import os
import logging
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from utils import call_tempora_api, get_operators, get_prices, get_countries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

COUNTRY_CODES = {"USA": "1", "South Africa": "2"}

user_sessions = {}  # Temporary store for selected country/operator

# /start
def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("Buy Number", callback_data="buy_number")],
        [InlineKeyboardButton("Request Recharge", callback_data="request_recharge")]
    ]
    update.message.reply_text("Welcome to TemporaSMS Bot!", reply_markup=InlineKeyboardMarkup(keyboard))

# Button handler
def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_balance":
        resp = call_tempora_api("getBalance")
        query.edit_message_text(f"Tempora Balance:\n`{resp}`", parse_mode="Markdown")

    elif data == "request_recharge":
        query.edit_message_text("Send the amount you want to request (e.g., 100).")

    elif data == "buy_number":
        # Show countries
        keyboard = []
        for country in COUNTRY_CODES:
            keyboard.append([InlineKeyboardButton(country, callback_data=f"country_{country}")])
        query.edit_message_text("Select country:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("country_"):
        country_name = data.split("_",1)[1]
        user_sessions[user_id] = {"country": COUNTRY_CODES[country_name]}
        operators = get_operators()
        if not operators:
            query.edit_message_text("Failed to get operators.")
            return
        keyboard = []
        for op_name, op_id in operators.items():
            keyboard.append([InlineKeyboardButton(f"{op_name}", callback_data=f"operator_{op_id}")])
        query.edit_message_text(f"Select operator for {country_name}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("operator_"):
        op_id = data.split("_",1)[1]
        user_sessions[user_id]["operator"] = op_id
        country = user_sessions[user_id]["country"]
        prices = get_prices(country, op_id)
        if not prices:
            query.edit_message_text("Failed to get prices.")
            return
        keyboard = []
        # Flatten price dict
        for service, service_prices in prices[country].items():
            for price, price_id in service_prices.items():
                keyboard.append([InlineKeyboardButton(f"{service} - {price}", callback_data=f"buy_{service}_{price}")])
        query.edit_message_text("Select service & price:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        _, service, price = data.split("_")
        session = user_sessions.get(user_id, {})
        country = session.get("country")
        operator = session.get("operator")
        resp = call_tempora_api("getNumber", {"service": service, "country": country, "operator": operator})
        if resp and "ACCESS_NUMBER" in resp:
            parts = resp.split(":")
            order_id = parts[1]
            number = parts[2]
            query.edit_message_text(f"Number bought: {number}\nWaiting for OTP (2 min max)...")
            start_time = time.time()
            while time.time() - start_time < 120:
                otp_resp = call_tempora_api("getStatus", {"id": order_id})
                if otp_resp and "STATUS_OK" in otp_resp:
                    otp = otp_resp.split(":")[1]
                    query.edit_message_text(f"OTP received: {otp}")
                    return
                time.sleep(5)
            query.edit_message_text("Timeout reached. You can cancel this activation on website.")
        else:
            query.edit_message_text(f"Failed to get number: {resp}")

# Text handler (recharge)
def text_handler(update: Update, context):
    text = update.message.text.strip()
    if text.isdigit():
        amount = float(text)
        context.bot.send_message(chat_id=ADMIN_ID,
                                 text=f"Recharge request from @{update.effective_user.username or update.effective_user.id}: {amount}\nUse /addbalance <user_id> <amount> to approve.")
        update.message.reply_text("Recharge request sent to admin for approval.")
    else:
        update.message.reply_text("Unknown text. Use menu or commands.")

# Admin addbalance
def addbalance_cmd(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("Unauthorized.")
        return
    if len(context.args) < 2:
        update.message.reply_text("Usage: /addbalance <user_id> <amount>")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        update.message.reply_text(f"Added {amount} to {user_id} (placeholder).")
        context.bot.send_message(chat_id=user_id, text=f"Your account has been credited with {amount}.")
    except Exception as e:
        update.message.reply_text("Invalid arguments.")

def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(CommandHandler("addbalance", addbalance_cmd))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
