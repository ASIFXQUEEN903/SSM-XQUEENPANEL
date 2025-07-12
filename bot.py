import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import httpx
from config import API_KEY, BOT_TOKEN, ADMIN_ID, API_ID, API_HASH

app = Client(
    "SMMBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

user_data = {}

@app.on_message(filters.command("start"))
async def start(_, m: Message):
    user_data[m.from_user.id] = {"balance": 0, "orders": []}
    await m.reply_text("👋 Welcome to *XQUEEN SMM Bot!*\nUse /services to see available SMM services.")

@app.on_message(filters.command("services"))
async def services(_, m: Message):
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(API_KEY, data={"key": API_KEY, "action": "services"})
            services = res.json()
            if not isinstance(services, list):
                raise ValueError("Invalid API response format.")
        except Exception as e:
            return await m.reply_text(f"❌ Failed to fetch services.\n\n`{str(e)}`")

        text = "🛍️ *Available Services:*\n\n"
        for srv in services[:10]:  # Limit to 10 for readability
            if isinstance(srv, dict):
                text += (
                    f"🔹 *{srv.get('service')}* - {srv.get('name')}\n"
                    f"💰 Rate: {srv.get('rate')} | Min: {srv.get('min')} | Max: {srv.get('max')}\n\n"
                )
        await m.reply_text(text or "❌ No services found.")

@app.on_message(filters.command("balance"))
async def balance(_, m: Message):
    uid = m.from_user.id
    bal = user_data.get(uid, {}).get("balance", 0)
    await m.reply_text(f"💰 Your wallet balance: ₹{bal}")

@app.on_message(filters.command("order"))
async def order(_, m: Message):
    parts = m.text.split()
    if len(parts) < 4:
        return await m.reply_text("⚠️ Usage: `/order service_id link quantity`", quote=True)

    service, link, qty = parts[1], parts[2], parts[3]
    uid = m.from_user.id

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(API_KEY, data={
                "key": API_KEY,
                "action": "add",
                "service": service,
                "link": link,
                "quantity": qty,
            })
            result = res.json()
        except Exception as e:
            return await m.reply_text(f"❌ Error placing order.\n\n`{str(e)}`")

        if "order" in result:
            user_data[uid]["orders"].append(result["order"])
            return await m.reply_text(f"✅ Order placed successfully!\n🆔 Order ID: `{result['order']}`")
        else:
            return await m.reply_text(f"❌ Error: `{result.get('error', 'Unknown error')}`")

@app.on_message(filters.command("status"))
async def status(_, m: Message):
    parts = m.text.split()
    if len(parts) != 2:
        return await m.reply_text("⚠️ Usage: `/status order_id`", quote=True)

    oid = parts[1]
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(API_KEY, data={"key": API_KEY, "action": "status", "order": oid})
            data = res.json()
        except Exception as e:
            return await m.reply_text(f"❌ Failed to fetch status.\n\n`{str(e)}`")

        msg = (
            f"📦 *Order Status:*\n"
            f"🆔 Order ID: `{oid}`\n"
            f"📈 Status: `{data.get('status')}`\n"
            f"📊 Start Count: `{data.get('start_count')}`\n"
            f"📉 Remains: `{data.get('remains')}`\n"
            f"💸 Charge: `${data.get('charge')}`"
        )
        await m.reply_text(msg)

app.run()
