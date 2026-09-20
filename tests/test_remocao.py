import sqlite3
from datetime import date, timedelta

import db


def _concurso(titulo):
    return {
        "titulo": titulo,
        "link": f"https://exemplo/{titulo}",
        "inscricoes_ate": (date.today() + timedelta(days=30)).strftime("%d/%m/%Y"),
        "vagas": "10",
        "salario_max": "R$ 5.000,00",
        "nivel": "Superior",
    }


def _usuario_completo(banco, chat_id=1):
    banco.adicionar_usuario(chat_id, "Fulano")
    banco.atualizar_uf_usuario(chat_id, ["bahia", "sergipe"])
    banco.atualizar_filtros(chat_id, salario=5000, nivel="Superior")
    banco.salvar_concursos("bahia", [_concurso("A"), _concurso("B")])
    banco.marcar_enviados(chat_id, [c["id"] for c in banco.buscar_concursos(["bahia"])])
    return chat_id


def test_resumo_conta_o_que_existe(banco):
    user_id = _usuario_completo(banco)
    resumo = banco.resumo_do_usuario(user_id)

    assert resumo == {"ufs": 2, "enviados": 2, "cadastro": 1}


def test_resumo_de_quem_nao_existe(banco):
    assert banco.resumo_do_usuario(999) == {"ufs": 0, "enviados": 0, "cadastro": 0}


def test_remove_tudo_do_usuario(banco):
    user_id = _usuario_completo(banco)
    removidos = banco.remover_usuario(user_id)

    assert removidos == {
        "user_concursos_enviados": 2,
        "user_ufs": 2,
        "users": 1,
    }
    assert banco.resumo_do_usuario(user_id) == {"ufs": 0, "enviados": 0, "cadastro": 0}
    assert banco.usuario_ja_registrado(user_id) is False
    assert banco.obter_ufs_usuario(user_id) == []
    assert banco.obter_filtros(user_id) == (None, None, None)


def test_remocao_nao_afeta_outros_usuarios(banco):
    _usuario_completo(banco, chat_id=1)
    _usuario_completo(banco, chat_id=2)

    banco.remover_usuario(1)

    assert banco.resumo_do_usuario(2) == {"ufs": 2, "enviados": 2, "cadastro": 1}
    assert banco.listar_usuarios() == [2]


def test_remocao_nao_apaga_os_concursos(banco):
    """Concurso é dado público compartilhado, não é do usuário."""
    user_id = _usuario_completo(banco)
    banco.remover_usuario(user_id)

    assert len(banco.buscar_concursos(["bahia"])) == 2


def test_usuario_pode_voltar_do_zero(banco):
    user_id = _usuario_completo(banco)
    banco.remover_usuario(user_id)

    banco.adicionar_usuario(user_id, "Fulano")
    banco.atualizar_uf_usuario(user_id, ["parana"])

    assert banco.obter_ufs_usuario(user_id) == ["parana"]
    # Sem histórico: os concursos voltam a ser novidade para ele.
    assert len(banco.buscar_concursos(["bahia"], nao_enviados_para=user_id)) == 2


def test_remover_quem_nao_existe_nao_estoura(banco):
    assert banco.remover_usuario(999) == {
        "user_concursos_enviados": 0,
        "user_ufs": 0,
        "users": 0,
    }


def test_limpa_user_ufs_mesmo_sem_foreign_key(tmp_path, monkeypatch):
    """Regressão: no banco de produção, `user_ufs` não tem FK nenhuma.

    Ela foi criada antes de o projeto usar foreign keys, e `CREATE TABLE IF
    NOT EXISTS` não recria tabela existente. Confiar no ON DELETE CASCADE
    limparia `user_concursos_enviados` e deixaria as UFs órfãs — e o
    comportamento seria diferente num banco novo, que já nasce com a FK.
    """
    caminho = tmp_path / "sem_fk.db"
    conn = sqlite3.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE users (
            chat_id INTEGER PRIMARY KEY, nome TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            salario_min INTEGER, nivel TEXT, vagas_min INTEGER,
            notificacoes_ativas INTEGER DEFAULT 1
        );
        -- sem FOREIGN KEY, como está em produção
        CREATE TABLE user_ufs (user_id INTEGER, uf TEXT, PRIMARY KEY (user_id, uf));
        CREATE TABLE user_concursos_enviados (
            user_id INTEGER, concurso_id INTEGER,
            PRIMARY KEY (user_id, concurso_id)
        );
        CREATE TABLE concursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT UNIQUE, link TEXT,
            inscricoes_ate TEXT, vagas TEXT, salario_max TEXT, nivel TEXT, estado TEXT
        );
        INSERT INTO users (chat_id, nome) VALUES (1, 'Fulano');
        INSERT INTO user_ufs VALUES (1, 'bahia'), (1, 'sergipe');
        INSERT INTO user_concursos_enviados VALUES (1, 1);
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_FILE", str(caminho))
    db.criar_tabelas()

    with db.conectar() as conn:
        assert conn.execute("PRAGMA foreign_key_list(user_ufs)").fetchall() == []

    db.remover_usuario(1)

    with db.conectar() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_ufs").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM user_concursos_enviados"
        ).fetchone()[0] == 0
