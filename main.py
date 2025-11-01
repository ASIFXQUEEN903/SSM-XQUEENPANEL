import logging
import re
import threading
import time
from datetime import datetime

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# -----------------------
# CONFIG (Replace with your own values)
# -----------------------
BOT_TOKEN = "7611620330:AAEa5oS_hRhGM7qq5cNE-FQ0u7otuNC8Trk"  # <-- replace if needed
ADMIN_ID = 7582601826  # <-- replace if needed
MONGO_URL = "mongodb+srv://xqueenfree:xqueenfree@cluster0.gi357.mongodb.net/?retryWrites=true&w=majority"  # <-- replace if needed

# -----------------------
# INIT
# -----------------------
logging.basicConfig(level=logging.INFO)
telebot.logger.setLevel(logging.INFO)

bot = telebot.TeleBot(BOT_TOKEN)

# -----------------------
# MONGO DB SETUP
# -----------------------
client = MongoClient(MONGO_URL)
db = client['usa_bot']
users_col = db['users']
wallets_col = db['wallets']
recharges_col = db['recharges']
orders_col = db['orders']

# -----------------------
# TEMP STORAGE
# -----------------------
pending_messages = {}
active_chats = {}
user_stage = {}

# -----------------------
# UTILITY FUNCTIONS
# -----------------------
def ensure_user_exists(user_id, user_name=None, username=None):
    # username optional for backwards compatibility with calls that didn't pass username
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({
            "user_id": user_id,
            "name": user_name or "Unknown",
            "username": username,
            "wallet": 0.0,
            "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        })
    wallets_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "balance": 0.0}},
        upsert=True
    )

def get_balance(user_id):
    rec = wallets_col.find_one({"user_id": user_id})
    if not rec:
        return 0.0
    return float(rec.get("balance", 0.0))

def add_balance(user_id, amount):
    wallets_col.update_one({"user_id": user_id}, {"$inc": {"balance": float(amount)}}, upsert=True)

def deduct_balance(user_id, amount):
    wallets_col.update_one({"user_id": user_id}, {"$inc": {"balance": -float(amount)}}, upsert=True)

def format_currency(x):
    try:
        x = float(x)
    except Exception:
        x = 0.0
    if float(x).is_integer():
        return f"₹{int(x)}"
    return f"₹{x:.2f}"

