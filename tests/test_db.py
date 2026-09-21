import sqlite3
from datetime import date, timedelta

import pytest

import db
from conftest import hoje_do_bot


def _data(dias: int) -> str:
    """Data em dd/mm/aaaa deslocada de hoje."""
    return (hoje_do_bot() + timedelta(days=dias)).strftime("%d/%m/%Y")


def _concurso(titulo, dias=30, salario="R$ 5.000,00", vagas="10", nivel="Superior"):
    return {
        "titulo": titulo,
        "link": f"https://exemplo/{titulo}",
        "inscricoes_ate": _data(dias),
        "vagas": vagas,
        "salario_max": salario,
        "nivel": nivel,
    }


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bruto,esperado", [
    ("13/02/2026", "2026-02-13"),
    ("01/01/2030", "2030-01-01"),
    ("-", None),
    ("", None),
    (None, None),
    ("13-02-2026", None),
])
def test_parse_data(bruto, esperado):
    assert db.parse_data(bruto) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    ("R$ 13.288,85", 13288.85),
    ("R$ 990", 990.0),
    ("R$ 1.500,00 a R$ 3.000,00", 3000.0),  # faixa: interessa o máximo
    ("-", None),
    (None, None),
])
def test_parse_salario(bruto, esperado):
    assert db.parse_salario(bruto) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    ("49", 49),
    ("1.200", 1200),
    (7, 7),
    ("-", None),  # não divulgado é diferente de zero
    ("", None),
    (None, None),
])
def test_parse_vagas(bruto, esperado):
    assert db.parse_vagas(bruto) == esperado


# --------------------------------------------------------------------------- #
# Gravação
# --------------------------------------------------------------------------- #

def test_salvar_ignora_data_invalida(banco):
    novos = banco.salvar_concursos("bahia", [_concurso("Sem prazo") | {"inscricoes_ate": "-"}])
    assert novos == 0
    assert banco.buscar_concursos(["bahia"]) == []


def test_salvar_atualiza_em_vez_de_duplicar(banco):
    banco.salvar_concursos("bahia", [_concurso("Concurso X", salario="R$ 3.000,00")])
    novos = banco.salvar_concursos("bahia", [_concurso("Concurso X", salario="R$ 9.000,00")])

    resultado = banco.buscar_concursos(["bahia"])
    assert novos == 0
    assert len(resultado) == 1
    # Prazo prorrogado e salário retificado precisam sobrescrever o registro.
    assert resultado[0]["salario_max"] == "R$ 9.000,00"


def test_mesmo_titulo_em_estados_diferentes(banco):
    """Concurso nacional aparece na lista dos dois estados, não só no primeiro."""
    banco.salvar_concursos("bahia", [_concurso("Concurso Nacional")])
    banco.salvar_concursos("sergipe", [_concurso("Concurso Nacional")])

    assert len(banco.buscar_concursos(["bahia"])) == 1
    assert len(banco.buscar_concursos(["sergipe"])) == 1


# --------------------------------------------------------------------------- #
# Busca e filtros
# --------------------------------------------------------------------------- #

