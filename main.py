import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# -----------------------
# CONFIG
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MONGO_URL = os.getenv("MONGO_URL")

bot = telebot.TeleBot(BOT_TOKEN)

# -----------------------
# MONGO DB SETUP
# -----------------------
client = MongoClient(MONGO_URL)
db = client['usa_bot']
users_col = db['users']  # Store user ids

# Temporary storage for pending messages
pending_messages = {}  # {user_id: {'text': ..., 'service': ...}}

# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    users_col.update_one({'user_id': user_id}, {'$set': {'user_id': user_id}}, upsert=True)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 BUY", callback_data="buy"))
    bot.send_message(
        msg.chat.id,
        "👋 Welcome to USA Number Service\n👉 Telegram / WhatsApp OTP Buy Here",
        reply_markup=kb
    )

# -----------------------
# CALLBACK HANDLER
# -----------------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    # ------------------- BUY MENU -------------------
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

    # ------------------- SERVICE SELECT -------------------
    elif call.data.startswith("buy_"):
        service = "Telegram" if "telegram" in call.data else "WhatsApp"
        bot.send_photo(
            call.message.chat.id,
            "https://files.catbox.moe/8rpxez.jpg",
            caption=f"Scan & Pay for {service}\nThen send your UTR Number here."
        )
        bot.register_next_step_handler(call.message, lambda m: utr_handler(m, service))

    # ------------------- ADMIN ACTION -------------------
    elif call.data.startswith(("confirm", "cancel")):
        parts = call.data.split("|")
        action = parts[0]
        user_id = int(parts[1])

        if user_id not in pending_messages:
            bot.send_message(call.message.chat.id, "⚠️ No pending message from this user.")
            return

        user_data = pending_messages.pop(user_id)
        service = user_data['service']
        msg_text = user_data['text']

        if action == "confirm":
            bot.send_message(user_id, f"✅ You have successfully purchased {service}!\nYour message: {msg_text}")
            bot.send_message(call.message.chat.id, "✅ Confirmed and user notified.")
        else:
            bot.send_message(user_id, "❌ Your payment not received in our system and your query is cancelled. Please try again.")
            bot.send_message(call.message.chat.id, "❌ Cancelled and user notified.")

# -----------------------
# UTR HANDLER (USER MESSAGE CAPTURE)
# -----------------------
def utr_handler(msg, service):
    user_id = msg.from_user.id
    users_col.update_one({'user_id': user_id}, {'$set': {'user_id': user_id}}, upsert=True)

    pending_messages[user_id] = {
        'text': msg.text.strip(),
        'service': service
    }

    verify_msg = (
        f"New pending message from user:\n"
        f"Name: {msg.from_user.first_name}\n"
        f"ID: {user_id}\n"
        f"Message: {msg.text.strip()}\n"
        f"Service: {service}"
    )

    # Send to Admin with Confirm/Cancel buttons
    bot.send_message(
        ADMIN_ID,
        verify_msg,
        reply_markup=admin_keyboard(user_id)
    )

def admin_keyboard(user_id):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{user_id}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{user_id}"))
    return kb

# -----------------------
# BROADCAST COMMAND (ADMIN ONLY)
# -----------------------
@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    if msg.from_user.id != ADMIN_ID:
        return  # Only admin can broadcast

    text = msg.text.partition(' ')[2]  # Get message after /broadcast
    if not text:
        bot.reply_to(msg, "⚠️ Usage: /broadcast Your message here")
        return

    all_users = users_col.find()
    count = 0
    for user in all_users:
        try:
            bot.send_message(user['user_id'], f"📢 Broadcast:\n{text}")
            count += 1
        except:
            pass  # Ignore errors if user blocked bot

    bot.reply_to(msg, f"✅ Broadcast sent to {count} users.")

# -----------------------
# RUN BOT
# -----------------------
bot.infinity_polling()