# -----------------------
# START COMMAND
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    user_name = msg.from_user.first_name or "Unknown"
    username = msg.from_user.username

    ensure_user_exists(user_id, user_name, username)
    user_stage[user_id] = "start"

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💰 Balance", callback_data="balance"),
        InlineKeyboardButton("🛒 Buy Account", callback_data="buy")
    )
    kb.add(
        InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton("🛠️ Support", callback_data="support")
    )
    kb.add(
        InlineKeyboardButton("📦 Your Info", callback_data="info"),
        InlineKeyboardButton("🆘 How to Use?", callback_data="how_to_use")
    )

    # ✅ Admin-only buttons
    if user_id == ADMIN_ID:
        kb.add(
            InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"),
            InlineKeyboardButton("💸 Refund", callback_data="refund_start")
        )

    caption = (
        "🥂 <b>Welcome To Otp Bot By Queen</b> 🥂\n"
        "<blockquote expandable>\n"
        "- Automatic OTPs 📍\n"
        "- Easy to Use 🥂🥂\n"
        "- 24/7 Support 👨‍🔧\n"
        "- Instant Payment Approvals 🧾\n"
        "</blockquote>\n"
        "<blockquote expandable>\n"
        "🚀 <b>How to use Bot :</b>\n"
        "1️⃣ Recharge\n"
        "2️⃣ Select Country\n"
        "3️⃣ Buy Account\n"
        "4️⃣ Get Number & Login through Telegram / Telegram X / Whatsapp\n"
        "5️⃣ Receive OTP & You’re Done ✅\n"
        "</blockquote>\n"
        "🚀 <b>Enjoy Fast Account Buying Experience!</b>"
    )
    try:
        bot.send_photo(
            msg.chat.id,
            "https://files.catbox.moe/0tw7v4.jpg",
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception:
        bot.send_message(msg.chat.id, caption, parse_mode="HTML", reply_markup=kb)

# -----------------------
# CALLBACK HANDLER
# -----------------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    try:
        user_id = call.from_user.id
        data = call.data
        username = call.from_user.username
        first_name = call.from_user.first_name or "Unknown"

        ensure_user_exists(user_id, first_name, username)

        # ---------- Simple info/balance ----------
        if data == "info":
            u = users_col.find_one({"user_id": user_id}) or {}
            bal = get_balance(user_id)
            name = u.get("name", "Unknown")
            username_db = u.get("username")
            username_display = f"@{username_db}" if username_db else "Not Set"
            info_text = (
                f"📦 <b>Your Info</b>\n\n"
                f"👤 Name: {name}\n"
                f"🔖 Username: {username_display}\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"💰 Balance: {format_currency(bal)}"
            )
            bot.send_message(user_id, info_text, parse_mode="HTML")
            return

        if data == "balance":
            bal = get_balance(user_id)
            bot.send_message(user_id, f"💼 Your Wallet Balance: <b>{format_currency(bal)}</b>", parse_mode="HTML")
            return

        if data == "how_to_use":
            bot.send_message(user_id, "📘 How to use:\n\n1️⃣ Recharge\n2️⃣ Buy Account\n3️⃣ Wait for Otp ✅")
            return

        if data == "support":
            bot.send_message(user_id, "🛠️ Support:Contact @NOBITA_USA_903 ")
            # optionally forward to admin or create ticket
            bot.send_message(ADMIN_ID, f"🆘 Support request from <a href='tg://user?id={user_id}'>{user_id}</a>", parse_mode="HTML")
            return
          # ---------- Buy flow entry (choose country/service) ----------
        if data == "buy":
            kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🇺🇸 USA", callback_data="choose_usa"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
    user_stage[user_id] = "select_country"
    bot.edit_message_text(
        chat_id=user_id,
        message_id=call.message.message_id,
        text="🌎 Select your country:",
        reply_markup=kb
    )
    return

        if data == "choose_usa":
            kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(" Telegram — ₹50", callback_data="buy_telegram"),
        InlineKeyboardButton(" WhatsApp — ₹45", callback_data="buy_whatsapp")
    )
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="buy"))
    user_stage[user_id] = "choose_usa"
    bot.edit_message_text(
        chat_id=user_id,
        message_id=call.message.message_id,
        text="🇺🇸 Choose service to buy:",
        reply_markup=kb
    )
    return  
          

        if data == "back_to_menu":
            # same as /start but simpler
            start_msg = telebot.types.Message  # dummy to reuse start (we'll call start by building a fake object is complex)
            # simpler: re-send the start menu manually
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("💰 Balance", callback_data="balance"),
                InlineKeyboardButton("🛒 Buy Account", callback_data="buy")
            )
            kb.add(
                InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
                InlineKeyboardButton("🛠️ Support", callback_data="support")
            )
            kb.add(
                InlineKeyboardButton("📦 Your Info", callback_data="info"),
                InlineKeyboardButton("🆘 How to Use?", callback_data="how_to_use")
            )
            if user_id == ADMIN_ID:
                kb.add(
                    InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"),
                    InlineKeyboardButton("💸 Refund", callback_data="refund_start")
                )
            bot.send_message(user_id, "🔙 Back to menu", reply_markup=kb)
            user_stage[user_id] = "start"
            return

        # ---------- Buy Telegram / WhatsApp finalization ----------
        if data in ("buy_telegram", "buy_whatsapp"):
            # ensure user stage is correct (optional)
            if user_stage.get(user_id) not in (None, "choose_usa", "service", "start"):
                # allow but notify
                pass

            service = "Telegram" if data == "buy_telegram" else "WhatsApp"
            price = 50 if service == "Telegram" else 45

            # Ensure user record exists
            ensure_user_exists(user_id, first_name, username)

            bal = get_balance(user_id)
            if bal < price:
                bot.answer_callback_query(call.id, "Insufficient balance")
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("💳 Recharge", callback_data="recharge"))
                bot.send_message(user_id, f"⚠️ Insufficient balance. Your balance is {format_currency(bal)}. Please recharge to buy {service}.", reply_markup=kb)
                return

            # Deduct and create order
            deduct_balance(user_id, price)
            order = {
                "user_id": user_id,
                "service": service,
                "country": "USA",
                "price": price,
                "created_at": datetime.utcnow(),
                "status": "processing"
            }
            order_id = orders_col.insert_one(order).inserted_id

            # Notify user
            bot.answer_callback_query(call.id, f"{service} order placed")
            bot.send_message(user_id, f"✅ Payment of {format_currency(price)} deducted from your wallet.\n🔧 Your {service} number is now being generated. Please wait...\n\nIf admin needs to contact you, they will start a chat.", parse_mode="HTML")

            # Notify admin with chat button
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Chat with User", callback_data=f"chat|{user_id}"))
            bot.send_message(ADMIN_ID, f"📦 New Order\nUser: <a href='tg://user?id={user_id}'>{user_id}</a>\nService: {service}\nPrice: {format_currency(price)}\nOrder ID: <code>{order_id}</code>", parse_mode="HTML", reply_markup=kb)

            # keep stage done
            user_stage[user_id] = "done"
            return

        # ---------- Recharge entry ----------
        if data == "recharge":
            user_stage[user_id] = "enter_amount"
            bot.send_message(user_id, "💳 Enter amount to add to wallet (e.g., 50 or 100):")
            return

        # ---------- Admin: start refund flow ----------
        if data == "refund_start":
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "Unauthorized")
                return
            msg = bot.send_message(ADMIN_ID, "💸 Enter user ID for refund:")
            bot.register_next_step_handler(msg, ask_refund_user)
            return

        # ---------- Admin: Approve/Cancel recharge ----------
        if data.startswith(("approve_rech|","cancel_rech|")):
            parts = data.split("|")
            action = parts[0]  # approve_rech or cancel_rech
            req_id = parts[1] if len(parts) > 1 else None
            req = recharges_col.find_one({"req_id": req_id}) if req_id else None
            if not req:
                bot.send_message(ADMIN_ID, "⚠️ Recharge request not found or already processed.")
                return

            user_target = req.get("user_id")
            amount = float(req.get("amount", 0))

            if action == "approve_rech":
                # Add balance
                add_balance(user_target, amount)
                recharges_col.update_one({"req_id": req_id}, {"$set": {"status": "approved", "processed_at": datetime.utcnow(), "processed_by": ADMIN_ID}})
                bot.send_message(user_target, f"✅ Your recharge of {format_currency(amount)} has been approved and added to your wallet.")
                bot.send_message(ADMIN_ID, f"✅ Recharge approved and {format_currency(amount)} added to user {user_target}.")
            else:
                recharges_col.update_one({"req_id": req_id}, {"$set": {"status": "cancelled", "processed_at": datetime.utcnow(), "processed_by": ADMIN_ID}})
                bot.send_message(user_target, f"❌ Your recharge request of {format_currency(amount)} was cancelled by admin.")
                bot.send_message(ADMIN_ID, f"❌ Recharge cancelled for user {user_target}.")
            return

        # ---------- Admin: start chat with user ----------
        if data.startswith("chat|"):
            try:
                target_id = int(data.split("|",1)[1])
            except Exception:
                bot.send_message(ADMIN_ID, "Invalid chat target.")
                return
            active_chats[target_id] = True
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🛑 End this Chat", callback_data=f"endchat|{target_id}"))
            try:
                bot.send_message(target_id, "💬 Admin connected with you.")
            except Exception:
                bot.send_message(ADMIN_ID, "⚠️ Could not start chat (user may have blocked bot).")
                return
            bot.send_message(ADMIN_ID, f"💬 Chat started with user {target_id}", reply_markup=kb)
            return

        if data.startswith("endchat|"):
            try:
                target_id = int(data.split("|",1)[1])
            except Exception:
                bot.send_message(ADMIN_ID, "Invalid target.")
                return
            bot.send_message(ADMIN_ID, f"💬 Type final message to user {target_id}:")
            # register next step to send final message
            def finish_handler(m):
                finish_chat(m, target_id)
            msg = bot.send_message(ADMIN_ID, "Type final message:")
            bot.register_next_step_handler(msg, finish_handler)
            return

        # ---------- Broadcast menu (Admin) ----------
        if data == "broadcast_menu":
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "Unauthorized")
                return
            bot.send_message(ADMIN_ID, "Reply to a message (or send one) to broadcast to all users. Then send /sendbroadcast")
            return

        # default fallback
        bot.answer_callback_query(call.id, "Unknown action")
    except Exception as e:
        logging.exception("Error in callback handler:")
        try:
            bot.send_message(ADMIN_ID, f"Callback handler error:\n{e}")
        except:
            pass

