from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import obter_filtros, atualizar_filtros, atualizar_notificacoes_usuario
from bot.handlers import menu_notificacoes


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
        "⚙️ <b>Configurações do Bot</b>\n\n"
        f"💵 Salário mínimo: <b>{salario or '—'}</b>\n"
        f"🎓 Nível: <b>{nivel or '—'}</b>\n"
        f"🏢 Vagas mínimas: <b>{vagas or '—'}</b>\n\n"
        "Escolha o que deseja configurar:"
    )

    teclado = [
        [InlineKeyboardButton("🔔 Notificações", callback_data="menu_notificacoes")],
        [
            InlineKeyboardButton("💵 Salário", callback_data="cfg_salario"),
            InlineKeyboardButton("🎓 Nível", callback_data="cfg_nivel")
        ],
        [
            InlineKeyboardButton("🏢 Vagas", callback_data="cfg_vagas"),
            InlineKeyboardButton("♻️ Reset Filtros", callback_data="cfg_reset")
        ]
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            texto,
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="HTML"
        )
    else:
        await msg.reply_text(
            texto,
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="HTML"
        )

        
async def menu_salario(query):
    teclado = [
        [InlineKeyboardButton("3k+", callback_data="sal_3000"), InlineKeyboardButton("5k+", callback_data="sal_5000")],
        [InlineKeyboardButton("8k+", callback_data="sal_8000"), InlineKeyboardButton("10k+", callback_data="sal_10000")],
        [InlineKeyboardButton("12k+", callback_data="sal_12000")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")]
    ]
    await query.edit_message_text("💵 <b>Escolha o salário mínimo:</b>", reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")

async def menu_nivel(query):
    teclado = [
        [InlineKeyboardButton("Médio", callback_data="niv_medio"), InlineKeyboardButton("Técnico", callback_data="niv_tecnico")],
        [InlineKeyboardButton("Superior", callback_data="niv_superior"), InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")]
    ]
    await query.edit_message_text("🎓 <b>Escolha o nível desejado:</b>", reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")

async def menu_vagas(query):
    teclado = [
        [InlineKeyboardButton("5+", callback_data="vag_5"), InlineKeyboardButton("10+", callback_data="vag_10")],
        [InlineKeyboardButton("20+", callback_data="vag_20"), InlineKeyboardButton("50+", callback_data="vag_50")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_menu")]
    ]
    await query.edit_message_text("🏢 <b>Escolha o mínimo de vagas:</b>", reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")


async def callback_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # -------- MENU NOTIFICAÇÕES --------
    if data == "menu_notificacoes":
        await menu_notificacoes(update, context)
        return

    # -------- MENU PRINCIPAL CONFIG --------
    if data == "cfg_menu":
        await config(update, context)
        return

    # -------- SUBMENUS --------
    if data == "cfg_salario":
        await menu_salario(query)
        return

    if data == "cfg_nivel":
        await menu_nivel(query)
        return

    if data == "cfg_vagas":
        await menu_vagas(query)
        return

    # -------- RESET --------
    if data == "cfg_reset":
        atualizar_filtros(user_id, None, None, None)
        await config(update, context)
        return

    # -------- FILTROS --------
    if data.startswith("niv_"):
        mapa = {
            "medio": "Médio",
            "tecnico": "Técnico",
            "superior": "Superior"
        }
        atualizar_filtros(user_id, nivel=mapa.get(data.split("_")[1]))

    elif data.startswith("sal_"):
        atualizar_filtros(user_id, salario=int(data.split("_")[1]))

    elif data.startswith("vag_"):
        atualizar_filtros(user_id, vagas=int(data.split("_")[1]))

    # -------- NOTIFICAÇÕES --------
    elif data == "ativar_notificacao":
        atualizar_notificacoes_usuario(user_id, 1)
        await menu_notificacoes(update, context)
        return

    elif data == "desativar_notificacao":
        atualizar_notificacoes_usuario(user_id, 0)
        await menu_notificacoes(update, context)
        return

    # -------- FALLBACK --------
    await config(update, context)