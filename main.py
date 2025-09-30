import os
import re
import time
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
db = client["usa_bot"]
users_col = db["users"]

# -----------------------
# TEMP STORAGE
# -----------------------
pending_messages = {}   # {user_id: {'service': ..., 'utr': ...}}
utr_stage = {}          # {user_id: True/False} – only true when waiting for UTR
chat_sessions = {}      # {admin_id: target_user_id} – admin chats only with chosen user

# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=["start"])
def start(msg):
    uid = msg.from_user.id
    users_col.update_one({"user_id": uid}, {"$set": {"user_id": uid}}, upsert=True)
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
    data = call.data

    if data == "buy":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Telegram – ₹50", callback_data="buy_telegram"))
        kb.add(InlineKeyboardButton("WhatsApp – ₹45", callback_data="buy_whatsapp"))
        bot.edit_message_text("Choose your service:", call.message.chat.id,
                              call.message.message_id, reply_markup=kb)

    elif data.startswith("buy_"):
        service = "Telegram" if "telegram" in data else "WhatsApp"
        uid = call.from_user.id
        utr_stage[uid] = True     # user is now allowed to send UTR
        bot.send_photo(
            uid,
            "https://files.catbox.moe/8rpxez.jpg",
            caption=f"Scan & Pay for {service}\n\nThen send your *12 digit* UTR number here."
        )

    elif data.startswith(("confirm", "cancel", "chat")):
        action, uid = data.split("|")
        uid = int(uid)

        if action == "chat":
            chat_sessions[ADMIN_ID] = uid
            bot.send_message(uid, "💬 Owner is connected with you.")
            bot.send_message(ADMIN_ID, f"💬 You are now chatting with user {uid}.")
            return

        if uid not in pending_messages:
            bot.send_message(call.message.chat.id, "⚠️ No pending UTR from this user.")
            return

        info = pending_messages.pop(uid)
        service = info["service"]

        if action == "confirm":
            bot.send_message(uid,
                f"✅ Your payment is successful! Generating USA {service} number…")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{uid}"))
            bot.send_message(ADMIN_ID,
                f"Payment confirmed for user {uid}.",
                reply_markup=kb)
        else:
            bot.send_message(uid,
                "❌ Your payment not received in our system and your query is cancelled. Try again.")
            bot.send_message(ADMIN_ID, f"❌ Payment cancelled for user {uid}.")

# -----------------------
# UTR HANDLER
# -----------------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def messages(m):
    uid = m.from_user.id
    text = m.text.strip()

    # -------- ADMIN CHAT MODE --------
    if uid == ADMIN_ID and ADMIN_ID in chat_sessions:
        target = chat_sessions[ADMIN_ID]
        bot.send_message(target, f"👑 Owner: {text}")
        return

    # -------- USER REPLY DURING CHAT --------
    if uid in chat_sessions.values():
        # forward user reply back to admin
        bot.send_message(ADMIN_ID, f"💬 User {uid}: {text}")
        return

    # -------- UTR NUMBER ENTRY --------
    if utr_stage.get(uid):
        if re.fullmatch(r"\d{12}", text):
            utr_stage[uid] = False
            pending_messages[uid] = {
                "utr": text,
                "service": "Telegram/WhatsApp"  # real service stored in callback above
            }
            bot.send_message(uid,
                "🔄 Payment is verifying… Please wait 5–10 seconds")

            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{uid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{uid}")
            )
            bot.send_message(
                ADMIN_ID,
                f"💰 Payment request\nUser: {m.from_user.first_name}\nID: {uid}\nUTR: {text}",
                reply_markup=kb
            )
        else:
            bot.send_message(uid, "⚠️ Please enter a valid *12 digit* UTR number.")
        return

    # Any random message outside stages
    bot.send_message(uid, "Use /start to buy service.")

# -----------------------
# COMPLETE COMMAND
# -----------------------
@bot.message_handler(commands=["complete"])
def complete(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    if ADMIN_ID not in chat_sessions:
        bot.reply_to(msg, "⚠️ No active chat session.")
        return
    uid = chat_sessions.pop(ADMIN_ID)
    bot.send_message(uid,
        "✅ Your USA number process is complete. Thank you for using our bot. Powered by xqueen")
    bot.send_message(ADMIN_ID, f"💬 Chat with user {uid} ended.")

# -----------------------
# REFUND COMMAND
# -----------------------
@bot.message_handler(commands=["refund"])
def refund(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    if ADMIN_ID not in chat_sessions:
        bot.reply_to(msg, "⚠️ No active chat session.")
        return
    uid = chat_sessions.pop(ADMIN_ID)
    bot.send_message(uid,
        "❌ Technical issue. Your money will be refunded shortly.")
    time.sleep(3)
    bot.send_message(ADMIN_ID, f"💬 Refund completed. Chat with user {uid} ended.")

# -----------------------
# BROADCAST
# -----------------------
@bot.message_handler(commands=["broadcast"])
def broadcast(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    text = msg.text.partition(" ")[2]
    if not text:
        bot.reply_to(msg, "⚠️ Usage: /broadcast Your message here")
        return
    count = 0
    for u in users_col.find():
        try:
            bot.send_message(u["user_id"], f"📢 Broadcast:\n{text}")
            count += 1
        except:
            pass
    bot.reply_to(msg, f"✅ Broadcast sent to {count} users.")

# -----------------------
# RUN BOT
# -----------------------
print("✅ Bot is running...")
bot.infinity_polling()
