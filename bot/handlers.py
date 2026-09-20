"""Handlers dos comandos do bot."""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatacao import agrupar_em_mensagens, formatar_ufs
from config import SIGLAS_ESTADOS, logger
from db import (
    adicionar_usuario,
    atualizar_uf_usuario,
    buscar_concursos,
    marcar_enviados,
    obter_filtros,
    obter_ufs_usuario,
    usuario_ja_registrado,
)

# Pausa entre mensagens de uma listagem longa (~1 msg/s por chat na API).
PAUSA_ENTRE_MENSAGENS = 0.6


async def _garantir_usuario(update: Update) -> int:
    """Registra o usuário se ainda não existir e devolve o chat_id.

    Chamado em todo handler porque `user_ufs` referencia `users`: alguém que
    mande /uf antes de /start esbarraria na foreign key.
    """
    chat = update.effective_chat
    if not await asyncio.to_thread(usuario_ja_registrado, chat.id):
        await asyncio.to_thread(adicionar_usuario, chat.id, chat.first_name)
    return chat.id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await _garantir_usuario(update)
    nome = update.effective_chat.first_name or "!"

    mensagem = (
        f"Olá, {nome}! Sou seu assistente de concursos públicos.\n\n"
        "Estou aqui para te ajudar a encontrar as melhores oportunidades de "
        "concursos no Brasil.\n\n"
        "Comece registrando seus estados de interesse:\n"
        "<code>/uf RJ SP</code>\n\n"
        "Para ver tudo que sei fazer, digite <b>/help</b>."
    )

    await update.effective_message.reply_text(mensagem, parse_mode="HTML")
    logger.info("Usuário %s iniciou o bot.", user_id)


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mensagem = (
        "<b>Guia de Comandos do Bot de Concursos</b>\n\n"

        "<b>/uf</b>\n"
        "Define ou mostra seus estados de interesse:\n"
        "  • <code>/uf RJ</code> → acompanha o Rio de Janeiro.\n"
        "  • <code>/uf RJ SP MG</code> → acompanha os três.\n"
        "  • <code>/uf</code> → mostra os estados já registrados.\n\n"

        "<b>/concursos</b>\n"
        "Envia na hora os concursos abertos que você ainda não recebeu.\n\n"

        "<b>/todos</b>\n"
        "Lista todos os concursos com inscrição aberta nos seus estados, "
        "mesmo os que você já viu.\n\n"

        "<b>/config</b>\n"
        "Ajusta filtros de salário mínimo, nível e vagas mínimas, e liga ou "
        "desliga as notificações automáticas.\n\n"

        "<b>Automático:</b> a cada hora eu atualizo a base e te aviso dos "
        "concursos novos que combinam com seus estados e filtros."
    )

    await update.effective_message.reply_text(mensagem, parse_mode="HTML")


async def uf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await _garantir_usuario(update)
    mensagem = update.effective_message

    if not context.args:
        ufs = await asyncio.to_thread(obter_ufs_usuario, user_id)
        if not ufs:
            await mensagem.reply_text(
                "❌ Você ainda não tem estados registrados.\n"
                "Exemplo: <code>/uf RJ SP</code>",
                parse_mode="HTML",
            )
        else:
            await mensagem.reply_text(f"🌎 Seus estados de interesse:\n• {formatar_ufs(ufs)}")
        return

    siglas = [arg.strip().lower() for arg in context.args]
    invalidas = [s for s in siglas if s not in SIGLAS_ESTADOS]
    if invalidas:
        await mensagem.reply_text(
            f"❌ Sigla inválida: {', '.join(s.upper() for s in invalidas)}.\n"
            "Use as siglas de duas letras, por exemplo: <code>/uf RJ SP MG</code>",
            parse_mode="HTML",
        )
        logger.warning("Usuário %s enviou siglas inválidas: %s", user_id, invalidas)
        return

    # Sem duplicatas, preservando a ordem digitada.
    slugs = list(dict.fromkeys(SIGLAS_ESTADOS[s] for s in siglas))
    await asyncio.to_thread(atualizar_uf_usuario, user_id, slugs)

    await mensagem.reply_text(
        f"🌍 Seus estados de interesse agora são:\n• {formatar_ufs(slugs)}"
    )
    logger.info("Usuário %s atualizou estados: %s", user_id, slugs)


async def _listar(update: Update, apenas_novos: bool) -> None:
    """Base de /concursos (só novidades) e /todos (tudo que está aberto)."""
    user_id = await _garantir_usuario(update)
    mensagem = update.effective_message

    ufs = await asyncio.to_thread(obter_ufs_usuario, user_id)
    if not ufs:
        await mensagem.reply_text(
            "❌ Você ainda não tem estados registrados.\n"
            "Exemplo: <code>/uf RJ SP</code>",
            parse_mode="HTML",
        )
        return

    salario, nivel, vagas = await asyncio.to_thread(obter_filtros, user_id)
    concursos = await asyncio.to_thread(
        buscar_concursos,
        ufs,
        salario,
        nivel,
        vagas,
        user_id if apenas_novos else None,
    )

    if not concursos:
        if apenas_novos:
            await mensagem.reply_text(
                "✅ Você já viu todos os concursos abertos para seus estados e filtros."
            )
        else:
            await mensagem.reply_text(
                "📭 Nenhum concurso com inscrição aberta nos seus estados e filtros.\n"
                "Tente afrouxar os filtros em /config."
            )
        return

    await mensagem.reply_text(
        f"📚 <b>{len(concursos)} concurso(s) encontrado(s)</b> em {formatar_ufs(ufs)}.",
        parse_mode="HTML",
    )

    enviados: list[int] = []
    for texto, ids in agrupar_em_mensagens(concursos, compacto=not apenas_novos):
        await mensagem.reply_text(texto, parse_mode="HTML")
        enviados.extend(ids)
        await asyncio.sleep(PAUSA_ENTRE_MENSAGENS)

    if apenas_novos and enviados:
        # Marca depois do envio: se falhar no meio, o restante volta na
        # próxima vez em vez de sumir.
        await asyncio.to_thread(marcar_enviados, user_id, enviados)

    await mensagem.reply_text("✅ Fim da lista.")


async def concursos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _listar(update, apenas_novos=True)


async def todos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _listar(update, apenas_novos=False)
