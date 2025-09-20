import os
import logging
import time
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from utils import call_tempora_api

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config from environment
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Countries mapping
COUNTRIES = {
    "USA": "1",
    "South Africa": "2"
}

# Services example (you can add more)
SERVICES = {
    "Telegram": "telegram"
}

# --- Start command ---
def start(update: Update, context):
    user = update.effective_user
    text = f"Hello {user.first_name}!\nWelcome to TemporaSMS Bot\nUse the menu below."
    keyboard = [
        [InlineKeyboardButton("Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("Buy Number", callback_data="buy_number")],
        [InlineKeyboardButton("Request Recharge", callback_data="request_recharge")]
    ]
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Button clicks ---
def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "check_balance":
        resp = call_tempora_api("getBalance")
        query.edit_message_text(f"Tempora Balance:\n`{resp}`", parse_mode="Markdown")

    elif data == "request_recharge":
        query.edit_message_text("Send the amount you want to request (e.g. 100).")

    elif data == "buy_number":
        keyboard = [
            [InlineKeyboardButton("USA", callback_data="country_USA")],
            [InlineKeyboardButton("South Africa", callback_data="country_South Africa")]
        ]
        query.edit_message_text("Select Country:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("country_"):
        country_name = data.split("_")[1]
        country_code = COUNTRIES.get(country_name)
        if not country_code:
            query.edit_message_text("Invalid country selected.")
            return

        # Fetch prices
        resp = call_tempora_api("getPrices", {"country": country_code, "operator": 1})
        if len(resp) > 4000:  # Telegram message too long
            with open("prices.txt", "w") as f:
                f.write(resp)
            context.bot.send_document(chat_id=query.message.chat_id, document=open("prices.txt", "rb"))
            query.edit_message_text(f"Prices sent as file for {country_name}. Click below to buy.")
        else:
            query.edit_message_text(f"Prices for {country_name}:\n`{resp}`\nClick below to buy number.", parse_mode="Markdown")

        # Add Buy button
        buy_button = [[InlineKeyboardButton("Buy Telegram Number", callback_data=f"buy_{country_name}_Telegram")]]
        query.message.reply_text("Click to buy:", reply_markup=InlineKeyboardMarkup(buy_button))

    elif data.startswith("buy_"):
        parts = data.split("_")
        country_name = parts[1]
        service_name = parts[2]
        service = SERVICES.get(service_name)
        country_code = COUNTRIES.get(country_name)
        if not service or not country_code:
            query.edit_message_text("Invalid selection.")
            return

        # Request number
        resp = call_tempora_api("getNumber", {"service": service, "country": country_code, "operator": 1})
        if "ACCESS_NUMBER" not in resp:
            query.edit_message_text(f"Failed to get number:\n`{resp}`", parse_mode="Markdown")
            return

        parts = resp.split(":")
        order_id = parts[1]
        number = parts[2]

        msg = query.edit_message_text(f"Number received: {number}\nWaiting for OTP... ⏳")

        # Start OTP polling in separate thread
        Thread(target=poll_otp, args=(context, query.message.chat_id, order_id, msg.message_id)).start()

# --- OTP Polling ---
def poll_otp(context, chat_id, order_id, msg_id):
    start_time = time.time()
    while time.time() - start_time < 120:  # 2 min
        resp = call_tempora_api("getStatus", {"id": order_id})
        if resp.startswith("STATUS_OK"):
            otp = resp.split(":")[1]
            context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                          text=f"OTP received ✅: {otp}")
            return
        time.sleep(5)
    # Timeout
    context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Activation cancelled ❌ (OTP not received)")

# --- Text messages (for recharge) ---
def text_handler(update: Update, context):
    text = update.message.text.strip()
    if text.isdigit():
        amount = float(text)
        context.bot.send_message(chat_id=ADMIN_ID,
                                 text=f"Recharge request from @{update.effective_user.username or update.effective_user.id}: {amount}\nUse /addbalance <user_id> <amount> to approve.")
        update.message.reply_text("Recharge request sent to admin for approval.")
    else:
        update.message.reply_text("Unknown text. Use menu or commands.")

# --- /addbalance admin command ---
def addbalance_cmd(update: Update, context):
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

# --- Main ---
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
