import os
import re
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MONGO_URL = os.getenv("MONGO_URL")
bot = telebot.TeleBot(BOT_TOKEN)

client = MongoClient(MONGO_URL)
db = client["usa_bot"]
users_col = db["users"]

# -------- TEMP DATA --------
user_stage = {}        # {uid: "start"|"service"|"waiting_utr"|"done"}
user_service = {}      # {uid: "Telegram"/"WhatsApp"}
pending_messages = {}  # {uid: {'service':..., 'utr':...}}
chat_sessions = {}     # {admin_id: target_uid}

# -------- START --------
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    users_col.update_one({"user_id": uid}, {"$set": {"user_id": uid}}, upsert=True)
    user_stage[uid] = "start"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 BUY", callback_data="buy"))
    bot.send_message(m.chat.id,
        "👋 Welcome to USA Number Service\n👉 Telegram / WhatsApp OTP Buy Here",
        reply_markup=kb
    )

# -------- CALLBACK --------
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    uid = c.from_user.id
    data = c.data

    if data == "buy":
        user_stage[uid] = "service"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Telegram – ₹50", callback_data="service_Telegram"))
        kb.add(InlineKeyboardButton("WhatsApp – ₹45", callback_data="service_WhatsApp"))
        bot.edit_message_text("Choose your service:", c.message.chat.id,
                              c.message.message_id, reply_markup=kb)

    elif data.startswith("service_") and user_stage.get(uid) == "service":
        service = data.split("_",1)[1]
        user_service[uid] = service
        user_stage[uid] = "waiting_utr"
        bot.send_photo(
            uid,
            "https://files.catbox.moe/8rpxez.jpg",
            caption=f"Scan & Pay for {service}\n\nThen send your *12 digit* UTR number here."
        )

    elif data.startswith(("confirm","cancel","chat")):
        action, target_id = data.split("|")
        target_id = int(target_id)

        if action == "chat":
            chat_sessions[ADMIN_ID] = target_id
            bot.send_message(target_id, "💬 Owner is connected with you.")
            bot.send_message(ADMIN_ID, f"💬 Chat started with user {target_id}")
            return

        if target_id not in pending_messages:
            bot.send_message(c.message.chat.id, "⚠️ No pending request from this user.")
            return

        info = pending_messages.pop(target_id)
        service = info['service']

        if action == "confirm":
            bot.send_message(target_id,
                f"✅ Your payment is successful! Generating USA {service} number…")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{target_id}"))
            bot.send_message(ADMIN_ID,
                f"Payment confirmed for user {target_id}.",
                reply_markup=kb)
        else:
            bot.send_message(target_id,
                "❌ Your payment not received and your query is cancelled. Please try again.")
            bot.send_message(ADMIN_ID, f"❌ Payment cancelled for user {target_id}.")
        user_stage[target_id] = "done"

# -------- MESSAGE HANDLER --------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handler(m):
    uid = m.from_user.id
    text = m.text.strip()

    # ----- ADMIN REPLY DURING CHAT -----
    if uid == ADMIN_ID and ADMIN_ID in chat_sessions:
        bot.send_message(chat_sessions[ADMIN_ID], f"👑 Owner: {text}")
        return

    # ----- USER REPLY DURING CHAT -----
    if uid in chat_sessions.values():
        bot.send_message(ADMIN_ID, f"💬 User {uid}: {text}")
        return

    stage = user_stage.get(uid, "none")

    # ----- WAITING FOR UTR -----
    if stage == "waiting_utr":
        if re.fullmatch(r"\d{12}", text):
            user_stage[uid] = "done"
            service = user_service.get(uid, "Service")
            pending_messages[uid] = {"service": service, "utr": text}
            bot.send_message(uid, "🔄 Payment is verifying… Please wait 5–10 seconds.")
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{uid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{uid}")
            )
            bot.send_message(
                ADMIN_ID,
                f"💰 Payment Request\nName: {m.from_user.first_name}\nID: {uid}\nService: {service}\nUTR: {text}",
                reply_markup=kb
            )
        else:
            bot.send_message(uid, "⚠️ Please enter a valid *12 digit* UTR number.")
        return

    # ----- Anything else -----
    if stage in ["start","service"]:
        bot.send_message(uid, "⚠️ Please follow the steps. Click BUY and select service first.")
    else:
        bot.send_message(uid, "Use /start to begin a new order.")

# -------- COMPLETE / REFUND --------
@bot.message_handler(commands=['complete'])
def complete(m):
    if m.from_user.id != ADMIN_ID: return
    if ADMIN_ID not in chat_sessions:
        bot.reply_to(m, "⚠️ No active chat session.")
        return
    target = chat_sessions.pop(ADMIN_ID)
    service = user_service.get(target, "Service")
    bot.send_message(target,
        f"✅ Your USA {service} process is complete. Thank you for using our bot.")
    bot.send_message(ADMIN_ID, f"💬 Chat with user {target} ended.")

@bot.message_handler(commands=['refund'])
def refund(m):
    if m.from_user.id != ADMIN_ID: return
    if ADMIN_ID not in chat_sessions:
        bot.reply_to(m, "⚠️ No active chat session.")
        return
    target = chat_sessions.pop(ADMIN_ID)
    bot.send_message(target,
        "❌ Technical issue. Your money will be refunded shortly.")
    time.sleep(3)
    bot.send_message(ADMIN_ID, f"💬 Refund processed for user {target}.")

# -------- BROADCAST --------
@bot.message_handler(commands=['broadcast'])
def broadcast(m):
    if m.from_user.id != ADMIN_ID: return
    text = m.text.partition(' ')[2]
    if not text:
        bot.reply_to(m, "⚠️ Usage: /broadcast Your message here")
        return
    sent = 0
    for u in users_col.find():
        try:
            bot.send_message(u['user_id'], f"📢 Broadcast:\n{text}")
            sent += 1
        except: pass
    bot.reply_to(m, f"✅ Broadcast sent to {sent} users.")

# -------- RUN --------
print("✅ Bot running…")
bot.infinity_polling()
