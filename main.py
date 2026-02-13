from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import TELEGRAM_TOKEN, logger
from bot.handlers import (
    start, help, uf, concursos, todos, config, callback_config, criar_tabelas
)
from bot.jobs import (
    atualizar_base_concursos, buscar_e_enviar_concursos
)

def configurar_agendador(application: Application):
    application.job_queue.run_repeating(atualizar_base_concursos, interval=61 * 60, first=20)
    application.job_queue.run_repeating(buscar_e_enviar_concursos, interval=17 * 60, first=200)

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

    print("🤖 Bot iniciado!")
    application.run_polling()

if __name__ == '__main__':
    main()