# -----------------------
# REFUND SYSTEM (ADMIN)
# -----------------------
def ask_refund_user(message):
    try:
        refund_user_id = int(message.text)
        msg = bot.send_message(ADMIN_ID, "💰 Enter refund amount:")
        bot.register_next_step_handler(msg, process_refund, refund_user_id)
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ Invalid user ID. Please enter numeric ID only.")

def process_refund(message, refund_user_id):
    try:
        amount = float(message.text)
        user = users_col.find_one({"user_id": refund_user_id})

        if not user:
            bot.send_message(ADMIN_ID, "⚠️ User not found in database.")
            return

        # Add refund amount to wallet
        add_balance(refund_user_id, amount)
        new_balance = get_balance(refund_user_id)

        bot.send_message(ADMIN_ID, f"✅ Refunded {format_currency(amount)} to user {refund_user_id}\n💰 New Balance: {format_currency(new_balance)}")

        try:
            bot.send_message(refund_user_id, f"💸 {format_currency(amount)} added to your wallet!\n💰 New Balance: {format_currency(new_balance)} ✅")
        except Exception:
            bot.send_message(ADMIN_ID, "⚠️ Could not DM the user (maybe blocked).")

    except ValueError:
        bot.send_message(ADMIN_ID, "❌ Invalid amount entered. Please enter a number.")
    except Exception as e:
        logging.exception("Error in process_refund:")
        bot.send_message(ADMIN_ID, f"Error processing refund: {e}")

