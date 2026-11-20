
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PAYMENT_NUMBERS = {
    "bkash": os.getenv("BKASH_NUMBER", "YOUR_BKASH_NUMBER"),
    "nagad": os.getenv("NAGAD_NUMBER", "YOUR_NAGAD_NUMBER"),
    "rocket": os.getenv("ROCKET_NUMBER", "YOUR_ROCKET_NUMBER"),
}

METHOD, AMOUNT, TRANSACTION = range(3)

def init_db():
    with sqlite3.connect("payments.db") as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                method TEXT,
                amount TEXT,
                trx_id TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)

def save_payment(user, method, amount, trx_id):
    with sqlite3.connect("payments.db") as db:
        cur = db.execute("""
            INSERT INTO payments
            (user_id, name, method, amount, trx_id)
            VALUES (?, ?, ?, ?, ?)
        """, (user.id, user.full_name, method, amount, trx_id))
        return cur.lastrowid

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("bKash", callback_data="bkash")],
        [InlineKeyboardButton("Nagad", callback_data="nagad")],
        [InlineKeyboardButton("Rocket", callback_data="rocket")]
    ]
    await update.message.reply_text(
        "স্বাগতম! ❤️\nপেমেন্ট মাধ্যম নির্বাচন করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return METHOD

async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data
    context.user_data["method"] = method
    number = PAYMENT_NUMBERS[method]

    await query.message.reply_text(
        f"{method.upper()} নম্বর: {number}\n"
        "টাকা পাঠিয়ে কত টাকা পাঠিয়েছেন লিখুন:"
    )
    return AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text.strip()
    if not amount.isdigit() or int(amount) <= 0:
        await update.message.reply_text("সঠিক টাকার পরিমাণ লিখুন।")
        return AMOUNT

    context.user_data["amount"] = amount
    await update.message.reply_text("আপনার Transaction ID পাঠান:")
    return TRANSACTION

async def enter_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx_id = update.message.text.strip()
    if len(trx_id) < 5 or len(trx_id) > 100:
        await update.message.reply_text("সঠিক Transaction ID দিন।")
        return TRANSACTION

    user = update.effective_user
    method = context.user_data["method"]
    amount = context.user_data["amount"]
    payment_id = save_payment(user, method, amount, trx_id)

    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{payment_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:{payment_id}")
    ]]

    if ADMIN_ID:
        await context.bot.send_message(
            ADMIN_ID,
            f"নতুন পেমেন্ট #{payment_id}\n"
            f"নাম: {user.full_name}\n"
            f"User ID: {user.id}\n"
            f"মাধ্যম: {method.upper()}\n"
            f"পরিমাণ: {amount} টাকা\n"
            f"Transaction ID: {trx_id}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await update.message.reply_text(
        "আপনার পেমেন্ট তথ্য জমা হয়েছে। অ্যাডমিন যাচাই করবেন। ❤️"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID or not ADMIN_ID:
        await query.message.reply_text("অনুমতি নেই।")
        return

    action, payment_id = query.data.split(":")
    payment_id = int(payment_id)
    status = "approved" if action == "approve" else "rejected"

    with sqlite3.connect("payments.db") as db:
        cur = db.execute(
            "UPDATE payments SET status=? WHERE id=? AND status='pending'",
            (status, payment_id)
        )
        if cur.rowcount == 0:
            await query.message.reply_text("এই পেমেন্ট আগেই যাচাই করা হয়েছে।")
            return
        result = db.execute(
            "SELECT user_id FROM payments WHERE id=?", (payment_id,)
        ).fetchone()

    message = (
        "✅ আপনার পেমেন্ট অনুমোদিত হয়েছে!"
        if status == "approved"
        else "❌ আপনার পেমেন্ট বাতিল হয়েছে।"
    )
    await context.bot.send_message(result[0], message)
    await query.edit_message_text(query.message.text + "\n\n" + status.upper())

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"আপনার Telegram ID: {update.effective_user.id}"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("পেমেন্ট বাতিল হয়েছে।")
    return ConversationHandler.END

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN সেট করা হয়নি।")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    payment_flow = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            METHOD: [CallbackQueryHandler(choose_method, pattern="^(bkash|nagad|rocket)$")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            TRANSACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_transaction)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(payment_flow)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^(approve|reject):\d+$"))

    print("Payment Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
