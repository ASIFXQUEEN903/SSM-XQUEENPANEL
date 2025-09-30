import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import time

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
users_col = db['users']

# -----------------------
# TEMP STORAGE
# -----------------------
pending_messages = {}  # {user_id: {'service': ..., 'text': ...}}
active_chats = {}      # {user_id: True/False} → admin chat mode

# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    users_col.update_one({'user_id': user_id}, {'$set': {'user_id': user_id}}, upsert=True)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 BUY", callback_data="buy"))
    bot.send_message(msg.chat.id, "👋 Welcome to USA Number Service\n👉 Telegram / WhatsApp OTP Buy Here", reply_markup=kb)

# -----------------------
# CALLBACK HANDLER
# -----------------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "buy":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Telegram – ₹50", callback_data="buy_telegram"))
        kb.add(InlineKeyboardButton("WhatsApp – ₹45", callback_data="buy_whatsapp"))
        bot.edit_message_text("Choose your service:", call.message.chat.id, call.message.message_id, reply_markup=kb)

    elif call.data.startswith("buy_"):
        service = "Telegram" if "telegram" in call.data else "WhatsApp"
        bot.send_photo(call.message.chat.id, "https://files.catbox.moe/8rpxez.jpg",
                       caption=f"Scan & Pay for {service}\nThen send your UTR Number here.")
        bot.register_next_step_handler(call.message, lambda m: utr_handler(m, service))

    elif call.data.startswith(("confirm", "cancel", "chat")):
        parts = call.data.split("|")
        action = parts[0]
        user_id = int(parts[1])

        if action == "chat":
            active_chats[user_id] = True
            bot.send_message(user_id, "💬 Owner is connected. Please enter your message.")
            bot.send_message(ADMIN_ID, f"💬 You are now chatting with user {user_id}.")
            return

        if user_id not in pending_messages:
            bot.send_message(call.message.chat.id, "⚠️ No pending message from this user.")
            return

        user_data = pending_messages.pop(user_id)
        service = user_data['service']

        if action == "confirm":
            bot.send_message(user_id, f"✅ Your payment is successful! Generating USA {service} number…")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{user_id}"))
            bot.send_message(ADMIN_ID, f"Payment confirmed for user {user_id}.", reply_markup=kb)
        else:
            bot.send_message(user_id, "❌ Your payment not received in our system and your query is cancelled. Please try again.")
            bot.send_message(ADMIN_ID, "❌ Cancelled and user notified.")

# -----------------------
# UTR HANDLER
# -----------------------
def utr_handler(msg, service):
    user_id = msg.from_user.id
    users_col.update_one({'user_id': user_id}, {'$set': {'user_id': user_id}}, upsert=True)
    bot.send_message(user_id, "🔄 Payment is verifying… Please wait 5–10 seconds")
    pending_messages[user_id] = {'text': msg.text.strip(), 'service': service}

    verify_msg = f"New pending message from user:\nName: {msg.from_user.first_name}\nID: {user_id}\nMessage: {msg.text.strip()}\nService: {service}"
    bot.send_message(ADMIN_ID, verify_msg, reply_markup=admin_keyboard(user_id))

def admin_keyboard(user_id):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{user_id}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{user_id}"))
    return kb

# -----------------------
# ADMIN TO USER CHAT
# -----------------------
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_chat(msg):
    for user_id, active in active_chats.items():
        if active:
            try:
                bot.send_message(user_id, f"💬 Owner: {msg.text}")
            except:
                pass

# -----------------------
# USER REPLY TO ADMIN
# -----------------------
@bot.message_handler(func=lambda m: True)
def user_reply(msg):
    user_id = msg.from_user.id
    if user_id in active_chats and active_chats[user_id]:
        try:
            bot.send_message(ADMIN_ID, f"💬 User {user_id}: {msg.text}")
        except:
            pass

# -----------------------
# COMPLETE COMMAND
# -----------------------
@bot.message_handler(commands=['complete'])
def complete(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    for user_id, active in list(active_chats.items()):
        if active:
            service = pending_messages.get(user_id, {}).get('service', 'Service')
            bot.send_message(user_id, f"✅ Your USA {service} process is complete. Thank you for using our bot. Powered by xqueen")
            active_chats[user_id] = False
            bot.send_message(ADMIN_ID, f"💬 Chat with user {user_id} ended.")

# -----------------------
# REFUND COMMAND
# -----------------------
@bot.message_handler(commands=['refund'])
def refund(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    for user_id, active in list(active_chats.items()):
        if active:
            bot.send_message(user_id, "❌ Technical issue facing now. Your money will be refunded. Please wait 3–5 seconds…")
            time.sleep(4)
            active_chats[user_id] = False
            bot.send_message(ADMIN_ID, f"💬 Refund completed. Chat with user {user_id} ended.")

# -----------------------
# BROADCAST
# -----------------------
@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    text = msg.text.partition(' ')[2]
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
            pass
    bot.reply_to(msg, f"✅ Broadcast sent to {count} users.")

# -----------------------
# RUN BOT
# -----------------------
bot.infinity_polling()
