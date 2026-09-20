"""Menu de configuração (/config) e seus callbacks inline."""

from __future__ import annotations

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.formatacao import formatar_ufs
from config import logger
from db import (
    atualizar_filtros,
    atualizar_notificacoes_usuario,
    notificacoes_ativas,
    obter_filtros,
    obter_ufs_usuario,
)

NIVEIS = {"medio": "Médio", "tecnico": "Técnico", "superior": "Superior"}


async def _mostrar(update: Update, texto: str, teclado: list) -> None:
    """Edita a mensagem do callback ou responde, conforme a origem.

    `edit_message_text` com conteúdo idêntico devolve "Message is not
    modified" — acontece sempre que o usuário reaperta o mesmo botão.
    """
    markup = InlineKeyboardMarkup(teclado)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                texto, reply_markup=markup, parse_mode="HTML"
            )
        except BadRequest as erro:
            if "not modified" not in str(erro).lower():
                raise
    else:
        await update.effective_message.reply_text(
            texto, reply_markup=markup, parse_mode="HTML"
        )


async def config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    salario, nivel, vagas = await asyncio.to_thread(obter_filtros, user_id)
    ufs = await asyncio.to_thread(obter_ufs_usuario, user_id)

    estados = formatar_ufs(ufs) if ufs else "nenhum (use /uf)"
    salario_fmt = f"R$ {salario:,}".replace(",", ".") if salario else "—"

    texto = (
        "⚙️ <b>Configurações do Bot</b>\n\n"
        f"🌎 Estados: <b>{estados}</b>\n"
        f"💵 Salário mínimo: <b>{salario_fmt}</b>\n"
        f"🎓 Nível: <b>{nivel or '—'}</b>\n"
        f"🏢 Vagas mínimas: <b>{vagas or '—'}</b>\n\n"
        "Escolha o que deseja configurar:"
    )

    teclado = [
        [InlineKeyboardButton("🔔 Notificações", callback_data="menu_notificacoes")],
        [
            InlineKeyboardButton("💵 Salário", callback_data="cfg_salario"),
            InlineKeyboardButton("🎓 Nível", callback_data="cfg_nivel"),
        ],
        [
            InlineKeyboardButton("🏢 Vagas", callback_data="cfg_vagas"),
            InlineKeyboardButton("♻️ Limpar filtros", callback_data="cfg_reset"),
        ],
    ]

    await _mostrar(update, texto, teclado)


async def menu_notificacoes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    ativas = await asyncio.to_thread(notificacoes_ativas, user_id)

    texto = (
        "🔔 <b>Configuração de Notificações</b>\n\n"
        "Escolha se deseja receber avisos automáticos de novos concursos.\n\n"
        f"Status atual: <b>{'ativas' if ativas else 'desativadas'}</b>"
    )

    if ativas:
        acao = InlineKeyboardButton("❌ Desativar", callback_data="desativar_notificacao")
    else:
        acao = InlineKeyboardButton("✅ Ativar", callback_data="ativar_notificacao")

    teclado = [[acao], [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")]]
    await _mostrar(update, texto, teclado)


async def _menu_salario(update: Update) -> None:
    teclado = [
        [
            InlineKeyboardButton("3k+", callback_data="sal_3000"),
            InlineKeyboardButton("5k+", callback_data="sal_5000"),
        ],
        [
            InlineKeyboardButton("8k+", callback_data="sal_8000"),
            InlineKeyboardButton("10k+", callback_data="sal_10000"),
        ],
        [InlineKeyboardButton("12k+", callback_data="sal_12000")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")],
    ]
    await _mostrar(
        update,
        "💵 <b>Escolha o salário mínimo:</b>\n\n"
        "<i>Concursos sem salário divulgado ficam de fora deste filtro.</i>",
        teclado,
    )


async def _menu_nivel(update: Update) -> None:
    teclado = [
        [
            InlineKeyboardButton("Médio", callback_data="niv_medio"),
            InlineKeyboardButton("Técnico", callback_data="niv_tecnico"),
        ],
        [InlineKeyboardButton("Superior", callback_data="niv_superior")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")],
    ]
    await _mostrar(update, "🎓 <b>Escolha o nível desejado:</b>", teclado)


async def _menu_vagas(update: Update) -> None:
    teclado = [
        [
            InlineKeyboardButton("5+", callback_data="vag_5"),
            InlineKeyboardButton("10+", callback_data="vag_10"),
        ],
        [
            InlineKeyboardButton("20+", callback_data="vag_20"),
            InlineKeyboardButton("50+", callback_data="vag_50"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")],
    ]
    await _mostrar(
        update,
        "🏢 <b>Escolha o mínimo de vagas:</b>\n\n"
        "<i>Concursos sem número de vagas divulgado ficam de fora deste filtro.</i>",
        teclado,
    )


async def callback_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data or ""

    submenus = {
        "cfg_salario": _menu_salario,
        "cfg_nivel": _menu_nivel,
        "cfg_vagas": _menu_vagas,
    }

    if data in submenus:
        await submenus[data](update)
        return

    if data == "menu_notificacoes":
        await menu_notificacoes(update, context)
        return

    if data in ("ativar_notificacao", "desativar_notificacao"):
        ativar = data == "ativar_notificacao"
        await asyncio.to_thread(atualizar_notificacoes_usuario, user_id, ativar)
        logger.info("Usuário %s %s notificações.", user_id, "ativou" if ativar else "desativou")
        await menu_notificacoes(update, context)
        return

    if data == "cfg_reset":
        await asyncio.to_thread(atualizar_filtros, user_id)
    elif data.startswith("niv_"):
        await asyncio.to_thread(
            atualizar_filtros, user_id, nivel=NIVEIS.get(data.removeprefix("niv_"))
        )
    elif data.startswith("sal_"):
        await asyncio.to_thread(
            atualizar_filtros, user_id, salario=int(data.removeprefix("sal_"))
        )
    elif data.startswith("vag_"):
        await asyncio.to_thread(
            atualizar_filtros, user_id, vagas=int(data.removeprefix("vag_"))
        )

    # Qualquer outro callback cai aqui e volta para o menu principal.
    await config(update, context)