# -----------------------
# BROADCAST HANDLER (admin)
# -----------------------
def process_broadcast(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.chat.id, "❌ Unauthorized.")
        return
    source = msg.reply_to_message if msg.reply_to_message else msg
    text = getattr(source, "text", None) or getattr(source, "caption", "") or ""
    is_photo = bool(getattr(source, "photo", None))
    is_video = getattr(source, "video", None) is not None
    is_document = getattr(source, "document", None) is not None
    bot.send_message(ADMIN_ID, "📡 Broadcasting started... Please wait.")
    threading.Thread(target=broadcast_thread, args=(source, text, is_photo, is_video, is_document)).start()

def broadcast_thread(source_msg, text, is_photo, is_video, is_document):
    users = list(users_col.find())
    total = len(users)
    sent = 0
    failed = 0
    progress_interval = 25
    for user in users:
        uid = user.get("user_id")
        if not uid or uid == ADMIN_ID:
            continue
        try:
            if is_photo and getattr(source_msg, "photo", None):
                bot.send_photo(uid, photo=source_msg.photo[-1].file_id, caption=text or "")
            elif is_video and getattr(source_msg, "video", None):
                bot.send_video(uid, video=source_msg.video.file_id, caption=text or "")
            elif is_document and getattr(source_msg, "document", None):
                bot.send_document(uid, document=source_msg.document.file_id, caption=text or "")
            else:
                bot.send_message(uid, f"📢 Broadcast:\n{text}")
            sent += 1
            if sent % progress_interval == 0:
                try:
                    bot.send_message(ADMIN_ID, f"✅ Sent {sent}/{total} users...")
                except Exception:
                    pass
            time.sleep(0.06)
        except Exception as e:
            failed += 1
            print(f"❌ Broadcast failed for {uid}: {e}")
    try:
        bot.send_message(ADMIN_ID, f"🎯 Broadcast completed!\n✅ Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {total}")
    except Exception:
        pass

# -----------------------
# FINISH CHAT FUNCTION
# -----------------------
def finish_chat(msg, target_id):
    final_text = (msg.text or "").strip()
    if not final_text:
        bot.send_message(ADMIN_ID, "⚠️ Cannot send empty message.")
        return
    if target_id in active_chats and active_chats[target_id]:
        try:
            bot.send_message(target_id, final_text)
        except Exception:
            bot.send_message(ADMIN_ID, f"⚠️ Could not send message to {target_id}.")
        active_chats.pop(target_id, None)
        bot.send_message(ADMIN_ID, f"💬 Chat with user {target_id} ended.")
    else:
        bot.send_message(ADMIN_ID, "⚠️ No active chat to end.")

