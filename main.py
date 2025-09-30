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
pending_messages = {}  # {user_id: {'service': ..., 'utr': ...}}
active_chats = {}      # {user_id: True/False} → admin chat mode
user_stage = {}        # {user_id: 'start'|'service'|'waiting_utr'|'done'}

# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    users_col.update_one({'user_id': user_id}, {'$set': {'user_id': user_id}}, upsert=True)
    user_stage[user_id] = "start"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 BUY", callback_data="buy"))
    bot.send_message(msg.chat.id, "👋 Welcome to USA Number Service\n👉 Telegram / WhatsApp OTP Buy Here", reply_markup=kb)

# -----------------------
# CALLBACK HANDLER
# -----------------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    data = call.data

    # ---- BUY BUTTON ----
    if data == "buy":
        user_stage[user_id] = "service"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Telegram – ₹50", callback_data="buy_telegram"))
        kb.add(InlineKeyboardButton("WhatsApp – ₹45", callback_data="buy_whatsapp"))
        bot.edit_message_text("Choose your service:", call.message.chat.id, call.message.message_id, reply_markup=kb)

    # ---- SERVICE SELECT ----
    elif data.startswith("buy_") and user_stage.get(user_id) == "service":
        service = "Telegram" if "telegram" in data else "WhatsApp"
        user_stage[user_id] = "waiting_utr"
        pending_messages[user_id] = {'service': service}
        bot.send_photo(call.message.chat.id, "https://files.catbox.moe/8rpxez.jpg",
                       caption=f"Scan & Pay for {service}\nThen send your *12 digit* UTR number here.")

    # ---- ADMIN ACTION ----
    elif data.startswith(("confirm","cancel","chat")):
        action, target_id = data.split("|")
        target_id = int(target_id)

        if action == "chat":
            active_chats[target_id] = True
            bot.send_message(target_id, "💬 Owner is connected. Please enter your message.")
            bot.send_message(ADMIN_ID, f"💬 Chat started with user {target_id}")
            return

        if target_id not in pending_messages:
            bot.send_message(ADMIN_ID, "⚠️ No pending request from this user.")
            return

        info = pending_messages.pop(target_id)
        service = info.get('service', 'Service')

        if action == "confirm":
            bot.send_message(target_id, f"✅ Your payment is successful! Generating USA {service} number…")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{target_id}"))
            bot.send_message(ADMIN_ID, f"Payment confirmed for user {target_id}.", reply_markup=kb)
        else:
            bot.send_message(target_id, "❌ Your payment not received and your query is cancelled.")
            bot.send_message(ADMIN_ID, f"❌ Payment cancelled for user {target_id}.")
        user_stage[target_id] = "done"

# -----------------------
# UTR HANDLER
# -----------------------
@bot.message_handler(func=lambda m: True)
def utr_handler(msg):
    user_id = msg.from_user.id
    stage = user_stage.get(user_id, "none")
    text = msg.text.strip()

    # ---- WAITING FOR UTR ----
    if stage == "waiting_utr":
        if not text.isdigit() or len(text) != 12:
            bot.send_message(user_id, "⚠️ Please enter a valid *12 digit* UTR number.")
            return
        pending_messages[user_id]['utr'] = text
        bot.send_message(user_id, "🔄 Payment is verifying… Please wait 5–10 seconds.")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{user_id}"))
        kb.add(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{user_id}"))
        bot.send_message(ADMIN_ID, f"💰 Payment Request\nUser ID: {user_id}\nUTR: {text}\nService: {pending_messages[user_id]['service']}", reply_markup=kb)
        return

    # ---- ADMIN CHAT ----
    if user_id == ADMIN_ID:
        # Check if any active chat
        for uid, active in active_chats.items():
            if active:
                bot.send_message(uid, f"👑 Owner: {text}")
        return

    # ---- USER CHAT ----
    if user_id in active_chats and active_chats[user_id]:
        bot.send_message(ADMIN_ID, f"💬 User {user_id}: {text}")
        return

    # ---- OTHER CASE ----
    bot.send_message(user_id, "⚠️ Please follow the steps or use /start to begin.")

# -----------------------
# COMPLETE COMMAND
# -----------------------
@bot.message_handler(commands=['complete'])
def complete(msg):
    if msg.from_user.id != ADMIN_ID: return
    to_remove = []
    for uid, active in active_chats.items():
        if active:
            service = pending_messages.get(uid, {}).get('service', 'Service')
            bot.send_message(uid, f"✅ Your USA {service} process is complete. Thank you for using our bot.")
            to_remove.append(uid)
    for uid in to_remove:
        active_chats.pop(uid, None)
    bot.send_message(ADMIN_ID, f"💬 All active chats ended.")

# -----------------------
# REFUND COMMAND
# -----------------------
@bot.message_handler(commands=['refund'])
def refund(msg):
    if msg.from_user.id != ADMIN_ID: return
    to_remove = []
    for uid, active in active_chats.items():
        if active:
            bot.send_message(uid, "❌ Technical issue. Your money will be refunded. Please wait 3–5 seconds…")
            time.sleep(4)
            to_remove.append(uid)
    for uid in to_remove:
        active_chats.pop(uid, None)
    bot.send_message(ADMIN_ID, "💬 Refund processed for all active chats.")

# -----------------------
# BROADCAST
# -----------------------
@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    if msg.from_user.id != ADMIN_ID: return
    text = msg.text.partition(' ')[2]
    if not text:
        bot.reply_to(msg, "⚠️ Usage: /broadcast Your message here")
        return
    sent = 0
    for u in users_col.find():
        try:
            bot.send_message(u['user_id'], f"📢 Broadcast:\n{text}")
            sent += 1
        except: pass
    bot.reply_to(msg, f"✅ Broadcast sent to {sent} users.")

# -----------------------
# RUN BOT
# -----------------------
print("✅ Bot running…")
bot.infinity_polling()
