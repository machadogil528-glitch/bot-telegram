import logging
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = "8605323770:AAGTooVrn6aq3CfXMtCa40LpTxDCPt7MzxI"
CHAT_ID = 5866187111
INTERVALO = 20

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("dados.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estrategia TEXT,
    resultado TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS enviados (
    fixture_id INTEGER UNIQUE
)
""")

conn.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot rodando com detector avançado!")


async def resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT resultado, COUNT(*) 
        FROM resultados 
        GROUP BY resultado
    """)
    dados = dict(cursor.fetchall())

    win = dados.get("WIN", 0)
    loss = dados.get("LOSS", 0)
    reembolso = dados.get("REEMBOLSO", 0)

    lucro = (win * 10) - (loss * 10)

    await update.message.reply_text(f"""
📊 RESULTADOS

✅ WIN: {win}
❌ LOSS: {loss}
🔁 REEMBOLSO: {reembolso}

💰 Lucro estimado: {lucro}
""")


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    resultado = query.data

    cursor.execute(
        "INSERT INTO resultados (estrategia, resultado) VALUES (?, ?)",
        ("GOL HT", resultado)
    )
    conn.commit()

    await query.edit_message_text(f"✅ Resultado marcado: {resultado}")


def buscar():
    return [
        {
            "fixture": {"id": 1001, "status": {"elapsed": 12}},
            "teams": {
                "home": {"name": "Time Pressão Forte"},
                "away": {"name": "Time Recuado"}
            },
            "goals": {"home": 0, "away": 0},
            "statistics": [
                {"statistics": [
                    {"type": "Ball Possession", "value": "69%"},
                    {"type": "Dangerous Attacks", "value": 31},
                    {"type": "Total Shots", "value": 6},
                    {"type": "Shots on Goal", "value": 2},
                    {"type": "Corner Kicks", "value": 4}
                ]},
                {"statistics": [
                    {"type": "Ball Possession", "value": "31%"},
                    {"type": "Dangerous Attacks", "value": 6},
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Corner Kicks", "value": 0}
                ]}
            ]
        }
    ]


def numero(valor):
    if valor is None:
        return 0
    try:
        return int(str(valor).replace("%", ""))
    except:
        return 0


def pegar_valor(lista, nome):
    for item in lista:
        if item["type"] == nome:
            return numero(item["value"])
    return 0


def extrair(jogo):
    stats = jogo.get("statistics", [])

    if len(stats) < 2:
        return None

    casa_stats = stats[0]["statistics"]
    fora_stats = stats[1]["statistics"]

    casa = {
        "nome": jogo["teams"]["home"]["name"],
        "posse": pegar_valor(casa_stats, "Ball Possession"),
        "ataques": pegar_valor(casa_stats, "Dangerous Attacks"),
        "finalizacoes": pegar_valor(casa_stats, "Total Shots"),
        "chutes": pegar_valor(casa_stats, "Shots on Goal"),
        "escanteios": pegar_valor(casa_stats, "Corner Kicks"),
    }

    fora = {
        "nome": jogo["teams"]["away"]["name"],
        "posse": pegar_valor(fora_stats, "Ball Possession"),
        "ataques": pegar_valor(fora_stats, "Dangerous Attacks"),
        "finalizacoes": pegar_valor(fora_stats, "Total Shots"),
        "chutes": pegar_valor(fora_stats, "Shots on Goal"),
        "escanteios": pegar_valor(fora_stats, "Corner Kicks"),
    }

    dominante = casa if casa["ataques"] >= fora["ataques"] else fora

    return {
        "fixture": jogo["fixture"]["id"],
        "minuto": jogo["fixture"]["status"]["elapsed"] or 0,
        "casa": casa["nome"],
        "fora": fora["nome"],
        "gols_casa": jogo["goals"]["home"] or 0,
        "gols_fora": jogo["goals"]["away"] or 0,
        "dominante": dominante["nome"],
        "pressao": dominante["posse"],
        "ataques": dominante["ataques"],
        "finalizacoes": dominante["finalizacoes"],
        "chutes": dominante["chutes"],
        "escanteios": dominante["escanteios"],
    }


def detector_gol_ht(d):
    score = 0
    motivos = []

    minuto = d["minuto"]

    if minuto < 3 or minuto > 45:
        return None

    if d["pressao"] >= 60:
        score += 15
        motivos.append("pressão alta")

    if d["pressao"] >= 70:
        score += 10
        motivos.append("pressão muito forte")

    if d["ataques"] >= 20:
        score += 15
        motivos.append("ataques perigosos")

    if d["ataques"] >= 30:
        score += 15
        motivos.append("muitos ataques perigosos")

    if d["finalizacoes"] >= 4:
        score += 10
        motivos.append("bom volume de finalizações")

    if d["finalizacoes"] >= 7:
        score += 15
        motivos.append("volume ofensivo forte")

    if d["chutes"] >= 2:
        score += 15
        motivos.append("chutes no gol")

    if d["chutes"] >= 4:
        score += 15
        motivos.append("muitos chutes no gol")

    if d["escanteios"] >= 3:
        score += 10
        motivos.append("escanteios gerando pressão")

    if d["escanteios"] >= 5:
        score += 10
        motivos.append("muitos escanteios")

    if minuto <= 15 and (
        d["finalizacoes"] >= 4 or
        d["chutes"] >= 2 or
        d["escanteios"] >= 3
    ):
        score += 20
        motivos.append("padrão forte apareceu cedo")

    if score >= 75:
        nivel = "🔥 GOL HT - SINAL MUITO FORTE"
    elif score >= 60:
        nivel = "🔥 GOL HT - SINAL FORTE"
    elif score >= 50:
        nivel = "⚠️ GOL HT - SINAL MÉDIO"
    else:
        return None

    return {
        "nivel": nivel,
        "score": score,
        "motivos": motivos
    }


async def rodar(context: ContextTypes.DEFAULT_TYPE):
    jogos = buscar()

    for jogo in jogos:
        d = extrair(jogo)

        if not d:
            continue

        cursor.execute(
            "SELECT fixture_id FROM enviados WHERE fixture_id = ?",
            (d["fixture"],)
        )

        if cursor.fetchone():
            continue

        sinal = detector_gol_ht(d)

        if not sinal:
            continue

        cursor.execute(
            "INSERT OR IGNORE INTO enviados (fixture_id) VALUES (?)",
            (d["fixture"],)
        )
        conn.commit()

        teclado = [[
            InlineKeyboardButton("✅ WIN", callback_data="WIN"),
            InlineKeyboardButton("❌ LOSS", callback_data="LOSS"),
            InlineKeyboardButton("🔁 REEMBOLSO", callback_data="REEMBOLSO")
        ]]

        mensagem = f"""
🚨 ALERTA DE GOL HT

{sinal['nivel']}
📊 Score: {sinal['score']}/100

🏆 Jogo:
{d['casa']} x {d['fora']}

⏱ Minuto: {d['minuto']}'
⚽ Placar: {d['gols_casa']} x {d['gols_fora']}

🔥 Time com melhor momento:
{d['dominante']}

📈 Dados:
Pressão/posse: {d['pressao']}%
Ataques perigosos: {d['ataques']}
Finalizações: {d['finalizacoes']}
Chutes no gol: {d['chutes']}
Escanteios: {d['escanteios']}

🧠 Motivos:
{', '.join(sinal['motivos'])}
"""

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=mensagem,
            reply_markup=InlineKeyboardMarkup(teclado)
        )


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
