import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

from db import notificacoes_ativas as get_notificacoes_ativas  

from config import TELEGRAM_TOKEN, logger, SIGLAS_ESTADOS, SLUG_PARA_SIGLA

from db import (
    adicionar_usuario, criar_indice_user_concursos_enviados, usuario_ja_registrado, 
    criar_tabela_user_concursos_enviados, adicionar_concurso_enviado, concurso_ja_enviado, 
    atualizar_uf_usuario, criar_tabela_user_ufs, criar_tabela_concurso, criar_tabela_users, 
    obter_ufs_usuario, buscar_concursos_filtrados, obter_filtros
)

from scrapping import concursos_ache_conc


def criar_tabelas():
    criar_tabela_concurso()
    criar_tabela_users()
    criar_tabela_user_ufs()
    criar_tabela_user_concursos_enviados()
    criar_indice_user_concursos_enviados()



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    nome = update.effective_chat.first_name

    if not usuario_ja_registrado(user_id):
        adicionar_usuario(user_id, nome)

    mensagem = f"Olá, {nome}! Sou seu assistente de concursos públicos.\n\n"
    mensagem += "Estou aqui para te ajudar a encontrar as melhores oportunidades de concursos no Brasil.\n\n"
    mensagem += "Use os comandos para registrar seus <b>estados de interesse</b> e receber informações.\n\n"
    mensagem += "Para mais detalhes sobre como usar o bot, digite <b>/help</b>.\n"

    await update.message.reply_text(mensagem, parse_mode='HTML')
    logger.info(f"Novo usuário {user_id} iniciou o bot.")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    mensagem = (
        "<b>Guia de Comandos do Bot de Concursos</b>\n\n"

        "<b>/help</b>\n"
        "Mostra esta mensagem com os comandos disponíveis.\n\n"

        "<b>/uf</b>\n"
        "Defina ou veja os estados de interesse para receber concursos:\n"
        "  • /uf RJ            → define Rio de Janeiro como estado de interesse.\n"
        "  • /uf RJ SP MG      → define Rio de Janeiro, São Paulo e Minas Gerais.\n"
        "  • /uf               → mostra os estados que você já está acompanhando.\n\n"

        "<b>/concursos</b>\n"
        "Receba imediatamente os concursos abertos para os seus estados de interesse que você ainda não recebeu.\n\n"

        "<b>/todos</b>\n"
        "Lista todos os concursos ativos nos seus estados de interesse, incluindo detalhes como salário, vagas, nível e prazo de inscrição.\n\n"

        "<b>/config</b>\n"
        "Ajuste filtros de concursos por salário mínimo, nível e número mínimo de vagas.\n\n"

        "<b>Além disso, a cada 1 hora, atualizarei a base de concursos e enviarei os que você ainda não recebeu, respeitando suas regiões de interesse.</b>"
    )

    await update.message.reply_text(mensagem, parse_mode="HTML")
    logger.info(f"Usuário {user_id} solicitou ajuda. Enviando informações.")

async def uf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    if not context.args:
        ufs = obter_ufs_usuario(user_id)
        if not ufs:
            await update.message.reply_text("❌ Você ainda não tem estados registrados. Use /uf para adicionar.")
        else:
            ufs_maiusculas = [SLUG_PARA_SIGLA.get(uf, uf.upper()) for uf in ufs]
            await update.message.reply_text(f"🌎 Seus estados de interesse:\n• " + ", ".join(ufs_maiusculas))
        return

    ufs = [uf.lower() for uf in context.args]
    ufs_validas = []
    

    for uf in ufs:
        if uf in SIGLAS_ESTADOS:
            ufs_validas.append(SIGLAS_ESTADOS[uf])
        else:
            await update.message.reply_text(f"❌ Sigla inválida: {uf.upper()}.")
            logger.warning(f"Usuário {user_id} tentou usar sigla inválida: {uf}.")
            return

    atualizar_uf_usuario(user_id, ufs_validas)
    ufs_maiusculas = [uf.upper() for uf in ufs]
    await update.message.reply_text(f"🌍 Seus estados de interesse foram atualizados para:\n• " + ", ".join(ufs_maiusculas))
    logger.info(f"Usuário {user_id} atualizou estados: {', '.join(ufs_maiusculas)}")

async def concursos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    ufs = obter_ufs_usuario(user_id)
    if not ufs:
        await update.message.reply_text("❌ Você não tem UFs registradas. Use /uf para registrar.")
        return

    salario, nivel, vagas = obter_filtros(user_id)
    concursos_lista = buscar_concursos_filtrados(ufs, salario, nivel, vagas)

    if not concursos_lista:
        await update.message.reply_text("❌ Nenhum concurso novo encontrado para seus estados/filtros.")
        return

    count = 0
    for concurso in concursos_lista:
        if concurso_ja_enviado(user_id, concurso["id"]):
            continue

        adicionar_concurso_enviado(user_id, concurso["id"])
        mensagem = (
            f"🔔 <b>{concurso['titulo']}</b>\n"
            f"💵 <b>Salário máximo:</b> {concurso['salario_max']}\n"
            f"🏢 <b>Vagas:</b> {concurso['vagas']}\n"
            f"📅 <b>Até:</b> {concurso['inscricoes_ate']}\n"
            f"🎓 <b>Nível:</b> {concurso['nivel']}\n\n"
            f"🔗 {concurso['link']}"
        )
        await update.message.reply_text(mensagem, parse_mode='HTML')
        count += 1
        
    if count > 0:
        await update.message.reply_text("📚 Todos os concursos foram atualizados!")
    else:
        await update.message.reply_text("✅ Você já viu todos os concursos disponíveis.")

async def todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    ufs = obter_ufs_usuario(user_id)
    if not ufs:
        await update.message.reply_text("❌ Você não tem UFs registradas.")
        return

    salario, nivel, vagas = obter_filtros(user_id)
    concursos_lista = buscar_concursos_filtrados(ufs, salario, nivel, vagas)

    if not concursos_lista:
        await update.message.reply_text("📭 Nenhum concurso ativo no momento.")
        return

    await update.message.reply_text(f"📚 <b>Total encontrados:</b> {len(concursos_lista)}\n\n", parse_mode="HTML")
    await asyncio.sleep(1)

    for concurso in concursos_lista:
        mensagem = (
            f"🔔 <b>{concurso['titulo']}</b>\n"
            f"💵 <b>Max:</b> {concurso['salario_max']}\n"
            f"🏢 <b>Vagas:</b> {concurso['vagas']}\n"  
            f"📅 <b>Até:</b> {concurso['inscricoes_ate']}\n"
            f"🔗 {concurso['link']}"
        )
        await update.message.reply_text(mensagem, parse_mode="HTML")
        await asyncio.sleep(0.2)
    
    await update.message.reply_text("✅ Fim da lista.")



async def menu_notificacoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    status = get_notificacoes_ativas(user_id)

    texto = "⚙️ <b>Configuração de Notificações</b>\n\n"
    texto += "Escolha se deseja receber notificações de novos concursos.\n\n"

    if status == 1:
        texto += "<b>Notificações Ativas</b>"
        teclado = [
            [InlineKeyboardButton("❌ Desativar Notificações", callback_data="desativar_notificacao")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")]
        ]
    else:
        texto += "<b>Notificações Desativadas</b>"
        teclado = [
            [InlineKeyboardButton("✅ Ativar Notificações", callback_data="ativar_notificacao")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")]
        ]

    await query.edit_message_text(
        texto,
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="HTML"
    )