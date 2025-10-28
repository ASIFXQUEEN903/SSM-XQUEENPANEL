import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import threading
import time

# -----------------------
# CONFIG (Direct Values)
# -----------------------
BOT_TOKEN = "7611620330:AAEa5oS_hRhGM7qq5cNE-FQ0u7otuNC8Trk"
ADMIN_ID = 7582601826
MONGO_URL = "mongodb+srv://xqueenfree:xqueenfree@cluster0.gi357.mongodb.net/?retryWrites=true&w=majority"

bot = telebot.TeleBot(BOT_TOKEN)

# -----------------------
# MONGO DB SETUP
# -----------------------
client = MongoClient(MONGO_URL)
db = client['usa_bot']
users_col = db['users']
# optional: ensure index to avoid duplicates (uncomment if you want)
# users_col.create_index("user_id", unique=True)

# -----------------------
# TEMP STORAGE
# -----------------------
pending_messages = {}
active_chats = {}
user_stage = {}

# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    user_name = msg.from_user.first_name or "Unknown"

    # Save user to MongoDB
    try:
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "name": user_name}},
            upsert=True
        )
    except Exception as e:
        print(f"Error saving user {user_id}: {e}")

    user_stage[user_id] = "start"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 BUY", callback_data="buy"))

    # Show Broadcast button only for ADMIN
    if user_id == ADMIN_ID:
        kb.add(InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"))

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
    user_id = call.from_user.id
    data = call.data

    # ---- ADMIN BROADCAST BUTTON ----
    if data == "broadcast_menu" and user_id == ADMIN_ID:
        # Ask admin to send message or reply to existing message in admin chat
        bot.send_message(ADMIN_ID, "✍️ Send the broadcast message here (text/photo/video/document). You can also reply to a message to broadcast that message.")
        # Register next step: when admin sends message, process_broadcast will handle it
        bot.register_next_step_handler_by_chat_id(ADMIN_ID, process_broadcast)
        return

    # ---- BUY SECTION ----
    if data == "buy":
        user_stage[user_id] = "service"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Telegram – ₹50", callback_data="buy_telegram"))
        kb.add(InlineKeyboardButton("WhatsApp – ₹45", callback_data="buy_whatsapp"))
        bot.edit_message_text("Choose your service:", call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    elif data.startswith("buy_") and user_stage.get(user_id) == "service":
        service = "Telegram" if "telegram" in data else "WhatsApp"
        user_stage[user_id] = "waiting_utr"
        pending_messages[user_id] = {'service': service}
        bot.send_photo(
            call.message.chat.id,
            "https://files.catbox.moe/8rpxez.jpg",
            caption=f"Scan & Pay for {service}\nThen send your *12 digit* UTR number or screenshot here.",
            parse_mode="Markdown"
        )
        return

    # ---- PAYMENT CONFIRM/CANCEL/CHAT ----
    if data.startswith(("confirm","cancel","chat","endchat")):
        parts = data.split("|")
        action = parts[0]
        target_id = int(parts[1])

        if action == "chat":
            active_chats[target_id] = True
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🛑 End this Chat", callback_data=f"endchat|{target_id}"))
            bot.send_message(target_id, "💬 Admin connected with you.")
            bot.send_message(ADMIN_ID, f"💬 Chat started with user {target_id}", reply_markup=kb)
            return

        elif action == "endchat":
            bot.send_message(ADMIN_ID, f"💬 Type final message to user {target_id}:")
            bot.register_next_step_handler_by_chat_id(ADMIN_ID, lambda m: finish_chat(m, target_id))
            return

        if target_id not in pending_messages:
            bot.send_message(ADMIN_ID, "⚠️ No pending request for this user.")
            return

        info = pending_messages.pop(target_id)
        service = info.get('service', 'Service')

        if action == "confirm":
            bot.send_message(target_id, f"✅ Payment successful! Generating your USA {service} number...")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{target_id}"))
            bot.send_message(ADMIN_ID, f"Payment confirmed for user {target_id}.", reply_markup=kb)
        else:
            bot.send_message(target_id, "❌ Your Payment Not Received And Your Query Is cancelled.")
            bot.send_message(ADMIN_ID, f"❌ Payment cancelled for user {target_id}.")
        user_stage[target_id] = "done"

# -----------------------
# BROADCAST HANDLER (Button-triggered, same-behaviour as async example)
# -----------------------
def process_broadcast(msg):
    """
    msg: telebot.types.Message sent by ADMIN in response to prompt.
    Supports:
      - If admin replies to an earlier message, that replied message is used as source.
      - Otherwise uses the admin's own sent message.
    """
    # security check
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.chat.id, "❌ Unauthorized.")
        return

    # Use replied-to message as broadcast source if present
    source = msg.reply_to_message if msg.reply_to_message else msg

    # Extract text/caption and detect media type
    text = source.text or source.caption or ""
    is_photo = bool(source.photo)
    is_video = hasattr(source, "video") and source.video is not None
    is_document = hasattr(source, "document") and source.document is not None

    bot.send_message(ADMIN_ID, "📡 Broadcasting started... Please wait. (You can watch progress here)")

    # Start background thread so bot doesn't block
    threading.Thread(target=broadcast_thread, args=(source, text, is_photo, is_video, is_document)).start()

def broadcast_thread(source_msg, text, is_photo, is_video, is_document):
    users = list(users_col.find())
    total = len(users)
    sent = 0
    failed = 0
    progress_interval = 25  # send admin progress every 25 messages

    for user in users:
        user_id = user.get('user_id')
        if not user_id or user_id == ADMIN_ID:
            continue

        try:
            # send appropriate media or text
            if is_photo and source_msg.photo:
                photo_file = source_msg.photo[-1].file_id
                bot.send_photo(user_id, photo=photo_file, caption=text or "")
            elif is_video and getattr(source_msg, "video", None):
                bot.send_video(user_id, video=source_msg.video.file_id, caption=text or "")
            elif is_document and getattr(source_msg, "document", None):
                bot.send_document(user_id, document=source_msg.document.file_id, caption=text or "")
            else:
                # simple text broadcast
                bot.send_message(user_id, f"📢 Broadcast:\n{text}")

            sent += 1

            if sent % progress_interval == 0:
                try:
                    bot.send_message(ADMIN_ID, f"✅ Sent {sent}/{total} users...")
                except Exception:
                    pass

            # small delay to avoid Telegram flood limits
            time.sleep(0.06)

        except Exception as e:
            failed += 1
            print(f"❌ Broadcast failed for {user_id}: {e}")

    # Final report
    try:
        bot.send_message(ADMIN_ID, f"🎯 Broadcast completed!\n✅ Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {total}")
    except Exception:
        pass

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
        bot.send_message(ADMIN_ID, "⚠️ No active chat to end.")

# -----------------------
# MESSAGE HANDLER
# -----------------------
@bot.message_handler(func=lambda m: True, content_types=['text','photo','video','document'])
def chat_handler(msg):
    user_id = msg.from_user.id

    # ---- ADMIN CHAT (when admin types while connected to active chat users) ----
    if user_id == ADMIN_ID:
        for uid, active in active_chats.items():
            if active:
                try:
                    if msg.content_type == 'photo':
                        bot.send_photo(uid, msg.photo[-1].file_id)
                    elif msg.content_type == 'video':
                        bot.send_video(uid, msg.video.file_id)
                    elif msg.content_type == 'document':
                        bot.send_document(uid, msg.document.file_id)
                    else:
                        bot.send_message(uid, f"🤖Bot: {msg.text}")
                except Exception as e:
                    print(f"Error forwarding admin message to {uid}: {e}")
        return

    # ---- USER CHAT ----
    if user_id in active_chats and active_chats[user_id]:
        try:
            if msg.content_type == 'photo':
                bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=f"📸 Screenshot from {user_id}")
            elif msg.content_type == 'video':
                bot.send_video(ADMIN_ID, msg.video.file_id, caption=f"🎥 Video from {user_id}")
            elif msg.content_type == 'document':
                bot.send_document(ADMIN_ID, msg.document.file_id, caption=f"📎 Document from {user_id}")
            else:
                bot.send_message(ADMIN_ID, f"💬 User {user_id}: {msg.text}")
        except Exception as e:
            print(f"Error sending user message to admin: {e}")
        return

    # ---- PAYMENT UTR STAGE ----
    stage = user_stage.get(user_id, "none")
    if stage != "waiting_utr":
        bot.send_message(user_id, "⚠️ Please use /start to begin again.")
        return

    pending_messages.setdefault(user_id, {})
    user_name = msg.from_user.first_name or "Unknown"
    service = pending_messages[user_id].get('service', 'Service')

    if msg.content_type == 'text':
        text = msg.text.strip()
        if not text.isdigit() or len(text) != 12:
            bot.send_message(user_id, "⚠️ Please enter a valid *12 digit* UTR or send screenshot.", parse_mode="Markdown")
            return
        pending_messages[user_id]['utr'] = text
        info_text = f"UTR: {text}"
    elif msg.content_type == 'photo':
        photo_id = msg.photo[-1].file_id
        pending_messages[user_id]['screenshot'] = photo_id
        info_text = "📸 Screenshot sent"
    else:
        bot.send_message(user_id, "⚠️ Only UTR text or photo allowed.")
        return

    bot.send_message(user_id, "🔄 Payment request is verifying by our records. Please wait 5–10 seconds… don't re-start until your number is delivered...")

    admin_text = (
        f"💰 <b>Payment Request</b>\n"
        f"👤 Name: <a href='tg://user?id={user_id}'>{user_name}</a>\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"📦 Service: {service}\n"
        f"{info_text}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Confirm", callback_data=f"confirm|{user_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{user_id}")
    )

    if 'screenshot' in pending_messages[user_id]:
        bot.send_photo(ADMIN_ID, pending_messages[user_id]['screenshot'], caption=admin_text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=kb)

    user_stage[user_id] = "done"

# -----------------------
# RUN BOT
# -----------------------
print("✅ Bot running successfully...")
bot.infinity_polling(skip_pending=True)
