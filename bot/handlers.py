"""Handlers dos comandos do bot."""

from __future__ import annotations

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from bot.formatacao import (
    formatar_concurso,
    formatar_ufs,
    teclado_favorito,
)
from config import SIGLAS_ESTADOS, logger
from db import (
    adicionar_usuario,
    atualizar_uf_usuario,
    atualizar_palavras_usuario,
    buscar_concursos,
    adicionar_favorito,
    ids_favoritos,
    listar_favoritos,
    remover_favorito,
    marcar_enviados,
    normalizar,
    obter_palavras_usuario,
    obter_filtros,
    obter_ufs_usuario,
    remover_usuario,
    resumo_do_usuario,
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

        "<b>/contem</b>\n"
        "Filtra por palavra no título do concurso:\n"
        "  • <code>/contem professor</code> → só o que menciona professor.\n"
        "  • <code>/contem medico enfermeiro</code> → qualquer uma das duas.\n"
        "  • <code>/contem limpar</code> → volta a receber tudo.\n\n"

        "<b>/favoritos</b>\n"
        "Mostra os concursos que você guardou no botão ⭐.\n\n"

        "<b>/config</b>\n"
        "Ajusta filtros de salário mínimo, nível e vagas mínimas, e liga ou "
        "desliga as notificações automáticas.\n\n"

        "<b>/deletar</b>\n"
        "Apaga todos os seus dados daqui: cadastro, estados, filtros e "
        "histórico. Pede confirmação antes.\n\n"

        "<b>Automático:</b> a cada hora eu atualizo a base e te aviso dos "
        "concursos novos que combinam com seus estados e filtros. Quando o "
        "prazo de algum que você recebeu estiver acabando, eu lembro."
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


async def _enviar_um_a_um(mensagem, user_id: int, concursos: list[dict]) -> list[int]:
    """Uma mensagem por concurso, cada uma com seu próprio botão de favorito.

    Devolve os ids que realmente saíram.
    """
    favoritos = await asyncio.to_thread(ids_favoritos, user_id)
    enviados: list[int] = []

    for concurso in concursos:
        cid = concurso.get("id")
        try:
            # Preview ligado de propósito: com um concurso só na mensagem, o
            # cartão traz imagem e descrição próprias do edital.
            await mensagem.reply_text(
                formatar_concurso(concurso),
                parse_mode="HTML",
                reply_markup=teclado_favorito(cid, cid in favoritos),
            )
        except RetryAfter as erro:
            # Lista longa passa do ~1 msg/s por chat. Esperar o que a API
            # pediu e reenviar é melhor que perder o concurso em silêncio.
            logger.warning("Flood control em %s: aguardando %ss.", user_id, erro.retry_after)
            await asyncio.sleep(erro.retry_after + 1)
            await mensagem.reply_text(
                formatar_concurso(concurso),
                parse_mode="HTML",
                reply_markup=teclado_favorito(cid, cid in favoritos),
            )
        except TelegramError:
            logger.exception("Erro ao enviar concurso %s para %s.", cid, user_id)
            break

        enviados.append(cid)
        await asyncio.sleep(PAUSA_ENTRE_MENSAGENS)

    return enviados


async def _concursos_do_usuario(user_id: int, apenas_novos: bool) -> list[dict]:
    """Busca com os estados, filtros e palavras que o usuário configurou."""
    ufs = await asyncio.to_thread(obter_ufs_usuario, user_id)
    if not ufs:
        return []

    salario, nivel, vagas = await asyncio.to_thread(obter_filtros, user_id)
    palavras = await asyncio.to_thread(obter_palavras_usuario, user_id)
    return await asyncio.to_thread(
        buscar_concursos,
        ufs,
        salario,
        nivel,
        vagas,
        user_id if apenas_novos else None,
        None,
        palavras,
    )


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

    concursos = await _concursos_do_usuario(user_id, apenas_novos)

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

    # Uma mensagem por concurso em toda listagem: é o que prende o ⭐ ao
    # concurso certo. O teclado do Telegram fica sempre no rodapé, então
    # numa mensagem com vários ele não teria como apontar para um deles.
    enviados = await _enviar_um_a_um(mensagem, user_id, concursos)

    if apenas_novos and enviados:
        # Marca depois do envio: se falhar no meio, o restante volta na
        # próxima vez em vez de sumir.
        await asyncio.to_thread(marcar_enviados, user_id, enviados)

    await mensagem.reply_text("✅ Fim da lista.")


async def concursos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _listar(update, apenas_novos=True)


async def todos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _listar(update, apenas_novos=False)


# --------------------------------------------------------------------------- #
# Palavras-chave
# --------------------------------------------------------------------------- #

async def contem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Define ou mostra as palavras que o título precisa conter.

    Os filtros existentes eram todos quantitativos — salário, nível, vagas —
    e não havia como dizer *o que* se procura. Quem queria concurso de
    professor recebia tudo do estado e filtrava no olho.
    """
    user_id = await _garantir_usuario(update)
    mensagem = update.effective_message

    if not context.args:
        palavras = await asyncio.to_thread(obter_palavras_usuario, user_id)
        if not palavras:
            await mensagem.reply_text(
                "🔍 Você não filtra por palavra: recebe todos os concursos "
                "dos seus estados.\n\n"
                "Para filtrar: <code>/contem professor medico</code>\n"
                "Basta uma das palavras aparecer no título.",
                parse_mode="HTML",
            )
        else:
            await mensagem.reply_text(
                f"🔍 Suas palavras-chave:\n• {', '.join(palavras)}\n\n"
                "Para limpar: <code>/contem limpar</code>",
                parse_mode="HTML",
            )
        return

    if len(context.args) == 1 and normalizar(context.args[0]) in ("limpar", "remover"):
        await asyncio.to_thread(atualizar_palavras_usuario, user_id, [])
        await mensagem.reply_text(
            "🔍 Filtro de palavras removido. Você volta a receber todos os "
            "concursos dos seus estados."
        )
        return

    gravadas = await asyncio.to_thread(
        atualizar_palavras_usuario, user_id, context.args
    )
    if not gravadas:
        await mensagem.reply_text("❌ Não entendi nenhuma palavra válida.")
        return

    await mensagem.reply_text(
        f"🔍 Agora você só recebe concursos cujo título contenha:\n"
        f"• {', '.join(gravadas)}"
    )
    logger.info("Usuário %s definiu palavras: %s", user_id, gravadas)


# --------------------------------------------------------------------------- #
# Favoritos
# --------------------------------------------------------------------------- #

async def favoritos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await _garantir_usuario(update)
    mensagem = update.effective_message

    lista = await asyncio.to_thread(listar_favoritos, user_id)
    if not lista:
        await mensagem.reply_text(
            "⭐ Você ainda não favoritou nenhum concurso.\n\n"
            "Use o botão ⭐ abaixo dos concursos em /concursos para guardar "
            "os que te interessam."
        )
        return

    await mensagem.reply_text(
        f"⭐ <b>{len(lista)} concurso(s) favoritado(s)</b>, do que encerra "
        "mais cedo para o mais tarde:",
        parse_mode="HTML",
    )

    # Todos já são favoritos, então cada um nasce com o botão de remover.
    await _enviar_um_a_um(mensagem, user_id, lista)


async def callback_favoritar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    dado = query.data or ""

    # Ação explícita no callback, em vez de alternar às cegas: o botão já
    # mostra o estado, e dois toques rápidos não se atrapalham.
    remover = dado.startswith("desfav_")
    prefixo = "desfav_" if remover else "fav_"

    try:
        concurso_id = int(dado.removeprefix(prefixo))
    except ValueError:
        await query.answer("Não consegui identificar esse concurso.")
        return

    if remover:
        await asyncio.to_thread(remover_favorito, user_id, concurso_id)
        await query.answer("Removido dos favoritos.")
    else:
        await asyncio.to_thread(adicionar_favorito, user_id, concurso_id)
        await query.answer("⭐ Adicionado. Veja em /favoritos")

    # Vira o botão para refletir o novo estado, sem reescrever o texto.
    try:
        await query.edit_message_reply_markup(
            reply_markup=teclado_favorito(concurso_id, favoritado=not remover)
        )
    except BadRequest as erro:
        if "not modified" not in str(erro).lower():
            raise


# --------------------------------------------------------------------------- #
# Remoção de dados
# --------------------------------------------------------------------------- #

async def deletar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o que será apagado e pede confirmação.

    Bloquear o bot só interrompe as mensagens; os dados continuariam aqui.
    Este é o caminho para sair de verdade.
    """
    user_id = await _garantir_usuario(update)
    resumo = await asyncio.to_thread(resumo_do_usuario, user_id)

    texto = (
        "🗑 <b>Apagar meus dados</b>\n\n"
        "Guardo sobre você:\n"
        f"• cadastro (seu ID e primeiro nome): {resumo['cadastro']}\n"
        f"• estados de interesse: {resumo['ufs']}\n"
        f"• filtros de salário, nível e vagas\n"
        f"• histórico de concursos enviados: {resumo['enviados']}\n\n"
        "Apagar remove tudo isso e <b>não dá para desfazer</b>. "
        "Você pode voltar quando quiser com /start, começando do zero."
    )

    teclado = [
        [InlineKeyboardButton("🗑 Sim, apagar tudo", callback_data="del_confirmar")],
        [InlineKeyboardButton("⬅️ Cancelar", callback_data="del_cancelar")],
    ]

    await update.effective_message.reply_text(
        texto, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML"
    )


async def callback_deletar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "del_cancelar":
        await query.edit_message_text("✅ Nada foi apagado. Seus dados continuam aqui.")
        return

    removidos = await asyncio.to_thread(remover_usuario, user_id)
    logger.info("Usuário %s apagou os próprios dados: %s", user_id, removidos)

    await query.edit_message_text(
        "🗑 <b>Pronto, tudo apagado.</b>\n\n"
        "Não guardo mais nenhum dado seu. Se um dia quiser voltar, "
        "é só mandar /start.",
        parse_mode="HTML",
    )
