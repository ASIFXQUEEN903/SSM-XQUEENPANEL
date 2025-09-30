import os, telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -----------------------
# CONFIG
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = telebot.TeleBot(BOT_TOKEN)


# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 BUY", callback_data="buy"))
    bot.send_message(
        msg.chat.id,
        "👋 Welcome to USA Number Service\n👉 Telegram / WhatsApp OTP Buy Here",
        reply_markup=kb
    )


# -----------------------
# CALLBACK HANDLERS
# -----------------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "buy":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Telegram – ₹50", callback_data="buy_telegram"))
        kb.add(InlineKeyboardButton("WhatsApp – ₹45", callback_data="buy_whatsapp"))
        bot.edit_message_text(
            "Choose your service:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb
        )

    elif call.data.startswith("buy_"):
        service = "Telegram" if "telegram" in call.data else "WhatsApp"
        bot.send_photo(
            call.message.chat.id,
            "https://files.catbox.moe/8rpxez.jpg",  # ✅ Your QR code
            caption=f"Scan & Pay for {service}\nThen send your UTR Number here."
        )
        bot.register_next_step_handler(call.message, lambda m: utr_handler(m, service))


def utr_handler(msg, service):
    utr = msg.text.strip()
    verify_msg = (
        f"Name: {msg.from_user.first_name}\n"
        f"ID: {msg.from_user.id}\n"
        f"UTR: {utr}\n"
        f"Service: {service}\n"
        f"Amount: {'₹50' if service == 'Telegram' else '₹45'}\n\n"
        "🔄 Verifying payment… Please wait 5–10 seconds"
    )
    bot.send_message(msg.chat.id, verify_msg)

    # Send to Admin for approval
    bot.send_message(
        ADMIN_ID,
        f"New Order:\n{verify_msg}",
        reply_markup=admin_keyboard(msg.chat.id, service, utr)
    )


def admin_keyboard(uid, service, utr):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{uid}|{service}|{utr}"))
    kb.add(InlineKeyboardButton("❌ Decline", callback_data=f"decline|{uid}"))
    return kb


# -----------------------
# ADMIN DECISION
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith(("confirm", "decline")))
def admin_action(call):
    parts = call.data.split("|")
    action = parts[0]
    user_id = int(parts[1])

    if action == "confirm":
        service = parts[2]
        bot.send_message(user_id, f"✅ Payment Verified!\nGenerating USA Number for {service}… Please wait a second.")
        bot.send_message(call.message.chat.id, "✅ Confirmed and user notified.")
    else:
        bot.send_message(user_id, "❌ Wrong UTR number or No Payment Record.\nPlease retry payment.")
        bot.send_message(call.message.chat.id, "❌ Declined and user notified.")


# -----------------------
# RUN BOT
# -----------------------
bot.infinity_polling()
