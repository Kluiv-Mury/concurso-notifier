from datetime import date, timedelta

import pytest

import db
from bot.formatacao import MAX_ITENS_COM_BOTAO, agrupar_em_mensagens, teclado_favoritar


def _concurso(titulo, dias=30):
    return {
        "titulo": titulo,
        "link": f"https://exemplo/{titulo[:10]}",
        "inscricoes_ate": (date.today() + timedelta(days=dias)).strftime("%d/%m/%Y"),
        "vagas": "10",
        "salario_max": "R$ 5.000,00",
        "nivel": "Superior",
    }


@pytest.fixture
def base(banco):
    banco.adicionar_usuario(1, "Fulano")
    banco.atualizar_uf_usuario(1, ["bahia"])
    banco.salvar_concursos("bahia", [
        _concurso("Concurso Unirio abre vagas para Professores"),
        _concurso("Edital TRT: Analista Judiciário"),
        _concurso("Prefeitura abre vagas de Médico e Enfermeiro"),
    ])
    return banco


# --------------------------------------------------------------------------- #
# Normalização
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bruto,esperado", [
    ("Médico", "medico"),
    ("PROFESSOR", "professor"),
    ("  Analista  ", "analista"),
    ("Educação", "educacao"),
    ("", ""),
    (None, ""),
])
def test_normalizar(bruto, esperado):
    assert db.normalizar(bruto) == esperado


# --------------------------------------------------------------------------- #
# Filtro por palavra-chave
# --------------------------------------------------------------------------- #

def test_filtra_pelo_titulo(base):
    titulos = [c["titulo"] for c in base.buscar_concursos(["bahia"], palavras=["professor"])]
    assert titulos == ["Concurso Unirio abre vagas para Professores"]


def test_ignora_caixa_e_acento_nos_dois_sentidos(base):
    """'medico' tem que achar 'Médico', e 'médico' também."""
    com_acento = base.buscar_concursos(["bahia"], palavras=["médico"])
    sem_acento = base.buscar_concursos(["bahia"], palavras=["MEDICO"])

    assert len(com_acento) == len(sem_acento) == 1
    assert com_acento[0]["titulo"] == sem_acento[0]["titulo"]


def test_casa_com_parte_da_palavra(base):
    """'professor' precisa achar 'Professores'."""
    assert len(base.buscar_concursos(["bahia"], palavras=["professor"])) == 1


def test_varias_palavras_sao_OU(base):
    """Exigir todas quase nunca casaria: o título é manchete, não lista de cargos."""
    achados = base.buscar_concursos(["bahia"], palavras=["analista", "medico"])
    assert len(achados) == 2


def test_sem_palavras_traz_tudo(base):
    assert len(base.buscar_concursos(["bahia"])) == 3
    assert len(base.buscar_concursos(["bahia"], palavras=[])) == 3
    assert len(base.buscar_concursos(["bahia"], palavras=None)) == 3


def test_palavra_sem_resultado(base):
    assert base.buscar_concursos(["bahia"], palavras=["astronauta"]) == []


def test_palavra_combina_com_os_outros_filtros(base):
    base.salvar_concursos("bahia", [
        {**_concurso("Concurso para Professores"), "salario_max": "R$ 1.000,00"},
    ])
    achados = base.buscar_concursos(["bahia"], salario=3000, palavras=["professor"])

    assert [c["titulo"] for c in achados] == ["Concurso Unirio abre vagas para Professores"]


# --------------------------------------------------------------------------- #
# Palavras do usuário
# --------------------------------------------------------------------------- #

def test_grava_normalizado(base):
    gravadas = base.atualizar_palavras_usuario(1, ["Médico", "PROFESSOR"])

    assert gravadas == ["medico", "professor"]
    assert base.obter_palavras_usuario(1) == ["medico", "professor"]


