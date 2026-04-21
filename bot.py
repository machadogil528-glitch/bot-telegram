import sqlite3
import requests
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")
CHAT_ID = int(os.getenv("CHAT_ID", "5866187111"))

HEADERS = {
    "x-apisports-key": API_KEY
}

alertas_enviados = set()

def iniciar_banco():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS resultados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mercado TEXT NOT NULL,
        resultado TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def salvar_resultado(mercado, resultado):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO resultados (mercado, resultado) VALUES (?, ?)",
        (mercado, resultado)
    )
    conn.commit()
    conn.close()

def contar_resultados():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM resultados WHERE resultado='GREEN'")
    greens = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM resultados WHERE resultado='RED'")
    reds = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM resultados WHERE resultado='REEMBOLSO'")
    reembolsos = c.fetchone()[0]

    lucro = (greens * 10) - (reds * 10)

    conn.close()
    return greens, reds, reembolsos, lucro

def resumo_por_mercado():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    mercados = ["ESCANTEIO_HT", "GOL_HT", "GOL_FT", "AMBAS_MARCAM"]
    resumo = {}

    for mercado in mercados:
        c.execute(
            "SELECT COUNT(*) FROM resultados WHERE mercado=? AND resultado='GREEN'",
            (mercado,)
        )
        greens = c.fetchone()[0]

        c.execute(
            "SELECT COUNT(*) FROM resultados WHERE mercado=? AND resultado='RED'",
            (mercado,)
        )
        reds = c.fetchone()[0]

        c.execute(
            "SELECT COUNT(*) FROM resultados WHERE mercado=? AND resultado='REEMBOLSO'",
            (mercado,)
        )
        reembolsos = c.fetchone()[0]

        resumo[mercado] = {
            "greens": greens,
            "reds": reds,
            "reembolsos": reembolsos
        }

    conn.close()
    return resumo

def botoes_resultado(mercado):
    keyboard = [[
        InlineKeyboardButton("✅ Green", callback_data=f"GREEN|{mercado}"),
        InlineKeyboardButton("❌ Red", callback_data=f"RED|{mercado}"),
        InlineKeyboardButton("💸 Reembolso", callback_data=f"REEMBOLSO|{mercado}")
    ]]
    return InlineKeyboardMarkup(keyboard)

def jogos_ao_vivo():
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("response", [])

def estatisticas_fixture(fixture_id):
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("response", [])

def pegar_stat(stats, nome):
    for item in stats:
        if item.get("type") == nome:
            valor = item.get("value")
            if valor is None:
                return 0
            if isinstance(valor, str) and valor.endswith("%"):
                return int(valor.replace("%", ""))
            return valor
    return 0

def classificar_mercado(fixture, stats_resp):
    minuto = fixture["fixture"]["status"].get("elapsed") or 0
    if len(stats_resp) < 2:
        return None

    home = stats_resp[0]["statistics"]
    away = stats_resp[1]["statistics"]

    home_posse = pegar_stat(home, "Ball Possession")
    away_posse = pegar_stat(away, "Ball Possession")

    home_corners = pegar_stat(home, "Corner Kicks")
    away_corners = pegar_stat(away, "Corner Kicks")

    home_shots_on = pegar_stat(home, "Shots on Goal")
    away_shots_on = pegar_stat(away, "Shots on Goal")

    home_shots_total = pegar_stat(home, "Total Shots")
    away_shots_total = pegar_stat(away, "Total Shots")

    gols_home = fixture["goals"]["home"] or 0
    gols_away = fixture["goals"]["away"] or 0

    total_corners = home_corners + away_corners
    total_shots_on = home_shots_on + away_shots_on
    total_shots = home_shots_total + away_shots_total
    posse_max = max(home_posse, away_posse)

    home_forca = home_shots_total + home_shots_on + home_corners
    away_forca = away_shots_total + away_shots_on + away_corners

    # ESCANTEIO HT
    if (
        35 <= minuto <= 45 and
        total_corners >= 4 and
        posse_max >= 55 and
        total_shots >= 8
    ):
        return {
            "mercado": "ESCANTEIO_HT",
            "emoji": "🚩",
            "titulo": "ESCANTEIO HT",
            "minuto": minuto,
            "placar": f"{gols_home}-{gols_away}",
            "corners": total_corners,
            "shots_on": total_shots_on,
            "shots_total": total_shots,
            "posse_max": posse_max
        }

    # GOL HT
    if (
        30 <= minuto <= 45 and
        total_shots_on >= 3 and
        total_shots >= 10 and
        posse_max >= 55
    ):
        return {
            "mercado": "GOL_HT",
            "emoji": "⚽",
            "titulo": "GOL HT",
            "minuto": minuto,
            "placar": f"{gols_home}-{gols_away}",
            "corners": total_corners,
            "shots_on": total_shots_on,
            "shots_total": total_shots,
            "posse_max": posse_max
        }

    # GOL FT
    if (
        minuto >= 60 and
        total_shots_on >= 4 and
        total_shots >= 12 and
        posse_max >= 55
    ):
        return {
            "mercado": "GOL_FT",
            "emoji": "🥅",
            "titulo": "GOL FT",
            "minuto": minuto,
            "placar": f"{gols_home}-{gols_away}",
            "corners": total_corners,
            "shots_on": total_shots_on,
            "shots_total": total_shots,
            "posse_max": posse_max
        }

    # AMBAS MARCAM
    if (
        minuto >= 50 and
        home_shots_total >= 5 and
        away_shots_total >= 5 and
        home_shots_on >= 1 and
        away_shots_on >= 1
    ):
        return {
            "mercado": "AMBAS_MARCAM",
            "emoji": "🤝",
            "titulo": "AMBAS MARCAM",
            "minuto": minuto,
            "placar": f"{gols_home}-{gols_away}",
            "corners": total_corners,
            "shots_on": total_shots_on,
            "shots_total": total_shots,
            "posse_max": posse_max
        }

    return None

