from scrapping import mensagens_novas_para_usuario
from telegram import Bot
from db import criar_tabela_user_ufs, criar_tabela_users, criar_tabela_user_concursos, obter_ufs_usuario, atualizar_uf_usuario, adicionar_uf_usuario, adicionar_usuario, criar_tabela_concurso, listar_usuarios, adicionar_concurso, obter_id_concurso, usuario_ja_recebeu, marcar_concurso_enviado
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
import os
import json
import os


load_dotenv()
token = os.getenv("TELEGRAM_TOKEN")
criar_tabela_concurso()
criar_tabela_users()
criar_tabela_user_concursos()
criar_tabela_user_ufs()



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nome = update.effective_user.first_name or ""

    # 1. adiciona usuário (ignora se já existir)
    novo = adicionar_usuario(chat_id, nome)

    # 2. define UF padrão se for novo usuário
    if novo:
        adicionar_uf_usuario(chat_id, "RJ")

    await update.message.reply_text(
        "🤖 *Bot de Concursos ativo!*\n\n"
        "📌 Vou te avisar automaticamente quando surgirem *novos concursos* "
        "nos estados que você definir.\n\n"
        "🕐 A cada 1 hora faço uma verificação automática.\n"
        "⚡ Você também pode forçar a busca usando `/concursos`.\n\n"
        "🌎 Estado padrão: *RJ*\n"
        "✏️ Use `/uf` para adicionar ou remover estados de interesse.\n\n"
        "ℹ️ Digite `/help` para ver todos os comandos.",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """🤖 *Bot de Concursos Públicos*

Eu acompanho concursos públicos e te aviso automaticamente quando surgirem *novos concursos* de acordo com os *estados (UFs)* que você definir.

🕒 *Como funciona*
• A cada 1 hora faço uma verificação automática  
• Você recebe apenas concursos que *ainda não recebeu*  
• Pode forçar a busca manualmente

📍 *Comandos disponíveis*
/concursos – Mostra concursos *novos* para você  
/uf – Gerencia seus estados de interesse  
/help – Mostra esta mensagem de ajuda  

🌎 *Como funciona o /uf*
Você pode definir *um ou vários estados* de interesse.

Exemplos:
• `/uf RJ` → define apenas RJ  
• `/uf RJ SP MG` → define vários estados  
• `/uf` → mostra seus estados atuais  

📌 Por padrão, novos usuários começam com *RJ*.

Mais funcionalidades estão a caminho 🚀
""",
        parse_mode="Markdown"
    )



async def concursos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    mensagens = mensagens_novas_para_usuario(user_id)

    if not mensagens:
        await update.message.reply_text("Você já está em dia, nenhum concurso novo 🙂")
        return

    for m in mensagens:
        await update.message.reply_text(m)


async def uf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    # /uf sem argumentos → mostra UFs atuais
    if not context.args:
        ufs = obter_ufs_usuario(user_id)
        await update.message.reply_text(
            f"🌎 Seus estados de interesse:\n• " + ", ".join(ufs)
        )
        return

    # /uf RJ SP MG
    ufs = [uf.upper() for uf in context.args if len(uf) == 2]

    if not ufs:
        await update.message.reply_text(
            "❌ Uso inválido.\nExemplo: `/uf RJ SP MG`",
            parse_mode="Markdown"
        )
        return

    atualizar_uf_usuario(user_id, ufs)

    await update.message.reply_text(
        "✅ Estados atualizados com sucesso!\n\n"
        f"🌎 Agora você receberá concursos de:\n• {', '.join(ufs)}"
    )



async def enviar_novos(context: ContextTypes.DEFAULT_TYPE):
    usuarios = listar_usuarios()

    for user_id in usuarios:
        mensagens = mensagens_novas_para_usuario(user_id)

        for msg in mensagens:
            await context.bot.send_message(
                chat_id=user_id,
                text=msg
            )



app = ApplicationBuilder().token(token).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("concursos", concursos))
app.add_handler(CommandHandler("uf", uf))
app.add_handler(CommandHandler("enviar_novos", enviar_novos))


job_queue = app.job_queue
app.job_queue.run_repeating(enviar_novos, interval=3600, first=10) 


print("Bot rodando...")



app.run_polling()
