"""Montagem das mensagens enviadas no Telegram.

Todo texto vindo do scraping passa por `html.escape` antes de entrar numa
mensagem com `parse_mode="HTML"`. Um `&` ou `<` no título faz a API do
Telegram recusar a mensagem inteira com "Can't parse entities".
"""

from __future__ import annotations

from html import escape

from typing import Iterable, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import SLUG_PARA_SIGLA


def _campo(valor, padrao: str = "não informado") -> str:
    texto = str(valor).strip() if valor is not None else ""
    if not texto or texto == "-":
        return padrao
    return escape(texto)


def formatar_concurso(concurso: dict, compacto: bool = False) -> str:
    """Bloco de texto de um concurso. `compacto` usa 2 linhas em vez de 5."""
    titulo = _campo(concurso.get("titulo"), "Concurso")
    link = escape(concurso.get("link") or "")
    uf = SLUG_PARA_SIGLA.get(concurso.get("estado", ""), "")

    cabecalho = f"🔔 <b>{titulo}</b>"
    if uf:
        cabecalho += f" <i>({uf})</i>"

    if compacto:
        linhas = [
            cabecalho,
            f"💵 {_campo(concurso.get('salario_max'), '—')}"
            f" | 🏢 {_campo(concurso.get('vagas'), '—')} vagas"
            f" | 📅 até {_campo(concurso.get('inscricoes_ate'), '—')}",
        ]
    else:
        linhas = [
            cabecalho,
            f"💵 <b>Salário máximo:</b> {_campo(concurso.get('salario_max'))}",
            f"🏢 <b>Vagas:</b> {_campo(concurso.get('vagas'))}",
            f"📅 <b>Inscrições até:</b> {_campo(concurso.get('inscricoes_ate'))}",
            f"🎓 <b>Nível:</b> {_campo(concurso.get('nivel'))}",
        ]

    if link:
        linhas.append(f"🔗 {link}")

    return "\n".join(linhas)



def teclado_favorito(concurso_id, favoritado: bool) -> InlineKeyboardMarkup:
    """Botão único preso à mensagem de um concurso, no estado atual dele.

    Uma mensagem por concurso resolve o que numerar só contornava: o teclado
    do Telegram fica sempre no rodapé, então numa lista agrupada os botões
    viravam um bloco solto no fim, longe do concurso a que se referiam.
    """
    if favoritado:
        botao = InlineKeyboardButton(
            "💔 Remover dos favoritos", callback_data=f"desfav_{concurso_id}"
        )
    else:
        botao = InlineKeyboardButton(
            "⭐ Favoritar", callback_data=f"fav_{concurso_id}"
        )
    return InlineKeyboardMarkup([[botao]])


def agrupar_em_mensagens(
    concursos: Sequence[dict],
    compacto: bool = True,
    max_itens: Optional[int] = None,
) -> Iterator[tuple[str, list]]:
    """Junta vários concursos por mensagem, respeitando o limite do Telegram.

    Devolve `(texto, ids)` para quem envia marcar como entregue só o que de
    fato saiu. Usado onde a lista pode ser longa e não há botão por item —
    uma mensagem por concurso ali estouraria o limite de ~1 msg/s por chat.
    """
    atual: list[str] = []
    ids: list = []
    tamanho = 0

    for concurso in concursos:
        bloco = formatar_concurso(concurso, compacto=compacto)
        estourou = tamanho + len(bloco) > LIMITE_MENSAGEM
        cheio = max_itens is not None and len(atual) >= max_itens
        if atual and (estourou or cheio):
            yield "\n\n".join(atual), ids
            atual, ids, tamanho = [], [], 0
        atual.append(bloco)
        ids.append(concurso.get("id"))
        tamanho += len(bloco) + 2

    if atual:
        yield "\n\n".join(atual), ids


def formatar_lembrete(concurso: dict, dias: Optional[int]) -> str:
    """Bloco do aviso de prazo, com a urgência à frente do resto."""
    if dias is None:
        prazo = f"encerra em {_campo(concurso.get('inscricoes_ate'), '—')}"
    elif dias <= 0:
        prazo = "<b>encerra HOJE</b>"
    elif dias == 1:
        prazo = "<b>encerra AMANHÃ</b>"
    else:
        prazo = f"<b>faltam {dias} dias</b>"

    titulo = _campo(concurso.get("titulo"), "Concurso")
    uf = SLUG_PARA_SIGLA.get(concurso.get("estado", ""), "")
    link = escape(concurso.get("link") or "")

    linhas = [f"⏰ {prazo} — <b>{titulo}</b>" + (f" <i>({uf})</i>" if uf else "")]
    linhas.append(
        f"📅 até {_campo(concurso.get('inscricoes_ate'), '—')}"
        f" | 💵 {_campo(concurso.get('salario_max'), '—')}"
    )
    if link:
        linhas.append(f"🔗 {link}")
    return "\n".join(linhas)


def formatar_ufs(ufs: Iterable[str]) -> str:
    """Slugs do banco ('sao-paulo') para siglas legíveis ('SP')."""
    return ", ".join(SLUG_PARA_SIGLA.get(uf, uf.upper()) for uf in ufs)
