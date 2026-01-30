from scrapping import mensagens_novos, mensagens_todos
from telegram import Bot
from ids import salvar_usuario
from db import criar_tabela
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
import os
import json
import asyncio

import json
import os

if not os.path.exists("usuarios.json"):
    with open("usuarios.json", "w") as f:
        json.dump([], f)  


load_dotenv()
token = os.getenv("TELEGRAM_TOKEN")
criar_tabela()


async def start(update, context):
    chat_id = update.effective_chat.id
    salvar_usuario(chat_id)
    await update.message.reply_text(
        "Oi! Eu posso te enviar concursos novos automaticamente!"
    )

async def concursos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not mensagens_todos():
        await update.message.reply_text("Não há concursos disponíveis no momento!")
    for m in mensagens_todos():
        await update.message.reply_text(m)

async def concursos_novos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not mensagens_novos:
        await update.message.reply_text("Nenhum concurso novo encontrado!")
    for m in mensagens_novos():
        await update.message.reply_text(m)

async def enviar_novos(context: ContextTypes.DEFAULT_TYPE):
    
    novas_msgs = mensagens_novos()
    if not novas_msgs:
        return

    with open("usuarios.json", "r") as f:
        usuarios = json.load(f)

    for m in novas_msgs:
        for chat_id in usuarios:
            await context.bot.send_message(chat_id=chat_id, text=m)


app = ApplicationBuilder().token(token).build()
app.add_handler(CommandHandler("concursos", concursos))
app.add_handler(CommandHandler("novos", concursos_novos))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("enviar_novos", enviar_novos))


job_queue = app.job_queue
app.job_queue.run_repeating(enviar_novos, interval=3600, first=10) 


print("Bot rodando...")



app.run_polling()
