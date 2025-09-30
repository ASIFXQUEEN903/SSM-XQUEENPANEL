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
pending_messages = {}  # {user_id: {'service': ..., 'utr': ..., 'screenshot': ...}}
active_chats = {}      # {user_id: True/False → admin chat mode}
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
                       caption=f"Scan & Pay for {service}\nThen send your *12 digit* UTR number or screenshot here.")

    # ---- ADMIN ACTION ----
    elif data.startswith(("confirm","cancel","chat","endchat")):
        parts = data.split("|")
        action = parts[0]
        target_id = int(parts[1])

        # ---- START CHAT ----
        if action == "chat":
            active_chats[target_id] = True
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🛑 End this Chat", callback_data=f"endchat|{target_id}"))
            bot.send_message(target_id, "💬 Bot is connected with you.")
            bot.send_message(ADMIN_ID, f"💬 Chat started with user {target_id}", reply_markup=kb)
            return

        # ---- END CHAT ----
        elif action == "endchat":
            bot.send_message(ADMIN_ID, f"💬 Type the final message to send to user {target_id} before ending chat:")
            bot.register_next_step_handler_by_chat_id(ADMIN_ID, lambda m: finish_chat(m, target_id))
            return

        # ---- CONFIRM/CANCEL PAYMENT ----
        if target_id not in pending_messages:
            bot.send_message(ADMIN_ID, "⚠️ No pending request from this user.")
            return

        info = pending_messages.pop(target_id)
        service = info.get('service', 'Service')

        if action == "confirm":
            bot.send_message(target_id, f"✅ Your payment is successful! Generating USA {service} number...…")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{target_id}"))
            bot.send_message(ADMIN_ID, f"Payment confirmed for user {target_id}.", reply_markup=kb)
        else:
            bot.send_message(target_id, "❌ Your payment not received and your query is cancelled.")
            bot.send_message(ADMIN_ID, f"❌ Payment cancelled for user {target_id}.")
        user_stage[target_id] = "done"

# -----------------------
# FINISH CHAT FUNCTION
# -----------------------
def finish_chat(msg, target_id):
    final_text = msg.text.strip()
    if target_id in active_chats and active_chats[target_id]:
        bot.send_message(target_id, final_text)
        active_chats.pop(target_id, None)
        bot.send_message(ADMIN_ID, f"💬 Chat with user {target_id} ended.")
    else:
        bot.send_message(ADMIN_ID, f"⚠️ No active chat with user {target_id}.")

# -----------------------
# MESSAGE HANDLER
# -----------------------
@bot.message_handler(func=lambda m: True, content_types=['text','photo'])
def chat_handler(msg):
    user_id = msg.from_user.id

    # ---- ADMIN CHAT ----
    if user_id == ADMIN_ID:
        for uid, active in active_chats.items():
            if active:
                bot.send_message(uid, f"🤖Bot: {msg.text if msg.content_type=='text' else '📸 Screenshot sent'}")
        return

    # ---- USER CHAT ----
    if user_id in active_chats and active_chats[user_id]:
        bot.send_message(ADMIN_ID, f"💬 User {user_id}: {msg.text if msg.content_type=='text' else '📸 Screenshot sent'}")
        return

    stage = user_stage.get(user_id, "none")
    if stage != "waiting_utr":
        bot.send_message(user_id, "⚠️ Please follow the steps or use /start to begin.")
        return

    pending_messages.setdefault(user_id, {})
    user_name = msg.from_user.first_name
    uid = msg.from_user.id
    service = pending_messages[user_id].get('service', 'Service')

    if msg.content_type == 'text':
        text = msg.text.strip()
        if not text.isdigit() or len(text) != 12:
            bot.send_message(user_id, "⚠️ Please enter a valid *12 digit* UTR number or send a screenshot.")
            return
        pending_messages[user_id]['utr'] = text
        info_text = f"UTR: {text}"
    elif msg.content_type == 'photo':
        photo_id = msg.photo[-1].file_id
        pending_messages[user_id]['screenshot'] = photo_id
        info_text = "📸 Screenshot sent"
    else:
        bot.send_message(user_id, "⚠️ Only text (UTR) or photo (screenshot) allowed.")
        return

    bot.send_message(user_id, "🔄 Payment request is verifying by our records. Please wait 5–10 seconds…")

    # ---- SEND ADMIN ----
    admin_text = (
        f"💰 Payment Request\n"
        f"Name: <a href='tg://user?id={uid}'>{user_name}</a>\n"
        f"User ID: {uid}\n"
        f"Service: {service}\n"
        f"{info_text}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{uid}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{uid}")
    )

    if 'screenshot' in pending_messages[user_id]:
        bot.send_photo(ADMIN_ID, pending_messages[user_id]['screenshot'], caption=admin_text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=kb)

    user_stage[user_id] = "done"

# -----------------------
# COMPLETE COMMAND
# -----------------------
@bot.message_handler(commands=['complete'])
def complete(msg):
    if msg.from_user.id != ADMIN_ID: return
    ended = []
    for uid, active in active_chats.items():
        if active:
            service = pending_messages.get(uid, {}).get('service', 'Service')
            bot.send_message(uid, f"✅ Your USA {service} process is complete. Thank you for using our bot.")
            ended.append(uid)
    for uid in ended:
        active_chats.pop(uid, None)
    bot.send_message(ADMIN_ID, "💬 All active chats ended.")

# -----------------------
# REFUND COMMAND
# -----------------------
@bot.message_handler(commands=['refund'])
def refund(msg):
    if msg.from_user.id != ADMIN_ID: return
    ended = []
    for uid, active in active_chats.items():
        if active:
            bot.send_message(uid, "❌ Technical issue. Your money will be refunded. Please wait 3–5 seconds…")
            time.sleep(4)
            ended.append(uid)
    for uid in ended:
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