def test_substitui_as_anteriores(base):
    base.atualizar_palavras_usuario(1, ["medico"])
    base.atualizar_palavras_usuario(1, ["professor"])

    assert base.obter_palavras_usuario(1) == ["professor"]


def test_limpar_palavras(base):
    base.atualizar_palavras_usuario(1, ["medico"])
    base.atualizar_palavras_usuario(1, [])

    assert base.obter_palavras_usuario(1) == []


def test_descarta_duplicata_e_vazio(base):
    gravadas = base.atualizar_palavras_usuario(1, ["medico", "MÉDICO", "  ", ""])
    assert gravadas == ["medico"]


# --------------------------------------------------------------------------- #
# Favoritos
# --------------------------------------------------------------------------- #

def test_favoritar_alterna(base):
    cid = base.buscar_concursos(["bahia"])[0]["id"]

    assert base.favoritar(1, cid) is True
    assert len(base.listar_favoritos(1)) == 1
    assert base.favoritar(1, cid) is False
    assert base.listar_favoritos(1) == []


def test_favoritos_encerrados_ficam_de_fora(base):
    base.salvar_concursos("bahia", [_concurso("Já encerrou", dias=-1)])
    with base.conectar() as conn:
        cid = conn.execute(
            "SELECT id FROM concursos WHERE titulo = 'Já encerrou'"
        ).fetchone()["id"]
    base.favoritar(1, cid)

    assert base.listar_favoritos(1) == []
    assert len(base.listar_favoritos(1, incluir_encerrados=True)) == 1


def test_favoritos_ordenados_por_urgencia(base):
    base.salvar_concursos("bahia", [
        _concurso("Fecha depois", dias=40),
        _concurso("Fecha logo", dias=2),
    ])
    for c in base.buscar_concursos(["bahia"]):
        if c["titulo"] in ("Fecha depois", "Fecha logo"):
            base.favoritar(1, c["id"])

    assert [c["titulo"] for c in base.listar_favoritos(1)] == ["Fecha logo", "Fecha depois"]


def test_favorito_de_um_nao_vaza_para_outro(base):
    base.adicionar_usuario(2, "Outro")
    cid = base.buscar_concursos(["bahia"])[0]["id"]
    base.favoritar(1, cid)

    assert len(base.listar_favoritos(1)) == 1
    assert base.listar_favoritos(2) == []


def test_remover_usuario_leva_favoritos_e_palavras(base):
    cid = base.buscar_concursos(["bahia"])[0]["id"]
    base.favoritar(1, cid)
    base.atualizar_palavras_usuario(1, ["medico"])

    base.remover_usuario(1)

    assert base.listar_favoritos(1) == []
    assert base.obter_palavras_usuario(1) == []


# --------------------------------------------------------------------------- #
# Teclado
# --------------------------------------------------------------------------- #

def test_um_botao_por_concurso_da_mensagem():
    concursos = [{"id": i, "titulo": f"Concurso {i}"} for i in range(3)]
    teclado = teclado_favoritar(concursos, [0, 1, 2])

    assert len(teclado.inline_keyboard) == 3
    assert teclado.inline_keyboard[0][0].callback_data == "fav_0"


def test_botao_nao_estoura_o_limite_de_callback_data():
    """callback_data tem teto de 64 bytes na API."""
    concursos = [{"id": 999999, "titulo": "T" * 200}]
    botao = teclado_favoritar(concursos, [999999]).inline_keyboard[0][0]

    assert len(botao.callback_data.encode()) <= 64
    assert len(botao.text) < 40


def test_max_itens_limita_a_parede_de_botoes():
    concursos = [{"id": i, "titulo": f"C{i}", "inscricoes_ate": "01/01/2030"}
                 for i in range(12)]
    grupos = list(agrupar_em_mensagens(concursos, max_itens=MAX_ITENS_COM_BOTAO))

    assert all(len(ids) <= MAX_ITENS_COM_BOTAO for _, ids in grupos)
    assert sum(len(ids) for _, ids in grupos) == 12
