"""Configuração, logging e tabelas de estados."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
# httpx loga uma linha por requisição à API do Telegram — ruído puro em INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("concurso-notifier")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError(
        "TELEGRAM_TOKEN não encontrado. Copie .env.example para .env e "
        "preencha com o token do @BotFather."
    )


def _intervalo(nome: str, padrao_minutos: int) -> int:
    """Lê um intervalo em minutos do ambiente e devolve em segundos."""
    try:
        minutos = int(os.getenv(nome, padrao_minutos))
    except ValueError:
        logger.warning("%s inválido, usando o padrão de %d min.", nome, padrao_minutos)
        minutos = padrao_minutos
    return max(minutos, 1) * 60


INTERVALO_SCRAPING = _intervalo("INTERVALO_SCRAPING_MIN", 61)
INTERVALO_ALERTAS = _intervalo("INTERVALO_ALERTAS_MIN", 17)
INTERVALO_BACKUP = _intervalo("INTERVALO_BACKUP_MIN", 24 * 60)

def _admin_chat_id() -> int | None:
    """Chat que recebe avisos de saúde do scraping.

    Sem isso os problemas só aparecem no log, onde ninguém olha até alguém
    reclamar. Não configurar é uma escolha legítima e silenciosa; o aviso é
    só para o caso de estar configurado e ilegível.
    """
    bruto = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not bruto:
        return None
    try:
        return int(bruto)
    except ValueError:
        logger.warning(
            "ADMIN_CHAT_ID=%r não é um número; avisos de saúde só irão para o log.",
            bruto,
        )
        return None


ADMIN_CHAT_ID = _admin_chat_id()


def chave_nome() -> str | None:
    """Chave Fernet usada para cifrar o nome do usuário no banco.

    Lida a cada chamada, e não uma vez na importação, para que os testes
    possam trocá-la. Sem chave configurada o nome simplesmente não é
    guardado: o padrão falha na direção da privacidade, não da exposição.

    Gerar uma:
        python -c "from cryptography.fernet import Fernet; \\
                   print(Fernet.generate_key().decode())"
    """
    return os.getenv("NOME_KEY", "").strip() or None

SIGLAS_ESTADOS = {
    "ac": "acre", "al": "alagoas", "am": "amazonas", "ap": "amapa",
    "ba": "bahia", "ce": "ceara", "df": "distrito-federal", "es": "espirito-santo",
    "go": "goias", "ma": "maranhao", "mg": "minas-gerais", "ms": "mato-grosso-do-sul",
    "mt": "mato-grosso", "pa": "para", "pb": "paraiba", "pe": "pernambuco",
    "pi": "piaui", "pr": "parana", "rj": "rio-de-janeiro", "rn": "rio-grande-do-norte",
    "ro": "rondonia", "rr": "roraima", "rs": "rio-grande-do-sul", "sc": "santa-catarina",
    "se": "sergipe", "sp": "sao-paulo", "to": "tocantins",
}

SLUG_PARA_SIGLA = {slug: sigla.upper() for sigla, slug in SIGLAS_ESTADOS.items()}
