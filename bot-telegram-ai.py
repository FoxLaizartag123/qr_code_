import segno
import stripe
import sqlite3
from io import BytesIO
from PIL import Image, ImageDraw

from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = "8714786580:AAFIe5giVn9y6i4Ypq1UVk3ugrY3oWu33m0"

stripe.api_key = "rk_test_51RD1iPP2dZ0v0hXpfqSUTXLnAhtk0LvudBmlFiTjaCvxqSGDyYUasCy2zcGMeF7eWf8j5v4hPoAzjJACjkhMODJt0057sTqofN"
STRIPE_WEBHOOK_SECRET = "https://qr-code-4-he8e.onrender.com"


PAYMENT_BASIC = "https://buy.stripe.com/test_9B66oJ7I091V8Xxc4o5Ne00"
PAYMENT_PRO = "https://buy.stripe.com/test_eVqbJ38M46TN2z90lG5Ne01"

app_web = FastAPI()

conn = sqlite3.connect("saas.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    plan TEXT,
    usage INTEGER
)
""")
conn.commit()

user_style = {}
user_color = {}
user_gallery = {}

def get_user(uid):
    cursor.execute("SELECT plan, usage FROM users WHERE id=?", (uid,))
    return cursor.fetchone()

def create_user(uid):
    if not get_user(uid):
        cursor.execute("INSERT INTO users VALUES (?, 'free', 0)", (uid,))
        conn.commit()

def set_plan(uid, plan):
    create_user(uid)
    cursor.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
    conn.commit()

def can_generate(uid):
    create_user(uid)
    plan, usage = get_user(uid)

    limits = {
        "free": 1,
        "basic": 50,
        "pro": 10**9
    }

    if usage >= limits.get(plan, 1):
        return False, plan

    cursor.execute("UPDATE users SET usage=usage+1 WHERE id=?", (uid,))
    conn.commit()
    return True, plan

def build_qr(text, color="#000000"):
    qr = segno.make(text, error="h")

    bio = BytesIO()
    qr.save(bio, kind="png", scale=10, dark=color, light="white")
    bio.seek(0)

    img = Image.open(bio).convert("RGBA")

    canvas = Image.new(
        "RGBA",
        (img.size[0] + 40, img.size[1] + 40),
        (255, 255, 255, 255)
    )

    canvas.paste(img, (20, 20), img)

    draw = ImageDraw.Draw(canvas)
    draw.rectangle(
        [5, 5, canvas.size[0] - 5, canvas.size[1] - 5],
        outline=color,
        width=3
    )

    return canvas

@app_web.post("/stripe/webhook")
async def stripe_webhook(req: Request):
    payload = await req.body()
    sig = req.headers.get("stripe-signature")

    event = stripe.Webhook.construct_event(
        payload,
        sig,
        STRIPE_WEBHOOK_SECRET
    )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        uid = int(session["metadata"]["telegram_id"])
        plan = session["metadata"]["plan"]

        set_plan(uid, plan)

    return {"ok": True}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 QR ENGINE PRO\n\n"
        "🟢 FREE: 1 QR\n🟡 BASIC: 50 QR\n🔵 PRO: ilimitado\n\n"
        "💳 /upgrade\n/qr texto"
    )

async def upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    basic = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_BASIC, "quantity": 1}],
        metadata={"telegram_id": str(uid), "plan": "basic"},
        success_url="https://t.me",
        cancel_url="https://t.me"
    )

    pro = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_PRO, "quantity": 1}],
        metadata={"telegram_id": str(uid), "plan": "pro"},
        success_url="https://t.me",
        cancel_url="https://t.me"
    )

    keyboard = [
        [InlineKeyboardButton("BASIC", url=basic.url)],
        [InlineKeyboardButton("PRO", url=pro.url)]
    ]

    await update.message.reply_text(
        "Escolhe plano:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = " ".join(context.args)

    if not text:
        return await update.message.reply_text("Uso: /qr texto")

    ok, plan = can_generate(uid)

    if not ok:
        return await update.message.reply_text(
            "⛔ Limite atingido. Usa /upgrade"
        )

    img = build_qr(text)

    bio = BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)

    await update.message.reply_photo(bio)

async def auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    ok, plan = can_generate(uid)

    if not ok:
        return await update.message.reply_text("⛔ Limite atingido")

    img = build_qr(text)

    bio = BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)

    await update.message.reply_photo(bio)

def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qr", qr))
    app.add_handler(CommandHandler("upgrade", upgrade))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto))

    app.run_polling()

if __name__ == "__main__":
    from threading import Thread
    import uvicorn

    Thread(target=run_bot).start()
    uvicorn.run(app_web, host="0.0.0.0", port=8000)
