import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
from db import (
    adicionar_usuario, criar_indice_user_concursos_enviados,  usuario_ja_registrado, listar_usuarios, criar_tabela_user_concursos_enviados,
    adicionar_concurso_enviado, concurso_ja_enviado, atualizar_uf_usuario, criar_tabela_user_ufs,
    criar_tabela_concurso, criar_tabela_users, adicionar_uf_usuario, obter_ufs_usuario, adicionar_concurso,
    buscar_concursos_por_ufs, buscar_concursos_filtrados
)

from telegram.ext import CallbackQueryHandler
from scrapping import concursos_ache_conc
import asyncio

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

SIGLAS_ESTADOS = {
    "rj": "rio-de-janeiro", "sp": "sao-paulo", "mg": "minas-gerais", "es": "espirito-santo",
    "ba": "bahia", "pr": "parana", "sc": "santa-catarina", "rs": "rio-grande-do-sul", "df": "distrito-federal",
    "go": "goias", "pe": "pernambuco", "ce": "ceara", "ma": "maranhao", "pi": "piaui", "pb": "paraiba",
    "rn": "rio-grande-do-norte", "ms": "mato-grosso-do-sul", "mt": "mato-grosso", "al": "alagoas", "se": "sergipe",
    "ac": "acre", "am": "amazonas", "ro": "rondonia", "rr": "roraima", "to": "tocantins", "ap": "amapa", "pa": "para"
}

SLUG_PARA_SIGLA = {v: k.upper() for k, v in SIGLAS_ESTADOS.items()}


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
    mensagem += "Use os comandos para registrar seus <b>estados de interesse</b> e receber informações sobre <b>concursos</b> nessas regiões.\n\n"
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
        "  • /uf RJ           → define Rio de Janeiro como estado de interesse.\n"
        "  • /uf RJ SP MG     → define Rio de Janeiro, São Paulo e Minas Gerais.\n"
        "  • /uf              → mostra os estados que você já está acompanhando.\n\n"

        "<b>/concursos</b>\n"
        "Receba imediatamente os concursos abertos para os seus estados de interesse que você ainda não recebeu.\n\n"

        "<b>/todos</b>\n"
        "Lista todos os concursos ativos nos seus estados de interesse, incluindo detalhes como salário, vagas, nível e prazo de inscrição.\n\n"

        "<b>/config</b>\n"
        "Ajuste filtros de concursos por salário mínimo, nível e número mínimo de vagas.\n\n"

        "<b>Observações importantes:</b>\n"
        "  1. O bot envia atualizações automáticas de concursos periodicamente para os estados que você definiu.\n"
        "  2. Use /uf para atualizar seus estados a qualquer momento.\n"
        "  3. Use /config para ajustar filtros e receber apenas concursos que atendam aos seus critérios.\n"
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

            await update.message.reply_text(
                f"🌎 Seus estados de interesse:\n• " + ", ".join(ufs_maiusculas)
            )
        return

    ufs = [uf.lower() for uf in context.args]

    ufs_validas = []
    for uf in ufs:
        if uf in SIGLAS_ESTADOS:
            ufs_validas.append(SIGLAS_ESTADOS[uf])
        else:
            await update.message.reply_text(f"❌ Sigla inválida: {uf.upper()}.")
            logger.warning(f"Usuário {user_id} tentou usar a sigla inválida: {uf}.")
            return

    atualizar_uf_usuario(user_id, ufs_validas)

    ufs_maiusculas = [uf.upper() for uf in ufs]
    await update.message.reply_text(f"🌍 Seus estados de interesse foram atualizados para:\n• " + ", ".join(ufs_maiusculas))
    logger.info(f"Usuário {user_id} atualizou seus estados de interesse para: {', '.join(ufs_maiusculas)}")

async def concursos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    ufs = obter_ufs_usuario(user_id)
    if not ufs:
        await update.message.reply_text("❌ Você não tem UFs registradas. Use /uf para registrar.")
        return

    salario, nivel, vagas = obter_filtros(user_id)
    concursos = buscar_concursos_filtrados(ufs, salario, nivel, vagas)

    if not concursos:
        await asyncio.gather(
            *(update.message.reply_text(f"❌ Nenhum concurso encontrado para {uf}.") for uf in ufs)
        )

        return

    for concurso in concursos:
        if concurso_ja_enviado(user_id, concurso["id"]):
            continue

        adicionar_concurso_enviado(user_id, concurso["id"])
        mensagem = f"🔔 <b>{concurso['titulo']}</b>\n"
        mensagem += f"💵 <b>Salário máximo:</b> {concurso['salario_max']}\n"
        mensagem += f"🏢 <b>Vagas:</b> {concurso['vagas']}\n"
        mensagem += f"📅 <b>Inscrições até:</b> {concurso['inscricoes_ate']}\n"
        mensagem += f"🎓 <b>Nível:</b> {concurso['nivel']}\n"
        mensagem += f"\n🔗 {concurso['link']}"

        await update.message.reply_text(mensagem, parse_mode='HTML')
        

    await update.message.reply_text("📚 Todos os concursos foram atualizados!")

