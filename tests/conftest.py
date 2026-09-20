import os
import sys
from pathlib import Path

# `config` aborta sem token; nos testes basta um valor qualquer.
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-teste")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import db as _db  # noqa: E402


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Banco novo e isolado, com o esquema já criado."""
    monkeypatch.setattr(_db, "DB_FILE", str(tmp_path / "teste.db"))
    _db.criar_tabelas()
    return _db
