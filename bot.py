import logging
import sqlite3
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")
CHAT_ID = int(os.getenv("CHAT_ID", "5866187111"))

API_URL = "https://v3.football.api-sports.io/fixtures?live=all"

INTERVALO_BUSCA = 60  # segundos

# ================= LOG =================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ================= BANCO DE DADOS =================

conn = sqlite3.connect("resultados.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resultado TEXT,
    data TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sinais_enviados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER UNIQUE,
    tipo TEXT,
    data TEXT
)
""")

conn.commit()

# ================= COMANDOS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot iniciado! Monitorando sinais de Gol HT.")

async def resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT resultado, COUNT(*) FROM resultados GROUP BY resultado")
    dados = cursor.fetchall()

    win = 0
    loss = 0
    reembolso = 0

    for resultado, total in dados:
        if resultado == "WIN":
            win = total
        elif resultado == "LOSS":
            loss = total
        elif resultado == "REEMBOLSO":
            reembolso = total

    lucro = (win * 10) - (loss * 10)

    texto = f"""
📊 RESULTADOS

✅ WIN: {win}
❌ LOSS: {loss}
🔁 REEMBOLSO: {reembolso}

💰 Lucro estimado: {lucro}
"""

    await update.message.reply_text(texto)

# ================= BOTÕES =================

async def botoes_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    resultado = query.data
    data = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    cursor.execute(
        "INSERT INTO resultados (resultado, data) VALUES (?, ?)",
        (resultado, data)
    )
    conn.commit()

    await query.edit_message_text(f"Resultado marcado: {resultado}")

# ================= DETECTOR INTELIGENTE GOL HT =================

def detector_gol_ht(dados):
    score = 0
    motivos = []

    minuto = dados.get("minuto", 0)
    pressao = dados.get("pressao", 0)
    ataques_perigosos = dados.get("ataques_perigosos", 0)
    finalizacoes = dados.get("finalizacoes", 0)
    chutes_gol = dados.get("chutes_gol", 0)
    escanteios = dados.get("escanteios", 0)

    # Evita ruído muito inicial
    if minuto < 3:
        return None

    # Só primeiro tempo
    if minuto > 45:
        return None

    # Pressão
    if pressao >= 60:
        score += 20
        motivos.append("pressão alta")

    if pressao >= 70:
        score += 10
        motivos.append("pressão muito forte")

    # Ataques perigosos
    if ataques_perigosos >= 20:
        score += 20
        motivos.append("muitos ataques perigosos")

    if ataques_perigosos >= 35:
        score += 15
        motivos.append("ataques perigosos muito altos")

    # Finalizações
    if finalizacoes >= 4:
        score += 15
        motivos.append("bom volume de finalizações")

    if finalizacoes >= 7:
        score += 15
        motivos.append("volume ofensivo muito forte")

    # Chutes no gol
    if chutes_gol >= 2:
        score += 15
        motivos.append("chutes no gol")

    if chutes_gol >= 4:
        score += 15
        motivos.append("muitos chutes no gol")

    # Escanteios
    if escanteios >= 3:
        score += 10
        motivos.append("sequência de escanteios")

    if escanteios >= 5:
        score += 10
        motivos.append("muitos escanteios")

    # Detector de explosão cedo
    if minuto <= 15 and (finalizacoes >= 4 or chutes_gol >= 2 or escanteios >= 3):
        score += 20
        motivos.append("padrão forte apareceu cedo")

    if score >= 70:
        return {
            "tipo": "🔥 GOL HT - SINAL FORTE",
            "score": score,
            "motivos": motivos
        }

    if score >= 50:
        return {
            "tipo": "⚠️ GOL HT - SINAL MÉDIO",
            "score": score,
            "motivos": motivos
        }

    return None

# ================= API FOOTBALL =================

def buscar_jogos_ao_vivo():
    headers = {
        "x-apisports-key": API_FOOTBALL_KEY
    }

    try:
        resposta = requests.get(API_URL, headers=headers, timeout=20)

        if resposta.status_code != 200:
            logging.error(f"Erro API: {resposta.status_code} - {resposta.text}")
            return []

        dados = resposta.json()
        return dados.get("response", [])

    except Exception as erro:
        logging.error(f"Erro ao buscar jogos: {erro}")
        return []

def ja_enviou_sinal(fixture_id):
    cursor.execute(
        "SELECT fixture_id FROM sinais_enviados WHERE fixture_id = ?",
        (fixture_id,)
    )
    return cursor.fetchone() is not None

def salvar_sinal(fixture_id, tipo):
    data = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    try:
        cursor.execute(
            "INSERT INTO sinais_enviados (fixture_id, tipo, data) VALUES (?, ?, ?)",
            (fixture_id, tipo, data)
        )
        conn.commit()
    except:
        pass

# ================= EXTRAÇÃO DOS DADOS =================

def extrair_dados_jogo(jogo):
    fixture_id = jogo["fixture"]["id"]
    minuto = jogo["fixture"]["status"].get("elapsed", 0)

    time_casa = jogo["teams"]["home"]["name"]
    time_fora = jogo["teams"]["away"]["name"]

    gols_casa = jogo["goals"]["home"] or 0
    gols_fora = jogo["goals"]["away"] or 0

    estatisticas = jogo.get("statistics", [])

    dados_casa = {}
    dados_fora = {}

    if len(estatisticas) >= 2:
        for item in estatisticas[0].get("statistics", []):
            dados_casa[item["type"]] = item["value"]

        for item in estatisticas[1].get("statistics", []):
            dados_fora[item["type"]] = item["value"]

    def numero(valor):
        if valor is None:
            return 0
        if isinstance(valor, str):
            valor = valor.replace("%", "")
        try:
            return int(valor)
        except:
            return 0

    ataques_perigosos_casa = numero(dados_casa.get("Dangerous Attacks"))
    ataques_perigosos_fora = numero(dados_fora.get("Dangerous Attacks"))

    finalizacoes_casa = numero(dados_casa.get("Total Shots"))
    finalizacoes_fora = numero(dados_fora.get("Total Shots"))

    chutes_gol_casa = numero(dados_casa.get("Shots on Goal"))
    chutes_gol_fora = numero(dados_fora.get("Shots on Goal"))

    escanteios_casa = numero(dados_casa.get("Corner Kicks"))
    escanteios_fora = numero(dados_fora.get("Corner Kicks"))

    posse_casa = numero(dados_casa.get("Ball Possession"))
    posse_fora = numero(dados_fora.get("Ball Possession"))

    if posse_casa >= posse_fora:
        time_dominante = time_casa
        pressao = posse_casa
        ataques_perigosos = ataques_perigosos_casa
        finalizacoes = finalizacoes_casa
        chutes_gol = chutes_gol_casa
        escanteios = escanteios_casa
    else:
        time_dominante = time_fora
        pressao = posse_fora
        ataques_perigosos = ataques_perigosos_fora
        finalizacoes = finalizacoes_fora
        chutes_gol = chutes_gol_fora
        escanteios = escanteios_fora

    return {
        "fixture_id": fixture_id,
        "minuto": minuto,
        "time_casa": time_casa,
        "time_fora": time_fora,
        "gols_casa": gols_casa,
        "gols_fora": gols_fora,
        "time_dominante": time_dominante,
        "pressao": pressao,
        "ataques_perigosos": ataques_perigosos,
        "finalizacoes": finalizacoes,
        "chutes_gol": chutes_gol,
        "escanteios": escanteios
    }

# ================= MONITORAMENTO =================

async def monitorar_jogos(context: ContextTypes.DEFAULT_TYPE):
    jogos = buscar_jogos_ao_vivo()

    if not jogos:
        logging.info("Nenhum jogo ao vivo encontrado.")
        return

    for jogo in jogos:
        try:
            dados = extrair_dados_jogo(jogo)

            fixture_id = dados["fixture_id"]
            minuto = dados["minuto"]

            if ja_enviou_sinal(fixture_id):
                continue

            sinal = detector_gol_ht(dados)

            if sinal:
                salvar_sinal(fixture_id, sinal["tipo"])

                teclado = [
                    [
                        InlineKeyboardButton("✅ WIN", callback_data="WIN"),
                        InlineKeyboardButton("❌ LOSS", callback_data="LOSS"),
                        InlineKeyboardButton("🔁 REEMBOLSO", callback_data="REEMBOLSO")
                    ]
                ]

                reply_markup = InlineKeyboardMarkup(teclado)

                mensagem = f"""
🚨 ALERTA DE GOL HT

{sinal['tipo']}
📊 Score: {sinal['score']}/100

🏆 Jogo:
{dados['time_casa']} x {dados['time_fora']}

⏱ Minuto: {minuto}'
⚽ Placar: {dados['gols_casa']} x {dados['gols_fora']}

🔥 Time com melhor momento:
{dados['time_dominante']}

📈 Dados do padrão:
Pressão/posse: {dados['pressao']}%
Ataques perigosos: {dados['ataques_perigosos']}
Finalizações: {dados['finalizacoes']}
Chutes no gol: {dados['chutes_gol']}
Escanteios: {dados['escanteios']}

🧠 Motivos:
{', '.join(sinal['motivos'])}
"""

                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=mensagem,
                    reply_markup=reply_markup
                )

        except Exception as erro:
            logging.error(f"Erro ao analisar jogo: {erro}")

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resultado", resultado))
    app.add_handler(CallbackQueryHandler(botoes_resultado))

    app.job_queue.run_repeating(
        monitorar_jogos,
        interval=INTERVALO_BUSCA,
        first=10
    )

    print("✅ Bot rodando com Detector Inteligente de Gol HT...")
    app.run_polling()

if __name__ == "__main__":
    main()