def test_expirados_ficam_de_fora(banco):
    banco.salvar_concursos("bahia", [
        _concurso("Aberto", dias=10),
        _concurso("Encerrado", dias=-1),
        _concurso("Ultimo dia", dias=0),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"])}
    assert titulos == {"Aberto", "Ultimo dia"}


def test_filtro_salario(banco):
    banco.salvar_concursos("bahia", [
        _concurso("Alto", salario="R$ 12.000,00"),
        _concurso("Baixo", salario="R$ 2.000,00"),
        _concurso("Sem informacao", salario="-"),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"], salario=5000)}
    # 'Sem informacao' não pode entrar: o texto literal não é um salário alto.
    assert titulos == {"Alto"}


def test_filtro_vagas_ignora_quantidade_nao_divulgada(banco):
    banco.salvar_concursos("bahia", [
        _concurso("Muitas", vagas="80"),
        _concurso("Poucas", vagas="2"),
        _concurso("Nao divulgado", vagas="-"),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"], vagas=20)}
    assert titulos == {"Muitas"}


def test_filtro_nivel_por_substring(banco):
    banco.salvar_concursos("bahia", [
        _concurso("A", nivel="Médio, Técnico e Superior"),
        _concurso("B", nivel="Superior"),
        _concurso("C", nivel="Fundamental"),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"], nivel="Médio")}
    assert titulos == {"A"}


def test_ordena_por_salario_decrescente(banco):
    banco.salvar_concursos("bahia", [
        _concurso("Medio", salario="R$ 5.000,00"),
        _concurso("Maior", salario="R$ 13.288,85"),
        _concurso("Menor", salario="R$ 900,00"),
        _concurso("Sem valor", salario="-"),
    ])

    titulos = [c["titulo"] for c in banco.buscar_concursos(["bahia"])]
    assert titulos == ["Maior", "Medio", "Menor", "Sem valor"]


def test_busca_restrita_as_ufs_pedidas(banco):
    banco.salvar_concursos("bahia", [_concurso("Da Bahia")])
    banco.salvar_concursos("sergipe", [_concurso("De Sergipe")])

    assert [c["titulo"] for c in banco.buscar_concursos(["bahia"])] == ["Da Bahia"]
    assert banco.buscar_concursos([]) == []


def test_limite(banco):
    banco.salvar_concursos("bahia", [_concurso(f"C{i}") for i in range(10)])
    assert len(banco.buscar_concursos(["bahia"], limite=3)) == 3


# --------------------------------------------------------------------------- #
# Controle de envios
# --------------------------------------------------------------------------- #

def test_nao_enviados_exclui_o_que_ja_saiu(banco):
    banco.adicionar_usuario(1, "Fulano")
    banco.salvar_concursos("bahia", [_concurso("A"), _concurso("B")])

    todos = banco.buscar_concursos(["bahia"], nao_enviados_para=1)
    assert len(todos) == 2

    banco.marcar_enviados(1, [todos[0]["id"]])

    restantes = banco.buscar_concursos(["bahia"], nao_enviados_para=1)
    assert [c["id"] for c in restantes] == [todos[1]["id"]]


def test_marcar_enviados_e_idempotente(banco):
    banco.adicionar_usuario(1, "Fulano")
    banco.salvar_concursos("bahia", [_concurso("A")])
    cid = banco.buscar_concursos(["bahia"])[0]["id"]

    banco.marcar_enviados(1, [cid])
    banco.marcar_enviados(1, [cid])  # não pode estourar em UNIQUE

    assert banco.buscar_concursos(["bahia"], nao_enviados_para=1) == []


# --------------------------------------------------------------------------- #
# Usuários e filtros
# --------------------------------------------------------------------------- #

def test_filtros_do_usuario(banco):
    banco.adicionar_usuario(1, "Fulano")
    assert banco.obter_filtros(1) == (None, None, None)

    banco.atualizar_filtros(1, salario=5000)
    banco.atualizar_filtros(1, nivel="Superior")
    assert banco.obter_filtros(1) == (5000, "Superior", None)

    banco.atualizar_filtros(1)  # sem argumentos limpa tudo
    assert banco.obter_filtros(1) == (None, None, None)


def test_filtros_de_usuario_inexistente(banco):
    assert banco.obter_filtros(999) == (None, None, None)


def test_atualizar_ufs_substitui_as_anteriores(banco):
    banco.adicionar_usuario(1, "Fulano")
    banco.atualizar_uf_usuario(1, ["bahia", "sergipe"])
    banco.atualizar_uf_usuario(1, ["parana"])

    assert banco.obter_ufs_usuario(1) == ["parana"]


def test_listar_usuarios_so_traz_ativos_com_uf(banco):
    banco.adicionar_usuario(1, "Com UF")
    banco.adicionar_usuario(2, "Sem UF")
    banco.adicionar_usuario(3, "Silenciado")
    banco.atualizar_uf_usuario(1, ["bahia"])
    banco.atualizar_uf_usuario(3, ["bahia"])
    banco.atualizar_notificacoes_usuario(3, False)

    assert banco.listar_usuarios() == [1]


def test_notificacoes_padrao_ligadas(banco):
    banco.adicionar_usuario(1, "Fulano")
    assert banco.notificacoes_ativas(1) is True

    banco.atualizar_notificacoes_usuario(1, False)
    assert banco.notificacoes_ativas(1) is False


# --------------------------------------------------------------------------- #
# Migração
# --------------------------------------------------------------------------- #

def test_migracao_preserva_historico_de_envios(tmp_path, monkeypatch):
    """Regressão: a reconstrução de `concursos` não pode zerar os envios.

    Com as FKs ligadas, o RENAME redirecionava o `REFERENCES concursos` de
    `user_concursos_enviados` para a tabela temporária e o DROP apagava tudo
    em cascata — todos os usuários receberiam a base inteira de novo.
    """
    caminho = tmp_path / "legado.db"

    # Esquema anterior: UNIQUE global no título e sem as colunas de filtro.
    conn = sqlite3.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE concursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT UNIQUE, link TEXT, inscricoes_ate TEXT,
            vagas TEXT, salario_max TEXT, nivel TEXT, estado TEXT
        );
        CREATE TABLE users (
            chat_id INTEGER PRIMARY KEY, nome TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE user_ufs (user_id INTEGER, uf TEXT, PRIMARY KEY (user_id, uf));
        CREATE TABLE user_concursos_enviados (
            user_id INTEGER, concurso_id INTEGER,
            PRIMARY KEY (user_id, concurso_id),
            FOREIGN KEY (user_id) REFERENCES users (chat_id) ON DELETE CASCADE,
            FOREIGN KEY (concurso_id) REFERENCES concursos (id) ON DELETE CASCADE
        );
        CREATE TABLE user_concursos (user_id INTEGER, concurso_id INTEGER);
        INSERT INTO users (chat_id, nome) VALUES (1, 'Fulano');
        INSERT INTO concursos (titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado)
            VALUES ('Antigo', 'http://x', '13/02/2026', '49', 'R$ 13.288,85', 'Superior', 'bahia');
        INSERT INTO user_concursos_enviados (user_id, concurso_id) VALUES (1, 1);
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_FILE", str(caminho))
    db.criar_tabelas()
    db.criar_tabelas()  # idempotente

    with db.conectar() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_concursos_enviados").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM concursos").fetchone()[0] == 1
        assert conn.execute("SELECT versao FROM schema_version").fetchone()[0] == db.SCHEMA_VERSION
        # A tabela órfã da versão antiga some.
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='user_concursos'"
        ).fetchone()[0] == 0
        # Backfill das colunas normalizadas a partir do texto já gravado.
        linha = conn.execute(
            "SELECT inscricoes_ate_iso, salario_num, vagas_num FROM concursos"
        ).fetchone()
        assert tuple(linha) == ("2026-02-13", 13288.85, 49)


def test_migracao_cria_colunas_de_filtro(banco):
    """Banco novo já nasce com as colunas que o /config usa."""
    with banco.conectar() as conn:
        colunas = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    assert {"salario_min", "nivel", "vagas_min", "notificacoes_ativas"} <= colunas
