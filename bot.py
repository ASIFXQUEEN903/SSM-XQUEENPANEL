import os
import logging
import json
import time
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, Filters

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEMPORA_API_KEY = os.getenv("TEMPORA_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TEMPORA_BASE = "https://api.temporasms.com/stubs/handler_api.php"

# Country codes mapping
COUNTRIES = {
    "USA": "22",  # replace with actual Tempora country code
    "South Africa": "8"  # replace with actual Tempora country code
}

def call_tempora(params: dict):
    params = dict(params)
    params.setdefault("api_key", TEMPORA_API_KEY)
    try:
        r = requests.get(TEMPORA_BASE, params=params, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.exception("Tempora API error")
        return None

# Start command
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    text = f"Hello {user.first_name}!\nWelcome to TemporaSMS Bot"
    keyboard = [
        [InlineKeyboardButton("Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("Buy Number", callback_data="buy_number")],
        [InlineKeyboardButton("Request Recharge", callback_data="request_recharge")]
    ]
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# Button handler
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "check_balance":
        resp = call_tempora({"action": "getBalance"})
        query.edit_message_text(f"Balance:\n`{resp}`", parse_mode="Markdown")

    elif data == "request_recharge":
        query.edit_message_text("Send the amount you want to request (e.g. 100).")

    elif data == "buy_number":
        # show country buttons
        keyboard = [
            [InlineKeyboardButton("USA", callback_data="price_USA")],
            [InlineKeyboardButton("South Africa", callback_data="price_South Africa")]
        ]
        query.edit_message_text("Select Country:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("price_"):
        country_name = data.split("_")[1]
        country_code = COUNTRIES.get(country_name)
        if not country_code:
            query.edit_message_text("Country code not found.")
            return

        resp = call_tempora({"action": "getPrices", "country": country_code, "operator": 1})
        if resp:
            # truncate long response
            display_text = resp
            if len(resp) > 400:
                display_text = resp[:400] + "..."
            # show Buy button
            keyboard = [
                [InlineKeyboardButton("Buy Number", callback_data=f"buy_{country_name}")]
            ]
            query.edit_message_text(f"Prices for {country_name}:\n{display_text}",
                                    reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            query.edit_message_text("Failed to fetch prices.")

    elif data.startswith("buy_"):
        country_name = data.split("_")[1]
        country_code = COUNTRIES.get(country_name)
        resp = call_tempora({"action": "getNumber", "service": "telegram", "country": country_code, "operator": 1})
        if resp:
            # parse activation ID & number
            parts = resp.split(":")
            if len(parts) >= 3 and parts[0] == "ACCESS_NUMBER":
                order_id = parts[1]
                number = parts[2]
                query.edit_message_text(f"Number bought: {number}\nWaiting for OTP...")
                # poll OTP for 2 min
                otp = None
                for _ in range(12):
                    time.sleep(10)
                    status = call_tempora({"action": "getStatus", "id": order_id})
                    if status and status.startswith("STATUS_OK"):
                        otp = status.split(":")[1]
                        break
                if otp:
                    query.edit_message_text(f"Number: {number}\nOTP Received: {otp}")
                else:
                    query.edit_message_text(f"Number: {number}\nOTP not received / cancelled.")
            else:
                query.edit_message_text(f"Failed to buy number:\n{resp}")
        else:
            query.edit_message_text("Failed to buy number from API.")

# Text messages (for recharge)
def text_handler(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if text.isdigit():
        amount = float(text)
        context.bot.send_message(chat_id=ADMIN_ID,
                                 text=f"Recharge request from @{update.effective_user.username or update.effective_user.id}: {amount}\nUse /addbalance <user_id> <amount> to approve.")
        update.message.reply_text("Recharge request sent to admin for approval.")
    else:
        update.message.reply_text("Unknown text. Use menu or commands.")

# /addbalance admin command
def addbalance_cmd(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return
    if len(context.args) < 2:
        update.message.reply_text("Usage: /addbalance <user_id> <amount>")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        # TODO: update MongoDB balance here
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
