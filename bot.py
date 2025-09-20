import os
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from utils import call_tempora_api

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Country codes
COUNTRIES = {"USA":"1", "SOUTH_AFRICA":"3"}

# -----------------------
# /start command
# -----------------------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    text = f"Hello {user.first_name}!\nWelcome to TemporaSMS Bot\nUse the menu below."
    keyboard = [
        [InlineKeyboardButton("Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("Buy Number", callback_data="buy_number")],
        [InlineKeyboardButton("Request Recharge", callback_data="request_recharge")]
    ]
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# -----------------------
# Button handler
# -----------------------
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "check_balance":
        resp = call_tempora_api("getBalance")
        if resp:
            query.edit_message_text(f"Tempora Balance:\n`{resp}`", parse_mode="Markdown")
        else:
            query.edit_message_text("Error fetching balance.")

    elif data == "request_recharge":
        query.edit_message_text("Send the amount you want to request (e.g. 100).")

    elif data == "buy_number":
        keyboard = [
            [InlineKeyboardButton("🇺🇸 USA", callback_data="buy_USA")],
            [InlineKeyboardButton("🇿🇦 South Africa", callback_data="buy_SOUTH_AFRICA")]
        ]
        query.edit_message_text("Select country to buy number:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        country_name = data.split("_")[1]
        country_code = COUNTRIES[country_name]

        # Get price
        price_resp = call_tempora_api("getPrices", {"country":country_code, "operator":1})
        if price_resp:
            first_service = list(price_resp[country_code].keys())[0]
            price = list(price_resp[country_code][first_service].keys())[0]

            keyboard = [
                [InlineKeyboardButton(f"Buy Number ({price})", callback_data=f"buy_confirm_{country_name}")],
                [InlineKeyboardButton("Cancel", callback_data="cancel_buy")]
            ]
            query.edit_message_text(f"{country_name} number price: {price}", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            query.edit_message_text("Error fetching price.")

    elif data.startswith("buy_confirm_"):
        country_name = data.split("_")[2]
        country_code = COUNTRIES[country_name]

        # Buy number
        buy_resp = call_tempora_api("getNumber", {"service":"telegram","country":country_code,"operator":1})
        if buy_resp and "ACCESS_NUMBER" in buy_resp:
            _, order_id, number = buy_resp["ACCESS_NUMBER"].split(":")
            waiting_msg = query.message.reply_text(f"⏳ Waiting for OTP for number {number}…")

            # Poll OTP for 2 minutes
            otp = None
            for _ in range(24):
                time.sleep(5)
                otp_resp = call_tempora_api("getStatus", {"id":order_id})
                if otp_resp and "STATUS_OK" in otp_resp:
                    otp = otp_resp["STATUS_OK"]
                    break

            if otp:
                waiting_msg.edit_text(f"✅ OTP received for {number}: {otp}")
            else:
                waiting_msg.edit_text(f"❌ Activation Cancelled for {number}")
        else:
            query.message.reply_text(f"❌ Error buying number: {buy_resp}")

    elif data == "cancel_buy":
        query.edit_message_text("❌ Activation Cancelled by user")

# -----------------------
# Text handler (recharge)
# -----------------------
def text_handler(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if text.isdigit():
        amount = float(text)
        context.bot.send_message(chat_id=ADMIN_ID,
                                 text=f"Recharge request from @{update.effective_user.username or update.effective_user.id}: {amount}\nUse /addbalance <user_id> <amount> to approve.")
        update.message.reply_text("Recharge request sent to admin for approval.")
    else:
        update.message.reply_text("Unknown text. Use menu or commands.")

# -----------------------
# /addbalance admin command
# -----------------------
def addbalance_cmd(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("You are not authorized.")
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
    except Exception:
        update.message.reply_text("Invalid arguments.")

# -----------------------
# MAIN
# -----------------------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_handler))
    dp.add_handler(CommandHandler("addbalance", addbalance_cmd))

    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
