import sqlite3

import pytest
from cryptography.fernet import Fernet

import db


@pytest.fixture
def chave(monkeypatch):
    valor = Fernet.generate_key().decode()
    monkeypatch.setenv("NOME_KEY", valor)
    return valor


@pytest.fixture
def sem_chave(monkeypatch):
    monkeypatch.delenv("NOME_KEY", raising=False)


# --------------------------------------------------------------------------- #
# Ida e volta
# --------------------------------------------------------------------------- #

def test_cifra_e_decifra(chave):
    token = db.cifrar_nome("Kluivert")

    assert token != "Kluivert"
    assert "Kluivert" not in token
    assert db.decifrar_nome(token) == "Kluivert"


def test_acentos_sobrevivem(chave):
    assert db.decifrar_nome(db.cifrar_nome("João Conceição")) == "João Conceição"


def test_tokens_diferentes_para_o_mesmo_nome(chave):
    """Fernet usa IV aleatório: dois iguais não viram o mesmo token.

    Importa porque senão daria para descobrir quem tem o mesmo nome só
    comparando as linhas do banco.
    """
    assert db.cifrar_nome("Ana") != db.cifrar_nome("Ana")


def test_nome_vazio_ou_ausente(chave):
    assert db.cifrar_nome(None) is None
    assert db.cifrar_nome("") is None
    assert db.decifrar_nome(None) is None


# --------------------------------------------------------------------------- #
# Comportamento sem chave: falhar para o lado da privacidade
# --------------------------------------------------------------------------- #

def test_sem_chave_nao_guarda_nome(sem_chave, banco):
    """Melhor não guardar do que guardar em claro achando que está protegido."""
    banco.adicionar_usuario(1, "Kluivert")

    with banco.conectar() as conn:
        assert conn.execute(
            "SELECT nome FROM users WHERE chat_id = 1"
        ).fetchone()["nome"] is None


def test_chave_invalida_avisa_e_nao_guarda(monkeypatch, banco, caplog):
    monkeypatch.setenv("NOME_KEY", "isso-nao-e-uma-chave-fernet")

    with caplog.at_level("WARNING"):
        assert banco.cifrar_nome("Kluivert") is None
    assert any("NOME_KEY" in r.message for r in caplog.records)


def test_chave_trocada_nao_derruba(chave, banco, monkeypatch):
    """Perder a chave torna o nome ilegível, não quebra o bot."""
    banco.adicionar_usuario(1, "Kluivert")
    monkeypatch.setenv("NOME_KEY", Fernet.generate_key().decode())

    assert banco.obter_nome(1) is None       # ilegível, mas sem exceção
    assert banco.usuario_ja_registrado(1)    # o resto segue funcionando


# --------------------------------------------------------------------------- #
# Gravação e leitura pelo banco
# --------------------------------------------------------------------------- #

def test_nome_vai_cifrado_para_o_banco(chave, banco):
    banco.adicionar_usuario(1, "Kluivert")

    with banco.conectar() as conn:
        cru = conn.execute("SELECT nome FROM users WHERE chat_id = 1").fetchone()["nome"]

    # Quem abrir o arquivo do banco não lê o nome.
    assert "Kluivert" not in cru
    assert banco.obter_nome(1) == "Kluivert"


def test_obter_nome_de_quem_nao_existe(chave, banco):
    assert banco.obter_nome(999) is None


def test_remover_usuario_leva_o_nome(chave, banco):
    banco.adicionar_usuario(1, "Kluivert")
    banco.remover_usuario(1)

    assert banco.obter_nome(1) is None


# --------------------------------------------------------------------------- #
# Reconciliação de nomes antigos em texto puro
# --------------------------------------------------------------------------- #

def test_detecta_texto_puro(chave):
    assert db._esta_cifrado(db.cifrar_nome("Kluivert")) is True
    assert db._esta_cifrado("Kluivert") is False


def test_converte_nomes_antigos_em_texto_puro(tmp_path, monkeypatch):
    """Os 24 usuários existentes têm o nome em claro; o boot converte."""
    caminho = tmp_path / "legado.db"
    monkeypatch.setattr(db, "DB_FILE", str(caminho))
    monkeypatch.delenv("NOME_KEY", raising=False)
    db.criar_tabelas()

    with db.conectar() as conn:
        conn.executemany(
            "INSERT INTO users (chat_id, nome) VALUES (?, ?)",
            [(1, "Kluivert"), (2, "Ana"), (3, None)],
        )

    # A chave só aparece depois — é o cenário real de quem liga isso agora.
    monkeypatch.setenv("NOME_KEY", Fernet.generate_key().decode())
    assert db.cifrar_nomes_pendentes() == 2

    assert db.obter_nome(1) == "Kluivert"
    assert db.obter_nome(2) == "Ana"
    assert db.obter_nome(3) is None

    with db.conectar() as conn:
        crus = [r["nome"] for r in conn.execute("SELECT nome FROM users")]
    assert not any(c and "Kluivert" in c for c in crus)


def test_conversao_e_idempotente(chave, banco):
    banco.adicionar_usuario(1, "Kluivert")

    assert banco.cifrar_nomes_pendentes() == 0   # já está cifrado
    assert banco.obter_nome(1) == "Kluivert"     # e não foi cifrado duas vezes


def test_conversao_sem_chave_nao_mexe_em_nada(sem_chave, banco):
    """Sem chave, o texto puro antigo fica como está em vez de ser destruído."""
    with banco.conectar() as conn:
        conn.execute("INSERT INTO users (chat_id, nome) VALUES (1, 'Kluivert')")

    assert banco.cifrar_nomes_pendentes() == 0

    with banco.conectar() as conn:
        assert conn.execute(
            "SELECT nome FROM users WHERE chat_id = 1"
        ).fetchone()["nome"] == "Kluivert"