# -----------------------
# MESSAGE HANDLER (main)
# -----------------------
@bot.message_handler(func=lambda m: True, content_types=['text','photo','video','document'])
def chat_handler(msg):
    user_id = msg.from_user.id
    ensure_user_exists(user_id, msg.from_user.first_name or "Unknown", msg.from_user.username)

    # ADMIN typing while in active_chat => forward to user(s)
    if user_id == ADMIN_ID:
        for uid, active in list(active_chats.items()):
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
        # admin messages may also be used for broadcast command
        if msg.text and msg.text.strip().lower() == "/sendbroadcast":
            process_broadcast(msg)
        return

    # If user is in active chat with admin: forward messages to admin
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

    # ---- Recharge: entering amount
    if user_stage.get(user_id) == "enter_amount" and msg.content_type == 'text':
        text = msg.text.strip()
        if not text.isdigit():
            bot.send_message(user_id, "⚠️ Enter a valid numeric amount (e.g., 50).")
            return
        amount = float(text)
        pending_messages[user_id] = {"recharge_amount": amount}
        user_stage[user_id] = "waiting_recharge_proof"

        # Send QR image and instruction
        bot.send_photo(user_id, "https://files.catbox.moe/8rpxez.jpg", caption=f"💳 Pay ₹{int(amount)} using the QR above.\nAfter payment, send your 12-digit UTR number or a screenshot of payment here.")
        return

    # ---- Recharge: user sends UTR or screenshot
    if user_stage.get(user_id) == "waiting_recharge_proof":
        pending_messages.setdefault(user_id, {})
        amount = pending_messages[user_id].get("recharge_amount", 0)
        if msg.content_type == 'text':
            text = msg.text.strip()
            if not text.isdigit() or len(text) != 12:
                bot.send_message(user_id, "⚠️ Please enter a valid 12-digit UTR or send a screenshot.")
                return
            pending_messages[user_id]['utr'] = text
            proof_text = f"UTR: {text}"
        elif msg.content_type == 'photo':
            pending_messages[user_id]['screenshot'] = msg.photo[-1].file_id
            proof_text = "📸 Screenshot provided"
        else:
            bot.send_message(user_id, "⚠️ Please send 12-digit UTR or a screenshot photo.")
            return

        # create recharge request with a custom req_id
        req_id = f"R{int(time.time())}{user_id}"
        recharge_doc = {
            "req_id": req_id,
            "user_id": user_id,
            "amount": amount,
            "utr": pending_messages[user_id].get('utr'),
            "screenshot": pending_messages[user_id].get('screenshot'),
            "status": "pending",
            "requested_at": datetime.utcnow()
        }
        recharges_col.insert_one(recharge_doc)

        # notify user
        bot.send_message(user_id, "🔄 Your recharge request has been sent for verification. Please wait for admin approval.", parse_mode="HTML")

        # notify admin with Approve/Cancel buttons
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_rech|{req_id}"),
               InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_rech|{req_id}"))
        admin_text = (f"💳 <b>Recharge Request</b>\n"
                      f"User: <a href='tg://user?id={user_id}'>{user_id}</a>\n"
                      f"Amount: {format_currency(amount)}\n"
                      f"Req ID: <code>{req_id}</code>\n")
        if 'utr' in pending_messages[user_id]:
            admin_text += f"UTR: {pending_messages[user_id]['utr']}\n"
            bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=kb)
        else:
            # send screenshot to admin with caption
            bot.send_photo(ADMIN_ID, pending_messages[user_id]['screenshot'], caption=admin_text, parse_mode="HTML", reply_markup=kb)

        # cleanup
        user_stage[user_id] = "done"
        pending_messages.pop(user_id, None)
        return

    # ---- Payment UTR stage for other flows (if any) - default message
    bot.send_message(user_id, "⚠️ Please use /start to begin or press buttons from the menu.")

# -----------------------
# RUN BOT
# -----------------------
if __name__ == "__main__":
    print("✅ Bot running successfully...")
    bot.infinity_polling(skip_pending=True)
