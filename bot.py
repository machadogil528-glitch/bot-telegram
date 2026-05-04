import logging
import sqlite3
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= CONFIG =================

TELEGRAM_TOKEN = "8605323770:AAGTooVrn6aq3CfXMtCa40LpTxDCPt7MzxI"
CHAT_ID = 5866187111

INTERVALO = 10  # manda rápido pra teste

logging.basicConfig(level=logging.INFO)

# ================= BANCO =================

conn = sqlite3.connect("dados.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resultado TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS enviados (
    fixture_id INTEGER UNIQUE
)
""")

conn.commit()

# ================= COMANDOS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot rodando!")

async def resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT resultado, COUNT(*) FROM resultados GROUP BY resultado")
    dados = dict(cursor.fetchall())

    await update.message.reply_text(f"""
📊 RESULTADOS

✅ WIN: {dados.get('WIN',0)}
❌ LOSS: {dados.get('LOSS',0)}
🔁 REEMBOLSO: {dados.get('REEMBOLSO',0)}
""")

# ================= BOTÕES =================

async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cursor.execute("INSERT INTO resultados (resultado) VALUES (?)", (query.data,))
    conn.commit()

    await query.edit_message_text(f"Marcado: {query.data}")

# ================= DADOS FAKE =================

def buscar():
    return [
        {
            "fixture": {"id": 999001, "status": {"elapsed": 12}},
            "teams": {
                "home": {"name": "Time Teste Casa"},
                "away": {"name": "Time Teste Fora"}
            },
            "goals": {"home": 0, "away": 0},
            "statistics": [
                {
                    "statistics": [
                        {"type": "Ball Possession", "value": "68%"},
                        {"type": "Dangerous Attacks", "value": 28},
                        {"type": "Total Shots", "value": 5},
                        {"type": "Shots on Goal", "value": 2},
                        {"type": "Corner Kicks", "value": 3}
                    ]
                },
                {
                    "statistics": [
                        {"type": "Ball Possession", "value": "32%"},
                        {"type": "Dangerous Attacks", "value": 5},
                        {"type": "Total Shots", "value": 1},
                        {"type": "Shots on Goal", "value": 0},
                        {"type": "Corner Kicks", "value": 0}
                    ]
                }
            ]
        }
    ]

# ================= EXTRAIR =================

def extrair(j):
    stats = j.get("statistics", [])

    def val(d, key):
        for i in d:
            if i["type"] == key:
                return int(str(i["value"]).replace("%", "") or 0)
        return 0

    casa = stats[0]["statistics"]

    return {
        "fixture": j["fixture"]["id"],
        "minuto": j["fixture"]["status"]["elapsed"],
        "casa": j["teams"]["home"]["name"],
        "fora": j["teams"]["away"]["name"],
        "gols_casa": j["goals"]["home"],
        "gols_fora": j["goals"]["away"],
        "pressao": val(casa, "Ball Possession"),
        "ataques": val(casa, "Dangerous Attacks"),
        "finalizacoes": val(casa, "Total Shots"),
        "chutes": val(casa, "Shots on Goal"),
        "escanteios": val(casa, "Corner Kicks"),
    }

# ================= DETECTOR =================

def detectar(d):
    score = 0

    if d["pressao"] >= 60:
        score += 20
    if d["ataques"] >= 20:
        score += 20
    if d["finalizacoes"] >= 4:
        score += 15
    if d["chutes"] >= 2:
        score += 15
    if d["escanteios"] >= 3:
        score += 10

    if score >= 70:
        return f"🔥 SINAL FORTE ({score})"
    if score >= 50:
        return f"⚠️ SINAL MÉDIO ({score})"

    return None

# ================= LOOP =================

async def rodar(context: ContextTypes.DEFAULT_TYPE):
    jogos = buscar()

    for j in jogos:
        d = extrair(j)

        cursor.execute("SELECT * FROM enviados WHERE fixture_id = ?", (d["fixture"],))
        if cursor.fetchone():
            continue

        sinal = detectar(d)

        if sinal:
            cursor.execute("INSERT OR IGNORE INTO enviados VALUES (?)", (d["fixture"],))
            conn.commit()

            teclado = [[
                InlineKeyboardButton("✅ WIN", callback_data="WIN"),
                InlineKeyboardButton("❌ LOSS", callback_data="LOSS"),
                InlineKeyboardButton("🔁 REEMBOLSO", callback_data="REEMBOLSO")
            ]]

            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"""
🚨 GOL HT

{sinal}

{d['casa']} x {d['fora']}
⏱ {d['minuto']}'
⚽ {d['gols_casa']} x {d['gols_fora']}
""",
                reply_markup=InlineKeyboardMarkup(teclado)
            )

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resultado", resultado))
    app.add_handler(CallbackQueryHandler(botoes))

    app.job_queue.run_repeating(rodar, interval=INTERVALO, first=5)

    print("Bot ON 🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