async def clicar(update, context):
    query = update.callback_query
    await query.answer()

    try:
        resultado, mercado = query.data.split("|")
    except ValueError:
        await query.edit_message_text("Erro ao registrar resultado.")
        return

    salvar_resultado(mercado, resultado)

    nomes = {
        "GREEN": "✅ Green",
        "RED": "❌ Red",
        "REEMBOLSO": "💸 Reembolso"
    }

    mercado_bonito = mercado.replace("_", " ")

    await query.edit_message_text(
        f"{nomes[resultado]} registrado\nMercado: {mercado_bonito}"
    )

async def start(update, context):
    await update.message.reply_text("Bot online ✅")

async def alerta(update, context):
    await update.message.reply_text(
        "🚨 ALERTA MANUAL\nEntrada ao vivo",
        reply_markup=botoes_resultado("ESCANTEIO_HT")
    )

async def resultado(update, context):
    greens, reds, reembolsos, lucro = contar_resultados()
    resumo = resumo_por_mercado()

    texto = (
        f"📊 RESULTADOS GERAIS\n\n"
        f"✅ Green: {greens}\n"
        f"❌ Red: {reds}\n"
        f"💸 Reembolso: {reembolsos}\n\n"
        f"💰 Lucro: {lucro}\n\n"
        f"📌 POR MERCADO\n"
        f"🚩 Escanteio HT: G {resumo['ESCANTEIO_HT']['greens']} | R {resumo['ESCANTEIO_HT']['reds']} | Re {resumo['ESCANTEIO_HT']['reembolsos']}\n"
        f"⚽ Gol HT: G {resumo['GOL_HT']['greens']} | R {resumo['GOL_HT']['reds']} | Re {resumo['GOL_HT']['reembolsos']}\n"
        f"🥅 Gol FT: G {resumo['GOL_FT']['greens']} | R {resumo['GOL_FT']['reds']} | Re {resumo['GOL_FT']['reembolsos']}\n"
        f"🤝 Ambas marcam: G {resumo['AMBAS_MARCAM']['greens']} | R {resumo['AMBAS_MARCAM']['reds']} | Re {resumo['AMBAS_MARCAM']['reembolsos']}"
    )

    await update.message.reply_text(texto)

async def aovivo(update, context):
    try:
        jogos = jogos_ao_vivo()

        if not jogos:
            await update.message.reply_text("Nenhum jogo ao vivo agora.")
            return

        enviados = 0

        for fixture in jogos[:10]:
            fixture_id = fixture["fixture"]["id"]
            stats = estatisticas_fixture(fixture_id)
            sinal = classificar_mercado(fixture, stats)

            if sinal:
                jogo = f'{fixture["teams"]["home"]["name"]} x {fixture["teams"]["away"]["name"]}'
                texto = (
                    f"{sinal['emoji']} ALERTA {sinal['titulo']}\n"
                    f"🏟 {jogo}\n"
                    f"⏱ {sinal['minuto']}'\n"
                    f"⚽ {sinal['placar']}\n"
                    f"📊 Posse máx: {sinal['posse_max']}%\n"
                    f"🎯 Chutes no gol: {sinal['shots_on']}\n"
                    f"🥅 Chutes totais: {sinal['shots_total']}\n"
                    f"🚩 Escanteios: {sinal['corners']}"
                )
                await update.message.reply_text(
                    texto,
                    reply_markup=botoes_resultado(sinal["mercado"])
                )
                enviados += 1

        if enviados == 0:
            await update.message.reply_text("Encontrei jogos ao vivo, mas nenhum bateu a regra agora.")

    except Exception as e:
        await update.message.reply_text(f"Erro ao consultar jogos: {e}")

async def verificar_automatico(context):
    global alertas_enviados

    try:
        jogos = jogos_ao_vivo()
        if not jogos:
            return

        for fixture in jogos[:10]:
            fixture_id = fixture["fixture"]["id"]

            if fixture_id in alertas_enviados:
                continue

            stats = estatisticas_fixture(fixture_id)
            sinal = classificar_mercado(fixture, stats)

            if sinal:
                jogo = f'{fixture["teams"]["home"]["name"]} x {fixture["teams"]["away"]["name"]}'
                texto = (
                    f"{sinal['emoji']} ALERTA {sinal['titulo']}\n"
                    f"🏟 {jogo}\n"
                    f"⏱ {sinal['minuto']}'\n"
                    f"⚽ {sinal['placar']}\n"
                    f"📊 Posse máx: {sinal['posse_max']}%\n"
                    f"🎯 Chutes no gol: {sinal['shots_on']}\n"
                    f"🥅 Chutes totais: {sinal['shots_total']}\n"
                    f"🚩 Escanteios: {sinal['corners']}"
                )

                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=texto,
                    reply_markup=botoes_resultado(sinal["mercado"])
                )

                alertas_enviados.add(fixture_id)

    except Exception as e:
        print("Erro na verificação automática:", e)

iniciar_banco()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("alerta", alerta))
app.add_handler(CommandHandler("resultado", resultado))
app.add_handler(CommandHandler("aovivo", aovivo))
app.add_handler(CallbackQueryHandler(clicar))

app.job_queue.run_repeating(verificar_automatico, interval=120, first=10)

print("Bot rodando...")
app.run_polling()
