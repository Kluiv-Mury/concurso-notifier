from datetime import date, timedelta

import pytest

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


def _popular(banco):
    banco.adicionar_usuario(1, "Fulano")
    banco.atualizar_uf_usuario(1, ["bahia"])
    banco.atualizar_filtros(1, salario=5000)
    banco.salvar_concursos("bahia", [_concurso("A"), _concurso("B")])
    banco.marcar_enviados(1, [banco.buscar_concursos(["bahia"])[0]["id"]])


def test_wal_ligado(banco):
    """No modo `delete`, o scraping trancava o banco inteiro enquanto gravava."""
    with banco.conectar() as conn:
        modo = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert modo.lower() == "wal"


def test_backup_preserva_todos_os_dados(banco, monkeypatch):
    _popular(banco)
    destino = banco.fazer_backup()

    assert destino.exists()

    # Aponta o módulo para a cópia: ela tem que responder igual ao original.
    monkeypatch.setattr(banco, "DB_FILE", str(destino))

    assert banco.obter_ufs_usuario(1) == ["bahia"]
    assert banco.obter_filtros(1) == (5000, None, None)
    assert len(banco.buscar_concursos(["bahia"])) == 2
    # O histórico de envios é o que mais dói perder: sem ele, todo mundo
    # recebe a base inteira de novo.
    assert len(banco.buscar_concursos(["bahia"], nao_enviados_para=1)) == 1


def test_backup_roda_com_conexao_aberta(banco):
    """A API .backup() do SQLite é consistente com o banco em uso."""
    _popular(banco)

    with banco.conectar() as conn:
        conn.execute("INSERT INTO users (chat_id, nome) VALUES (99, 'Durante')")
        destino = banco.fazer_backup()

    assert destino.exists()


def test_dois_backups_no_mesmo_segundo_nao_se_sobrescrevem(banco):
    """Regressão: o carimbo tem resolução de segundo.

    Sem desambiguar o nome, o segundo backup sobrescrevia o primeiro em
    silêncio — perder cópia sem avisar é o pior desfecho num backup.
    """
    _popular(banco)
    primeiro = banco.fazer_backup()
    segundo = banco.fazer_backup()

    assert primeiro != segundo
    assert primeiro.exists() and segundo.exists()


def test_retencao_mantem_apenas_os_mais_recentes(banco):
    _popular(banco)

    for i in range(5):
        # O nome carrega carimbo de segundo; força nomes distintos.
        caminho = banco._dir_backup() / f"concursos-2026010{i}-000000.db"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"backup antigo")

    banco.fazer_backup(manter=3)

    restantes = sorted(p.name for p in banco._dir_backup().glob("concursos-*.db"))
    assert len(restantes) == 3
    # O recém-criado (2026-09-XX ou posterior) sobrevive; os mais velhos somem.
    assert restantes[-1].startswith("concursos-2")
    assert "concursos-20260100-000000.db" not in restantes


def test_retencao_nao_apaga_nada_com_manter_invalido(banco):
    _popular(banco)
    banco.fazer_backup()
    banco.fazer_backup(manter=0)  # guarda: 0 não pode significar "apague tudo"

    assert len(list(banco._dir_backup().glob("concursos-*.db"))) == 2


def test_backup_nao_escreve_fora_do_diretorio_do_banco(banco, tmp_path):
    """Regressão: o diretório é resolvido a partir do DB_FILE em uso."""
    _popular(banco)
    destino = banco.fazer_backup()

    assert destino.parent.parent == tmp_path
