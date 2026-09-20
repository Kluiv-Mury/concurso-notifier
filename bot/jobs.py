"""Tarefas periódicas: atualizar a base e avisar os usuários."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from bot.formatacao import agrupar_em_mensagens
from config import ADMIN_CHAT_ID, SIGLAS_ESTADOS, logger
from db import (
    atualizar_notificacoes_usuario,
    buscar_concursos,
    fazer_backup,
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

# Fração mínima de estados que precisa trazer dados para o ciclo ser
# considerado saudável. Estado pequeno sem concurso aberto é normal; a
# maioria vazia não é.
LIMIAR_ESTADOS_SAUDAVEIS = 0.5

# Intervalo mínimo entre dois avisos ao admin (6h).
INTERVALO_AVISO_ADMIN = 6 * 60 * 60


async def backup_do_banco(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Salva uma cópia do banco.

    O arquivo guarda os usuários, as UFs de cada um, os filtros e o histórico
    de envios. Perder isso significa não só perder os cadastros: com o
    histórico zerado, tudo volta a ser novidade e cada usuário é notificado
    da base inteira outra vez.
    """
    try:
        await asyncio.to_thread(fazer_backup)
    except Exception:
        # Backup é rede de segurança: falhar aqui não pode derrubar o bot.
        logger.exception("Falha ao fazer backup do banco.")


@dataclass
class ResumoColeta:
    """Contagens de um ciclo de scraping, para diagnóstico."""

    com_dados: int = 0      # página veio e trouxe concursos
    vazios: int = 0         # página veio, mas nada foi extraído
    inacessiveis: int = 0   # página não veio (rede, HTTP de erro, bloqueio)
    coletados: int = 0
    novos: int = 0

    @property
    def visitados(self) -> int:
        return self.com_dados + self.vazios + self.inacessiveis

    def diagnostico(self) -> Optional[str]:
        """Mensagem de problema, ou None se o ciclo parece saudável.

        A distinção que importa: se as páginas carregaram e mesmo assim nada
        foi extraído, o problema é o parser (layout da origem mudou). Se elas
        nem carregaram, é rede ou bloqueio. Antes os dois casos eram a mesma
        lista vazia e o log dizia só "0 concursos encontrados" — idêntico a
        um dia em que realmente não há concurso aberto.
        """
        if self.visitados == 0:
            return "Nenhum estado chegou a ser visitado."

        if self.com_dados == 0:
            if self.vazios > self.inacessiveis:
                return (
                    f"As páginas carregaram ({self.vazios} estados) mas nada foi "
                    "extraído. Provável mudança de layout na origem — o seletor "
                    "'table.tbl-conc' em scrapping.py precisa ser revisto."
                )
            return (
                f"Nenhuma página carregou ({self.inacessiveis} estados). "
                "Origem fora do ar, sem rede ou o bot foi bloqueado."
            )

        # Degradação parcial: alguns estados vazios é normal (os pequenos têm
        # poucos concursos); a maioria vazia, não.
        if self.com_dados < self.visitados * LIMIAR_ESTADOS_SAUDAVEIS:
            return (
                f"Só {self.com_dados} de {self.visitados} estados trouxeram "
                f"dados ({self.vazios} vazios, {self.inacessiveis} inacessíveis)."
            )

        return None


async def _avisar_admin(context: ContextTypes.DEFAULT_TYPE, texto: str) -> None:
    """Manda o aviso ao admin, no máximo uma vez a cada INTERVALO_AVISO_ADMIN.

    Sem o intervalo, um scraping quebrado viraria uma mensagem por hora até
    alguém consertar — e aviso repetido demais vira ruído que se ignora.
    """
    if not ADMIN_CHAT_ID:
        return

    agora = time.time()
    ultimo = context.bot_data.get("ultimo_aviso_saude", 0)
    if agora - ultimo < INTERVALO_AVISO_ADMIN:
        return

    try:
        await context.bot.send_message(
            ADMIN_CHAT_ID, f"⚠️ <b>Scraping com problema</b>\n\n{texto}", parse_mode="HTML"
        )
        context.bot_data["ultimo_aviso_saude"] = agora
    except TelegramError:
        logger.exception("Não consegui avisar o admin sobre o scraping.")


async def atualizar_base_concursos(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Varre os 27 estados, grava o resultado e checa a saúde do ciclo.

    `coletar_concursos` roda numa thread: a varredura leva minutos e, dentro
    do event loop, o bot pararia de responder a comandos nesse intervalo.
    """
    logger.info("Iniciando scraping global...")
    resumo = ResumoColeta()

    for estado in SIGLAS_ESTADOS.values():
        try:
            concursos = await coletar_concursos(estado)
        except Exception:
            logger.exception("Falha ao coletar concursos de %s.", estado)
            resumo.inacessiveis += 1
            continue

        if concursos is None:
            resumo.inacessiveis += 1
            continue

        if not concursos:
            resumo.vazios += 1
            continue

        resumo.com_dados += 1
        resumo.coletados += len(concursos)

        try:
            novos = await asyncio.to_thread(salvar_concursos, estado, concursos)
        except Exception:
            logger.exception("Falha ao gravar concursos de %s.", estado)
            continue

        resumo.novos += novos
        logger.info("%s: %d coletados, %d novos.", estado, len(concursos), novos)

    logger.info(
        "Fim do scraping. %d estados com dados, %d vazios, %d inacessíveis; "
        "%d coletados, %d novos.",
        resumo.com_dados, resumo.vazios, resumo.inacessiveis,
        resumo.coletados, resumo.novos,
    )

    problema = resumo.diagnostico()
    if problema:
        logger.error("Scraping com problema: %s", problema)
        await _avisar_admin(context, problema)


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
