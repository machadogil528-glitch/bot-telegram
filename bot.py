from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

TOKEN = "8605323770:AAGTooVrn6aq3CfXMtCa40LpTxDCPt7MzxI"

async def clicar(update, context):
    query = update.callback_query
    await query.answer()

    if "win" in query.data:
        await query.edit_message_text("✅ WIN registrado")
    else:
        await query.edit_message_text("❌ LOSS registrado")

async def start(update, context):
    keyboard = [
        [
            InlineKeyboardButton("✅ WIN", callback_data="win"),
            InlineKeyboardButton("❌ LOSS", callback_data="loss")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔥 Teste de botões",
        reply_markup=reply_markup
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(clicar))

app.run_polling()
