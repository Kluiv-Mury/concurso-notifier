import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

if not TELEGRAM_TOKEN:
    raise ValueError("❌ ERRO: O token do Telegram não foi encontrado no arquivo .env")

SIGLAS_ESTADOS = {
    "rj": "rio-de-janeiro", "sp": "sao-paulo", "mg": "minas-gerais", "es": "espirito-santo",
    "ba": "bahia", "pr": "parana", "sc": "santa-catarina", "rs": "rio-grande-do-sul", "df": "distrito-federal",
    "go": "goias", "pe": "pernambuco", "ce": "ceara", "ma": "maranhao", "pi": "piaui", "pb": "paraiba",
    "rn": "rio-grande-do-norte", "ms": "mato-grosso-do-sul", "mt": "mato-grosso", "al": "alagoas", "se": "sergipe",
    "ac": "acre", "am": "amazonas", "ro": "rondonia", "rr": "roraima", "to": "tocantins", "ap": "amapa", "pa": "para"
}

SLUG_PARA_SIGLA = {v: k.upper() for k, v in SIGLAS_ESTADOS.items()}