import os
import time
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, Filters

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
MONGO_URL = os.getenv("MONGO_URL", "MONGO_URL_HERE")
TEMPORA_API_KEY = os.getenv("TEMPORA_API_KEY", "TEMPORA_API_KEY_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TEMPORA_BASE = "https://api.temporasms.com/stubs/handler_api.php"

# Country mapping
COUNTRIES = {
    "USA": "1",
    "SOUTH_AFRICA": "8"
}

# Helper function to call Tempora API
def call_tempora_api(action, extra_params=None):
    params = {"action": action, "api_key": TEMPORA_API_KEY}
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get(TEMPORA_BASE, params=params, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.exception("Tempora API request failed")
        return None

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

    if data == "check_balance":
        resp = call_tempora_api("getBalance")
        if resp:
            query.edit_message_text(f"Tempora Balance:\n`{resp}`", parse_mode="Markdown")
        else:
            query.edit_message_text("❌ Error fetching balance. See logs.")

    elif data == "request_recharge":
        query.edit_message_text("Send the amount you want to request (e.g. 100).")

    elif data == "buy_number":
        # Show USA + South Africa buttons
        keyboard = [
            [InlineKeyboardButton("USA", callback_data="buy_price_USA")],
            [InlineKeyboardButton("South Africa", callback_data="buy_price_SOUTH_AFRICA")]
        ]
        query.edit_message_text("Select country to buy number:", reply_markup=InlineKeyboardMarkup(keyboard))

    # Price buttons
    elif data.startswith("buy_price_"):
        country_name = data.split("_")[2]
        country_code = COUNTRIES.get(country_name)
        if not country_code:
            query.edit_message_text("❌ Country not supported.")
            return

        # Fetch price
        price_resp = call_tempora_api("getPrices", {"country": country_code, "operator": 1})
        if price_resp:
            query.edit_message_text(
                f"Current price for {country_name}: `{price_resp}`\nClick confirm to buy number.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Confirm Buy", callback_data=f"buy_confirm_{country_name}")]
                ])
            )
        else:
            query.edit_message_text("❌ Error fetching price.")

    # Confirm buy
    elif data.startswith("buy_confirm_"):
        parts = data.split("_")
        if len(parts) != 3:
            query.edit_message_text("❌ Invalid confirmation callback.")
            return

        country_name = parts[2]
        country_code = COUNTRIES.get(country_name)
        if not country_code:
            query.edit_message_text("❌ Country not supported.")
            return

        # Buy number
        buy_resp = call_tempora_api("getNumber", {"service": "telegram", "country": country_code, "operator": 1})
        if buy_resp and "ACCESS_NUMBER" in buy_resp:
            try:
                _, order_id, number = buy_resp.split(":")
            except Exception:
                query.edit_message_text(f"❌ Unexpected API response: {buy_resp}")
                return

            waiting_msg = query.message.reply_text(f"⏳ Waiting for OTP for number {number}…")

            # Poll OTP for 2 minutes
            otp = None
            for _ in range(24):
                time.sleep(5)
                otp_resp = call_tempora_api("getStatus", {"id": order_id})
                if otp_resp and isinstance(otp_resp, str) and "STATUS_OK" in otp_resp:
                    otp = otp_resp.split(":")[1]  # Extract OTP from STATUS_OK:1234
                    break

            if otp:
                waiting_msg.edit_text(f"✅ OTP received for {number}: {otp}")
            else:
                waiting_msg.edit_text(f"❌ Activation Cancelled for {number}")
        else:
            query.message.reply_text(f"❌ Error buying number: {buy_resp}")

# /buy command (text command fallback)
def buy_handler(update: Update, context: CallbackContext):
    parts = context.args
    if len(parts) < 2:
        update.message.reply_text("Usage: /buy <service> <country>")
        return
    service = parts[0]
    country = parts[1]
    resp = call_tempora_api("getNumber", {"service": service, "country": country, "operator": 1})
    if resp:
        update.message.reply_text(f"API Response:\n`{resp}`", parse_mode="Markdown")
    else:
        update.message.reply_text("❌ Error requesting number.")

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
    dp.add_handler(CommandHandler("buy", buy_handler))
    dp.add_handler(CommandHandler("addbalance", addbalance_cmd))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
