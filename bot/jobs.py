"""Tarefas periódicas: atualizar a base e avisar os usuários."""

from __future__ import annotations

import asyncio

from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from bot.formatacao import agrupar_em_mensagens
from config import SIGLAS_ESTADOS, logger
from db import (
    atualizar_notificacoes_usuario,
    buscar_concursos,
    listar_usuarios,
    marcar_enviados,
    obter_filtros,
    obter_ufs_usuario,
    salvar_concursos,
)
from scrapping import coletar_concursos

# Teto de alertas por usuário em cada ciclo. Sem isso, um usuário novo com
# filtros amplos receberia a base inteira de uma vez.
MAX_ALERTAS_POR_CICLO = 10

# Pausa entre mensagens: a API aceita ~1 msg/s por chat.
PAUSA_ENTRE_MENSAGENS = 1.0


async def atualizar_base_concursos(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Varre os 27 estados e grava o resultado.

    `coletar_concursos` roda numa thread: a varredura leva minutos e, dentro
    do event loop, o bot pararia de responder a comandos nesse intervalo.
    """
    logger.info("Iniciando scraping global...")
    total_novos = 0

    for estado in SIGLAS_ESTADOS.values():
        try:
            concursos = await coletar_concursos(estado)
        except Exception:
            logger.exception("Falha ao coletar concursos de %s.", estado)
            continue

        if not concursos:
            continue

        try:
            novos = await asyncio.to_thread(salvar_concursos, estado, concursos)
        except Exception:
            logger.exception("Falha ao gravar concursos de %s.", estado)
            continue

        total_novos += novos
        logger.info("%s: %d coletados, %d novos.", estado, len(concursos), novos)

    logger.info("Fim do scraping global. %d concursos novos.", total_novos)


async def _enviar(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, texto: str
) -> bool:
    """Envia tratando flood control. False quando não deu para entregar."""
    for _ in range(2):
        try:
            await context.bot.send_message(user_id, texto, parse_mode="HTML")
            return True
        except RetryAfter as erro:
            logger.warning("Flood control para %s: aguardando %ss.", user_id, erro.retry_after)
            await asyncio.sleep(erro.retry_after + 1)
        except Forbidden:
            # Usuário bloqueou o bot; desliga para não insistir todo ciclo.
            logger.info("Usuário %s bloqueou o bot. Notificações desativadas.", user_id)
            await asyncio.to_thread(atualizar_notificacoes_usuario, user_id, False)
            return False
        except TelegramError:
            logger.exception("Erro ao enviar mensagem para %s.", user_id)
            return False
    return False


async def _notificar_usuario(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> int:
    ufs = await asyncio.to_thread(obter_ufs_usuario, user_id)
    if not ufs:
        return 0

    salario, nivel, vagas = await asyncio.to_thread(obter_filtros, user_id)
    concursos = await asyncio.to_thread(
        buscar_concursos,
        ufs,
        salario,
        nivel,
        vagas,
        user_id,              # exclui o que já foi enviado, na própria query
        MAX_ALERTAS_POR_CICLO,
    )
    if not concursos:
        return 0

    enviados: list[int] = []

    for texto, ids in agrupar_em_mensagens(concursos, compacto=True):
        if not await _enviar(context, user_id, texto):
            # Só é marcado como enviado o que realmente saiu; o resto volta no
            # próximo ciclo em vez de se perder para sempre.
            break
        enviados.extend(ids)
        await asyncio.sleep(PAUSA_ENTRE_MENSAGENS)

    if enviados:
        await asyncio.to_thread(marcar_enviados, user_id, enviados)

    return len(enviados)


async def buscar_e_enviar_concursos(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia a cada usuário ativo os concursos que ele ainda não recebeu."""
    usuarios = await asyncio.to_thread(listar_usuarios)
    logger.info("Verificando novidades para %d usuários.", len(usuarios))

    total = 0
    for user_id in usuarios:
        try:
            total += await _notificar_usuario(context, user_id)
        except Exception:
            logger.exception("Falha ao notificar %s.", user_id)

    logger.info("Ciclo de alertas concluído: %d concursos enviados.", total)
