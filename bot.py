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
        resultado TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def salvar_resultado(resultado):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT INTO resultados (resultado) VALUES (?)", (resultado,))
    conn.commit()
    conn.close()

def contar_resultados():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM resultados WHERE resultado='WIN'")
    wins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM resultados WHERE resultado='LOSS'")
    losses = c.fetchone()[0]

    lucro = (wins * 10) - (losses * 10)

    conn.close()
    return wins, losses, lucro

def botoes():
    keyboard = [[
        InlineKeyboardButton("✅ WIN", callback_data="win"),
        InlineKeyboardButton("❌ LOSS", callback_data="loss")
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

def analisar_jogo(fixture, stats_resp):
    minuto = fixture["fixture"]["status"].get("elapsed") or 0
    if minuto < 20:
        return None

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

    if (
        minuto >= 20 and
        (
            total_shots_on >= 2 or
            total_shots >= 8 or
            total_corners >= 4 or
            posse_max >= 60
        )
    ):
        return {
            "fixture_id": fixture["fixture"]["id"],
            "jogo": f'{fixture["teams"]["home"]["name"]} x {fixture["teams"]["away"]["name"]}',
            "placar": f"{gols_home}-{gols_away}",
            "minuto": minuto,
            "corners": total_corners,
            "shots_on": total_shots_on,
            "shots_total": total_shots,
            "posse_max": posse_max
        }

    return None

async def clicar(update, context):
    query = update.callback_query
    await query.answer()

    if "win" in query.data:
        salvar_resultado("WIN")
        await query.edit_message_text("✅ WIN registrado")
    else:
        salvar_resultado("LOSS")
        await query.edit_message_text("❌ LOSS registrado")

async def start(update, context):
    await update.message.reply_text("Bot online ✅")

async def alerta(update, context):
    await update.message.reply_text(
        "🚨 ALERTA MANUAL\nEntrada ao vivo",
        reply_markup=botoes()
    )

async def resultado(update, context):
    wins, losses, lucro = contar_resultados()
    await update.message.reply_text(
        f"📊 RESULTADOS\n\n✅ WIN: {wins}\n❌ LOSS: {losses}\n\n💰 Lucro: {lucro}"
    )

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
            sinal = analisar_jogo(fixture, stats)

            if sinal:
                texto = (
                    f"🚨 ALERTA AO VIVO\n"
                    f"🏟 {sinal['jogo']}\n"
                    f"⏱ {sinal['minuto']}'\n"
                    f"⚽ {sinal['placar']}\n"
                    f"📊 Posse máx: {sinal['posse_max']}%\n"
                    f"🎯 Chutes no gol: {sinal['shots_on']}\n"
                    f"🥅 Chutes totais: {sinal['shots_total']}\n"
                    f"🚩 Escanteios: {sinal['corners']}"
                )
                await update.message.reply_text(texto, reply_markup=botoes())
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
            sinal = analisar_jogo(fixture, stats)

            if sinal:
                texto = (
                    f"🚨 ALERTA AUTOMÁTICO\n"
                    f"🏟 {sinal['jogo']}\n"
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
                    reply_markup=botoes()
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
