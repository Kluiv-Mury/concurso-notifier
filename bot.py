import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
from db import (
    adicionar_usuario, criar_indice_user_concursos_enviados,  usuario_ja_registrado, listar_usuarios, criar_tabela_user_concursos_enviados,
    adicionar_concurso_enviado, concurso_ja_enviado, atualizar_uf_usuario, criar_tabela_user_ufs,
    criar_tabela_concurso, criar_tabela_users, adicionar_uf_usuario, obter_ufs_usuario, adicionar_concurso,
    buscar_concursos_por_ufs
)
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

    mensagem = "*Funcionamento do bot:*\n\n"
    mensagem += "🔔 A cada meia hora, envio automaticamente atualizações sobre novos concursos nos estados que você escolheu.\n\n"
    
    mensagem += "*Comandos disponíveis:*\n\n"
    
    mensagem += "🔹 /uf\n"
    mensagem += "Registre os estados de seu interesse. Exemplo: /uf RJ SP MG para acompanhar concursos de Rio de Janeiro, São Paulo e Minas Gerais.\n"
    mensagem += "Usando o comando /uf sozinho, eu mostro os estados que você já está acompanhando.\n\n"
    
    mensagem += "🔹 /concursos\n"
    mensagem += "Receba instantaneamente os detalhes de concursos abertos para os seus estados de interesse.\n\n"

    mensagem += "📝 Mais funcionalidades em breve!\n"

    await update.message.reply_text(mensagem, parse_mode='HTML')
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

    for uf in ufs:
        concursos = concursos_ache_conc(uf)
        
        if not concursos:
            await update.message.reply_text(f"❌ Nenhum concurso encontrado para {uf}.")
            continue

        for concurso in concursos:
            concurso_id = adicionar_concurso(
                concurso['titulo'],
                concurso['link'],
                concurso['inscricoes_ate'],
                concurso['vagas'],
                concurso['salario_max'],
                concurso['nivel'],
                uf
            )

            if not concurso_id:
                continue

            if concurso_ja_enviado(user_id, concurso_id):
                logger.info(f"Concurso {concurso['titulo']} já foi enviado para o usuário {user_id}.")
                continue
                
            

            adicionar_concurso_enviado(user_id, concurso_id)

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

        concursos = buscar_concursos_por_ufs(ufs)

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

    application.run_polling()

if __name__ == '__main__':
    main()