async def atualizar_base_concursos():
    logger.info("Iniciando scraping global dos concursos...")

    for uf in SIGLAS_ESTADOS.values():
        logger.info(f"Scraping concursos da UF: {uf}")

        concursos = concursos_ache_conc(uf)

        if not concursos:
            logger.info(f"Nenhum concurso encontrado para {uf}")
            continue

        for concurso in concursos:
            adicionar_concurso(
                concurso['titulo'],
                concurso['link'],
                concurso['inscricoes_ate'],
                concurso['vagas'],
                concurso['salario_max'],
                concurso['nivel'],
                uf
            )

    logger.info("Atualização global de concursos finalizada.")


async def buscar_e_enviar_concursos(application: Application):
    usuarios = await listar_usuarios()
    logger.info(f"Iniciando envio de concursos para {len(usuarios)} usuários.")

    for user_id in usuarios:
        ufs = obter_ufs_usuario(user_id)
        if not ufs:
            continue

        salario, nivel, vagas = obter_filtros(user_id)
        concursos = buscar_concursos_filtrados(ufs, salario, nivel, vagas)
        for concurso in concursos:
            if concurso_ja_enviado(user_id, concurso['id']):
                continue

            adicionar_concurso_enviado(user_id, concurso['id'])

            mensagem = f"🔔 <b>{concurso['titulo']}</b>\n"
            mensagem += f"💵 <b>Salário máximo:</b> {concurso['salario_max']}\n"
            mensagem += f"🏢 <b>Vagas:</b> {concurso['vagas']}\n"
            mensagem += f"📅 <b>Inscrições até:</b> {concurso['inscricoes_ate']}\n"
            mensagem += f"🎓 <b>Nível:</b> {concurso['nivel']}\n"
            mensagem += f"\n🔗 {concurso['link']}"

            try:
                await application.bot.send_message(user_id, mensagem, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem para {user_id}: {e}")

    logger.info("Envio de concursos finalizado.")


async def todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    ufs = obter_ufs_usuario(user_id)
    if not ufs:
        await update.message.reply_text("❌ Você não tem UFs registradas. Use /uf para registrar.")
        return

    salario, nivel, vagas = obter_filtros(user_id)
    concursos = buscar_concursos_filtrados(ufs, salario, nivel, vagas)

    if not concursos:
        await update.message.reply_text("📭 Nenhum concurso ativo no momento para seus estados.")
        return

    await update.message.reply_text(
        f"📚 <b>Concursos ativos para:</b> {', '.join(uf.upper() for uf in ufs)}\n"
        f"Total encontrados: <b>{len(concursos)}</b>\n\n",
        parse_mode="HTML"
    )

    await asyncio.sleep(1)


    for concurso in concursos:
        mensagem = f"🔔 <b>{concurso['titulo']}</b>\n"
        mensagem += f"💵 <b>Salário máximo:</b> {concurso['salario_max']}\n"
        mensagem += f"🏢 <b>Vagas:</b> {concurso['vagas']}\n"
        mensagem += f"📅 <b>Inscrições até:</b> {concurso['inscricoes_ate']}\n"
        mensagem += f"🎓 <b>Nível:</b> {concurso['nivel']}\n"
        mensagem += f"\n🔗 {concurso['link']}"

        await update.message.reply_text(mensagem, parse_mode="HTML")
        await asyncio.sleep(0.15)  

    await update.message.reply_text("✅ Fim da lista.")

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler
from db import obter_filtros, atualizar_filtros


async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        msg = update.message
        user_id = update.effective_chat.id
    else:
        query = update.callback_query
        msg = query.message
        user_id = query.from_user.id

    salario, nivel, vagas = obter_filtros(user_id)

    texto = (
        "⚙️ <b>Configurações de filtros</b>\n\n"
        f"💵 Salário mínimo: <b>{salario or '—'}</b>\n"
        f"🎓 Nível: <b>{nivel or '—'}</b>\n"
        f"🏢 Vagas mínimas: <b>{vagas or '—'}</b>\n"
    )

    teclado = [
        [
            InlineKeyboardButton("💵 Salário", callback_data="cfg_salario"),
            InlineKeyboardButton("🎓 Nível", callback_data="cfg_nivel"),
        ],
        [
            InlineKeyboardButton("🏢 Vagas", callback_data="cfg_vagas"),
            InlineKeyboardButton("♻️ Reset", callback_data="cfg_reset"),
        ]
    ]

    await msg.reply_text(
        texto,
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="HTML"
    )



async def menu_salario(query):
    teclado = [
        [
            InlineKeyboardButton("3k+", callback_data="sal_3000"),
            InlineKeyboardButton("5k+", callback_data="sal_5000"),
        ],
        [
            InlineKeyboardButton("8k+", callback_data="sal_8000"),
            InlineKeyboardButton("10k+", callback_data="sal_10000"),
        ],
        [
            InlineKeyboardButton("12k+", callback_data="sal_12000"),
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")
        ]
    ]

    await query.edit_message_text(
        "💵 <b>Escolha o salário mínimo:</b>",
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="HTML"
    )


async def menu_nivel(query):
    teclado = [
        [
            InlineKeyboardButton("Médio", callback_data="niv_medio"),
            InlineKeyboardButton("Técnico", callback_data="niv_tecnico"),
        ],
        [
            InlineKeyboardButton("Superior", callback_data="niv_superior"),
            InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")
        ]
    ]

    await query.edit_message_text(
        "🎓 <b>Escolha o nível desejado:</b>",
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="HTML"
    )


async def menu_vagas(query):
    teclado = [
        [
            InlineKeyboardButton("5+", callback_data="vag_5"),
            InlineKeyboardButton("10+", callback_data="vag_10"),
        ],
        [
            InlineKeyboardButton("20+", callback_data="vag_20"),
            InlineKeyboardButton("50+", callback_data="vag_50"),
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")
        ]
    ]

    await query.edit_message_text(
        "🏢 <b>Escolha o mínimo de vagas:</b>",
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="HTML"
    )


async def callback_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    nivel_mapeado = {
        "medio": "Médio",  
        "tecnico": "Técnico",
        "superior": "Superior"
    }

    if data == "cfg_menu":
        salario, nivel, vagas = obter_filtros(user_id)

        texto = (
            "⚙️ <b>Configurações de filtros</b>\n\n"
            f"💵 Salário mínimo: <b>{salario or '—'}</b>\n"
            f"🎓 Nível: <b>{nivel or '—'}</b>\n"
            f"🏢 Vagas mínimas: <b>{vagas or '—'}</b>\n"
        )

        teclado = [
            [
                InlineKeyboardButton("💵 Salário", callback_data="cfg_salario"),
                InlineKeyboardButton("🎓 Nível", callback_data="cfg_nivel"),
            ],
            [
                InlineKeyboardButton("🏢 Vagas", callback_data="cfg_vagas"),
                InlineKeyboardButton("♻️ Reset", callback_data="cfg_reset"),
            ]
        ]

        await query.edit_message_text(
            texto,
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="HTML"
        )
        return

    if data == "cfg_salario":
        await menu_salario(query)
        return

    if data == "cfg_nivel":
        await menu_nivel(query)
        return

    if data == "cfg_vagas":
        await menu_vagas(query)
        return

    if data == "cfg_reset":
        atualizar_filtros(user_id, None, None, None)
        await config(update, context)
        return

    if data.startswith("niv_"):
        nivel_correct = nivel_mapeado.get(data.split("_")[1], None)
        if nivel_correct:
            atualizar_filtros(user_id, nivel=nivel_correct) 
        await config(update, context)
        return

    if data.startswith("sal_"):
        atualizar_filtros(user_id, salario=int(data.split("_")[1]))
        await config(update, context)
        return

    if data.startswith("vag_"):
        atualizar_filtros(user_id, vagas=int(data.split("_")[1]))
        await config(update, context)
        return

def configurar_agendador(application: Application):

    application.job_queue.run_repeating(
        lambda _: asyncio.create_task(atualizar_base_concursos()),
        interval=61 * 60,
        first=20,
    )

    application.job_queue.run_repeating(
        lambda _: asyncio.create_task(buscar_e_enviar_concursos(application)),
        interval=17 * 60,
        first=200,  
    )


def main():
    criar_tabelas()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    configurar_agendador(application)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("uf", uf))
    application.add_handler(CommandHandler("concursos", concursos))
    application.add_handler(CommandHandler("todos", todos))
    application.add_handler(CommandHandler("config", config))
    application.add_handler(CallbackQueryHandler(callback_config, pattern="^(cfg_|sal_|niv_|vag_)"))


    application.run_polling()

if __name__ == '__main__':
    main()
