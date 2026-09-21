import os
import sys
from pathlib import Path

# `config` aborta sem token; nos testes basta um valor qualquer.
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-teste")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date  # noqa: E402

import pytest  # noqa: E402

import db as _db  # noqa: E402


def hoje_do_bot() -> date:
    """Hoje no fuso do bot, não no do runner.

    `date.today()` usa o fuso do sistema. Num CI em UTC ele discorda de
    `db.hoje()` (America/Sao_Paulo) das 21h às 23h59 de Brasília, e um
    concurso montado como "venceu ontem" ainda conta como aberto.
    """
    return date.fromisoformat(_db.hoje())


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Banco novo e isolado, com o esquema já criado."""
    monkeypatch.setattr(_db, "DB_FILE", str(tmp_path / "teste.db"))
    _db.criar_tabelas()
    return _db
