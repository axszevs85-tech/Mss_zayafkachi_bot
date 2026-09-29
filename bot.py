import os
import sqlite3
import logging

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatJoinRequestHandler, ConversationHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)

# ---- Railway Variables ----
TOKEN = os.environ["BOT_TOKEN=8656378230:AAFAkTUBY13ty_UB7xjVmi7HxvG9I_iR9Qo"]
ADMIN_ID = int(os.environ["ADMIN_ID=8756103290"])            # sizning Telegram ID raqamingiz
PRICE = int(os.getenv("PRICE_PER_SUB", "300"))    # 1 ta obunachi narxi (so'm)
MIN_QTY = int(os.getenv("MIN_QTY", "50"))         # minimal buyurtma
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME=@MCHE_9804", "admin")  # to'lov uchun aloqa
DB_PATH = os.getenv("DB_PATH", "bot.db")

CHANNEL, QTY = range(2)

MENU = ReplyKeyboardMarkup(
    [["🛒 Buyurtma berish", "📦 Buyurtmalarim"], ["💰 Narx"]],
    resize_keyboard=True,
)


# ---------------- DB ----------------
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, name TEXT,
            created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            channel TEXT, qty INTEGER, price INTEGER,
            status TEXT DEFAULT 'kutilmoqda',
            created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER,
            user_id INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);
        """)


# ---------------- Foydalanuvchi ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users(id, name) VALUES(?, ?)",
                  (u.id, u.first_name))
    await update.message.reply_text(
        f"Salom, {u.first_name}! 👋\n"
        "Kanalingiz uchun jonli obunachi buyurtma qilishingiz mumkin.",
        reply_markup=MENU,
    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💰 1 ta jonli obunachi: {PRICE} so'm\n"
        f"Minimal buyurtma: {MIN_QTY} ta"
    )


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as c:
        rows = c.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (update.effective_user.id,),
        ).fetchall()
    if not rows:
        await update.message.reply_text("Sizda hali buyurtma yo'q.")
        return
    text = "\n\n".join(
        f"#{r['id']} | {r['channel']}\n{r['qty']} ta | {r['price']} so'm | {r['status']}"
        for r in rows
    )
    await update.message.reply_text("📦 Oxirgi buyurtmalaringiz:\n\n" + text)


# ---------------- Buyurtma berish ----------------
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kanalingiz havolasi yoki @username ni yuboring.\n"
        "Bekor qilish: /cancel"
    )
    return CHANNEL


async def order_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["channel"] = update.message.text.strip()
    await update.message.reply_text(
        f"Nechta obunachi kerak? (kamida {MIN_QTY} ta, faqat raqam)"
    )
    return QTY


async def order_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
        if qty < MIN_QTY:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"Iltimos, {MIN_QTY} yoki undan katta raqam kiriting.")
        return QTY

    u = update.effective_user
    channel = context.user_data["channel"]
    total = qty * PRICE
    with db() as c:
        cur = c.execute(
            "INSERT INTO orders(user_id, channel, qty, price) VALUES(?,?,?,?)",
            (u.id, channel, qty, total),
        )
        oid = cur.lastrowid

    await update.message.reply_text(
        f"✅ Buyurtma #{oid} qabul qilindi.\n"
        f"Kanal: {channel}\nMiqdor: {qty} ta\nNarx: {total} so'm\n\n"
        f"To'lov va tasdiqlash uchun @{ADMIN_USERNAME} bilan bog'laning.",
        reply_markup=MENU,
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Qabul", callback_data=f"ok:{oid}"),
        InlineKeyboardButton("❌ Rad", callback_data=f"no:{oid}"),
    ]])
    await context.bot.send_message(
        ADMIN_ID,
        f"🆕 Yangi buyurtma #{oid}\n"
        f"Foydalanuvchi: {u.first_name} (id {u.id})"
        f"{' @' + u.username if u.username else ''}\n"
        f"Kanal: {channel}\nMiqdor: {qty}\nNarx: {total} so'm",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.", reply_markup=MENU)
    return ConversationHandler.END


# ---------------- Admin ----------------
async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Ruxsat yo'q", show_alert=True)
        return
    action, oid = q.data.split(":")
    oid = int(oid)
    status = {"ok": "jarayonda", "no": "rad etildi", "done": "bajarildi"}[action]
    with db() as c:
        c.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
        o = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    await q.answer()

    kb = None
    if status == "jarayonda":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏁 Bajarildi", callback_data=f"done:{oid}")]]
        )
    await q.edit_message_text(
        f"Buyurtma #{oid} — {status}\n"
        f"Kanal: {o['channel']}\nMiqdor: {o['qty']}\nNarx: {o['price']} so'm",
        reply_markup=kb,
    )
    try:
        await context.bot.send_message(
            o["user_id"], f"Buyurtma #{oid} holati: {status}"
        )
    except Exception:
        pass


async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        pending = c.execute(
            "SELECT COUNT(*) FROM orders WHERE status='kutilmoqda'").fetchone()[0]
        reqs = c.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    await update.message.reply_text(
        f"👥 Foydalanuvchilar: {users}\n"
        f"📦 Buyurtmalar: {orders} (kutilmoqda: {pending})\n"
        f"📨 Qabul qilingan zayavkalar: {reqs}"
    )


# ---------------- Zayavka (join request) ----------------
async def join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    await req.approve()
    with db() as c:
        c.execute("INSERT INTO requests(chat_id, user_id) VALUES(?, ?)",
                  (req.chat.id, req.from_user.id))
    try:
        await context.bot.send_message(
            req.user_chat_id,
            f"Salom, {req.from_user.first_name}! "
            f"{req.chat.title} kanaliga qabul qilindingiz ✅",
        )
    except Exception:
        pass  # foydalanuvchi botni bloklagan bo'lishi mumkin


def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    order_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🛒 Buyurtma berish$"), order_start),
            CommandHandler("buyurtma", order_start),
        ],
        states={
            CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_channel)],
            QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_qty)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(order_conv)
    app.add_handler(MessageHandler(filters.Regex("^📦 Buyurtmalarim$"), my_orders))
    app.add_handler(MessageHandler(filters.Regex("^💰 Narx$"), price))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^(ok|no|done):\d+$"))
    app.add_handler(ChatJoinRequestHandler(join_request))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
  
