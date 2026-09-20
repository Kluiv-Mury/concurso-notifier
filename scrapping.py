"""Coleta de concursos no acheconcursos.com.br.

Tudo aqui é síncrono e bloqueante de propósito (`requests` + `time.sleep`).
Quem chama de dentro do bot precisa usar `coletar_concursos()`, que joga o
trabalho numa thread — rodar isso direto no event loop deixa o bot mudo
durante todo o ciclo de scraping.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from config import logger

BASE_URL = "https://www.acheconcursos.com.br/concursos-{estado}"

TENTATIVAS = 3
TIMEOUT = 15
# Intervalo entre requisições, para não martelar a origem.
PAUSA_ENTRE_ESTADOS = (1.5, 3.5)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}

session = requests.Session()
session.headers.update(HEADERS)


def _buscar_html(url: str, estado: str) -> Optional[str]:
    """Baixa a página com retry em 429 e erro de rede. None se desistir."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = session.get(url, timeout=TIMEOUT)
        except requests.RequestException as erro:
            espera = random.uniform(4, 10)
            logger.warning(
                "%s: erro de conexão (%d/%d), tentando de novo em %.1fs: %s",
                estado, tentativa, TENTATIVAS, espera, erro,
            )
            time.sleep(espera)
            continue

        if resposta.status_code == 200:
            # O site declara charset no header, mas se vier ausente o requests
            # assume latin-1 e os acentos viram lixo.
            if resposta.encoding is None:
                resposta.encoding = resposta.apparent_encoding or "utf-8"
            return resposta.text

        if resposta.status_code == 429:
            espera = random.uniform(6, 12)
            logger.warning(
                "%s: bloqueio temporário 429 (%d/%d), aguardando %.1fs",
                estado, tentativa, TENTATIVAS, espera,
            )
            time.sleep(espera)
            continue

        logger.error("%s: HTTP %d em %s", estado, resposta.status_code, url)
        return None

    logger.error("%s: desisti após %d tentativas.", estado, TENTATIVAS)
    return None


def _extrair_concursos(html: str) -> List[Dict[str, Optional[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    concursos: List[Dict[str, Optional[str]]] = []

    for linha in soup.select("table.tbl-conc tr")[1:]:
        colunas = linha.find_all("td")
        if len(colunas) < 4:
            continue

        link_tag = colunas[0].find("a")
        titulo_tag = colunas[0].find("span", class_="titulo")
        nivel_tag = colunas[0].find("span", class_="vagas")

        titulo = titulo_tag.get_text(strip=True) if titulo_tag else ""
        if not titulo:
            continue

        nivel = None
        if nivel_tag:
            nivel = nivel_tag.get_text(strip=True).replace("Nível:", "").strip() or None

        concursos.append({
            "titulo": titulo,
            "link": link_tag["href"] if link_tag and link_tag.has_attr("href") else "",
            "nivel": nivel,
            "inscricoes_ate": colunas[1].get_text(strip=True),
            "vagas": colunas[2].get_text(strip=True),
            "salario_max": colunas[3].get_text(strip=True),
        })

    return concursos


def concursos_ache_conc(estado: str) -> List[Dict[str, Optional[str]]]:
    """Concursos abertos de um estado (slug, ex. 'rio-de-janeiro'). Bloqueante."""
    slug = estado.replace(" ", "-").strip().lower()
    html = _buscar_html(BASE_URL.format(estado=slug), slug)
    if html is None:
        return []

    concursos = _extrair_concursos(html)
    logger.info("%s: %d concursos encontrados.", slug, len(concursos))

    time.sleep(random.uniform(*PAUSA_ENTRE_ESTADOS))
    return concursos


async def coletar_concursos(estado: str) -> List[Dict[str, Optional[str]]]:
    """Versão para usar dentro do bot: roda o scraping fora do event loop."""
    return await asyncio.to_thread(concursos_ache_conc, estado)
