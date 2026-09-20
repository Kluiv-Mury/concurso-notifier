"""Ponto de entrada do bot de concursos."""

from __future__ import annotations

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from bot.handlers import (
    ajuda,
    callback_deletar,
    concursos,
    deletar,
    start,
    todos,
    uf,
)
from bot.jobs import (
    atualizar_base_concursos,
    backup_do_banco,
    buscar_e_enviar_concursos,
    lembrar_prazos,
)
from bot.menu_config import callback_config, config
from config import (
    INTERVALO_ALERTAS,
    INTERVALO_BACKUP,
    INTERVALO_LEMBRETES,
    INTERVALO_SCRAPING,
    TELEGRAM_TOKEN,
    logger,
)
from db import criar_tabelas

COMANDOS = [
    BotCommand("start", "Começar a usar o bot"),
    BotCommand("uf", "Definir ou ver seus estados de interesse"),
    BotCommand("concursos", "Ver os concursos que você ainda não recebeu"),
    BotCommand("todos", "Listar todos os concursos abertos"),
    BotCommand("config", "Ajustar filtros e notificações"),
    BotCommand("deletar", "Apagar todos os meus dados"),
    BotCommand("help", "Ver o guia de comandos"),
]


async def _pos_inicializacao(application: Application) -> None:
    """Publica o menu de comandos no cliente do Telegram."""
    await application.bot.set_my_commands(COMANDOS)


async def tratar_erro(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loga a exceção e avisa o usuário, em vez de falhar em silêncio."""
    logger.exception("Erro ao processar update: %s", context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Algo deu errado por aqui. Tente de novo em instantes."
            )
        except Exception:
            logger.debug("Não foi possível avisar o usuário sobre o erro.")


def configurar_agendador(application: Application) -> None:
    fila = application.job_queue
    fila.run_repeating(atualizar_base_concursos, interval=INTERVALO_SCRAPING, first=20)
    fila.run_repeating(buscar_e_enviar_concursos, interval=INTERVALO_ALERTAS, first=200)
    # `first=5`: uma cópia logo no boot, antes de o scraping tocar no banco.
    fila.run_repeating(backup_do_banco, interval=INTERVALO_BACKUP, first=5)
    # Depois do primeiro ciclo de alertas, para não competir com ele.
    fila.run_repeating(lembrar_prazos, interval=INTERVALO_LEMBRETES, first=600)


def main() -> None:
    criar_tabelas()

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_pos_inicializacao)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", ajuda))
    application.add_handler(CommandHandler("uf", uf))
    application.add_handler(CommandHandler("concursos", concursos))
    application.add_handler(CommandHandler("todos", todos))
    application.add_handler(CommandHandler("config", config))
    application.add_handler(CommandHandler("deletar", deletar))

    # O `pattern` precisa vir antes: dentro de um mesmo grupo só o primeiro
    # handler compatível roda, e `callback_config` aceita qualquer callback.
    application.add_handler(CallbackQueryHandler(callback_deletar, pattern=r"^del_"))
    application.add_handler(CallbackQueryHandler(callback_config))
    application.add_error_handler(tratar_erro)

    configurar_agendador(application)

    logger.info("🤖 Bot iniciado.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
