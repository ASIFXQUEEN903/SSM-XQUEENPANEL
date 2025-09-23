import os
import logging
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from utils import call_tempora_api, get_prices

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SERVICE = "telegram"

# Countries & Operators
COUNTRY_OPERATORS = {
    "USA": {"id": "1", "operators": [1, 8, 9, 11]},
    "South Africa": {"id": "2", "operators": [9, 11, 6]}
}

# Store active activations
active_activations = {}

# /start command
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    text = f"Hello {user.first_name}!\nWelcome to TemporaSMS Bot\nUse the menu below."
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
    user_id = query.from_user.id

    if data == "check_balance":
        resp = call_tempora_api("getBalance")
        query.edit_message_text(f"Tempora Balance:\n`{resp}`", parse_mode="Markdown")

    elif data == "request_recharge":
        query.edit_message_text("Send the amount you want to request (e.g. 100).")

    elif data == "buy_number":
        keyboard = [[InlineKeyboardButton(name, callback_data=f"country_{name}")] for name in COUNTRY_OPERATORS.keys()]
        query.edit_message_text("Select Country:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("country_"):
        country_name = data.split("_")[1]
        country_info = COUNTRY_OPERATORS[country_name]
        country_id = country_info["id"]

        # Get prices for operators
        keyboard = []
        for op in country_info["operators"]:
            price_info = get_prices(country_id, op)
            price_text = "N/A"
            if price_info and country_id in price_info:
                for key in price_info[country_id]:
                    price_text = list(price_info[country_id][key].keys())[0]
                    break
            keyboard.append([InlineKeyboardButton(f"Operator {op} 💰{price_text}", callback_data=f"buy_{country_name}_{op}")])
        query.edit_message_text("Select Operator:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        _, country_name, op_id = data.split("_")
        op_id = int(op_id)
        country_id = COUNTRY_OPERATORS[country_name]["id"]

        # Buy number
        resp = call_tempora_api("getNumber", {"service": SERVICE, "country": country_id, "operator": op_id})
        if resp:
            if "ACCESS_NUMBER" in resp:
                order_id = resp.split(":")[1]
                active_activations[user_id] = {"order_id": order_id, "otp_received": False}
                keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel")]]
                query.edit_message_text(f"Number bought!\n{resp}\nWaiting for OTP...", reply_markup=InlineKeyboardMarkup(keyboard))
                threading.Thread(target=check_otp, args=(context.bot, user_id, order_id), daemon=True).start()
            elif "NO_NUMBERS" in resp:
                query.edit_message_text("Out of stock for this operator.")
            else:
                query.edit_message_text(f"Error buying number:\n{resp}")
        else:
            query.edit_message_text("Error contacting API.")

    elif data == "cancel":
        if user_id in active_activations:
            if active_activations[user_id]["otp_received"]:
                query.edit_message_text("OTP already received. Cannot cancel.")
            else:
                order_id = active_activations[user_id]["order_id"]
                cancel_resp = call_tempora_api("setStatus", {"status": 8, "id": order_id})
                query.edit_message_text(f"Activation cancelled.\n{cancel_resp}")
                del active_activations[user_id]
        else:
            query.edit_message_text("No active activation to cancel.")

# Check OTP in background
def check_otp(bot, user_id, order_id):
    for _ in range(120):  # check every 1 sec up to 2 min
        resp = call_tempora_api("getStatus", {"id": order_id})
        if resp and "STATUS_OK" in resp:
            otp = resp.split(":")[1]
            bot.send_message(chat_id=user_id, text=f"OTP Received: {otp}")
            active_activations[user_id]["otp_received"] = True
            return
        time.sleep(1)

# Text messages (recharge)
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
        update.message.reply_text(f"Added {amount} to {user_id} (placeholder).")
        context.bot.send_message(chat_id=user_id, text=f"Your account has been credited with {amount}.")
    except Exception:
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
