import asyncio from pyrogram import Client, filters from pyrogram.types import Message import httpx from config import API_KEY, BOT_TOKEN, ADMIN_ID, API_ID, API_HASH

app = Client( "SMMBot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH )

user_data = {}

@app.on_message(filters.command("start")) async def start(_, m: Message): user_data[m.from_user.id] = {"balance": 0, "orders": []} await m.reply_text("Welcome to SMM Bot! Use /services to see available services.")

@app.on_message(filters.command("services")) async def services(_, m: Message): async with httpx.AsyncClient() as client: res = await client.post(API_KEY, data={"key": API_KEY, "action": "services"}) try: services = res.json() except: return await m.reply("❌ Failed to fetch services.")

text = "\U0001F6CD️ *Available Services:*\n\n"
    for srv in services[:10]:  # Show top 10 for readability
        text += f"\U0001F539 *{srv['service']}* - {srv['name']}\n\U0001F4B0 {srv['rate']} | {srv['min']}–{srv['max']}\n\n"
    await m.reply_text(text)

@app.on_message(filters.command("balance")) async def balance(_, m: Message): uid = m.from_user.id bal = user_data.get(uid, {}).get("balance", 0) await m.reply_text(f"\U0001F4B0 Your wallet balance: ₹{bal}")

@app.on_message(filters.command("order")) async def order(_, m: Message): parts = m.text.split() if len(parts) < 4: return await m.reply_text("Usage: /order service_id link quantity")

service, link, qty = parts[1], parts[2], parts[3]
uid = m.from_user.id

async with httpx.AsyncClient() as client:
    res = await client.post(API_KEY, data={
        "key": API_KEY,
        "action": "add",
        "service": service,
        "link": link,
        "quantity": qty,
    })
    try:
        result = res.json()
    except:
        return await m.reply("❌ Error placing order.")

    if "order" in result:
        user_data[uid]["orders"].append(result["order"])
        return await m.reply_text(f"✅ Order placed successfully!\n🆔 Order ID: {result['order']}")
    else:
        return await m.reply_text(f"❌ Error: {result.get('error', 'Unknown error')}")

@app.on_message(filters.command("status")) async def status(_, m: Message): parts = m.text.split() if len(parts) != 2: return await m.reply_text("Usage: /status order_id")

oid = parts[1]
async with httpx.AsyncClient() as client:
    res = await client.post(API_KEY, data={"key": API_KEY, "action": "status", "order": oid})
    try:
        data = res.json()
    except:
        return await m.reply("❌ Failed to fetch order status.")

    msg = f"📦 Order Status:\nStatus: {data['status']}\nStart: {data['start_count']}\nRemains: {data['remains']}\nCharge: ${data['charge']}"
    await m.reply_text(msg)

app.run()

