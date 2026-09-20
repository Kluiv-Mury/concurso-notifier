from datetime import date, timedelta

import pytest

import db
from bot.formatacao import formatar_lembrete
from bot.jobs import DIAS_PARA_LEMBRAR
from config import SIGLAS_ESTADOS, SLUGS_COLETA, SLUG_NACIONAL, SLUG_PARA_SIGLA


def _concurso(titulo, dias, **extra):
    base = {
        "titulo": titulo,
        "link": f"https://exemplo/{titulo}",
        "inscricoes_ate": (date.today() + timedelta(days=dias)).strftime("%d/%m/%Y"),
        "vagas": "10",
        "salario_max": "R$ 5.000,00",
        "nivel": "Superior",
    }
    return base | extra


# --------------------------------------------------------------------------- #
# Concursos de alcance nacional
# --------------------------------------------------------------------------- #

def test_listagem_nacional_entra_na_coleta():
    """Sem isso os federais, geralmente os mais bem pagos, eram invisíveis."""
    assert SLUG_NACIONAL in SLUGS_COLETA
    assert len(SLUGS_COLETA) == len(SIGLAS_ESTADOS) + 1


def test_nacional_nao_vira_opcao_de_uf():
    """'brasil' não é estado: /uf BR não pode existir."""
    assert SLUG_NACIONAL not in SIGLAS_ESTADOS.values() or SLUG_NACIONAL == "brasil"
    assert "br" not in SIGLAS_ESTADOS


def test_usuario_ve_concurso_nacional_sem_registrar_nada(banco):
    """Concurso federal vale para todo mundo, esteja em que estado estiver."""
    banco.salvar_concursos("bahia", [_concurso("Só da Bahia", 30)])
    banco.salvar_concursos(SLUG_NACIONAL, [_concurso("TRF-5 Juiz Federal", 30)])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"])}
    assert titulos == {"Só da Bahia", "TRF-5 Juiz Federal"}


def test_nacional_aparece_para_qualquer_estado(banco):
    banco.salvar_concursos(SLUG_NACIONAL, [_concurso("TRANSPETRO", 30)])

    for uf in ("bahia", "sao-paulo", "roraima"):
        titulos = {c["titulo"] for c in banco.buscar_concursos([uf])}
        assert "TRANSPETRO" in titulos


def test_nacional_respeita_os_filtros(banco):
    """Ser nacional não é passe livre: os filtros do usuário continuam valendo."""
    banco.salvar_concursos(SLUG_NACIONAL, [
        _concurso("Federal alto", 30, salario_max="R$ 37.765,55"),
        _concurso("Federal baixo", 30, salario_max="R$ 2.000,00"),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"], salario=10000)}
    assert titulos == {"Federal alto"}


def test_nacional_tem_rotulo_proprio():
    assert SLUG_PARA_SIGLA[SLUG_NACIONAL] == "Nacional"


def test_rotulo_nacional_aparece_na_mensagem(banco):
    banco.salvar_concursos(SLUG_NACIONAL, [_concurso("TRF-5", 30)])
    concurso = banco.buscar_concursos(["bahia"])[0]

    assert "(Nacional)" in formatar_lembrete(concurso, 2)


# --------------------------------------------------------------------------- #
# Lembrete de prazo
# --------------------------------------------------------------------------- #

def _com_historico(banco, dias):
    """Usuário que já recebeu um concurso encerrando em `dias`."""
    banco.adicionar_usuario(1, "Fulano")
    banco.atualizar_uf_usuario(1, ["bahia"])
    banco.salvar_concursos("bahia", [_concurso("Edital antigo", dias)])
    ids = [c["id"] for c in banco.buscar_concursos(["bahia"])]
    banco.marcar_enviados(1, ids)
    return ids


def test_avisa_quando_o_prazo_esta_acabando(banco):
    _com_historico(banco, dias=2)
    encerrando = banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR)

    assert [c["titulo"] for c in encerrando] == ["Edital antigo"]


def test_nao_avisa_de_prazo_distante(banco):
    _com_historico(banco, dias=40)
    assert banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR) == []


def test_nao_avisa_do_que_ja_encerrou(banco):
    _com_historico(banco, dias=-1)
    assert banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR) == []


def test_nao_repete_o_mesmo_lembrete(banco):
    ids = _com_historico(banco, dias=2)

    assert len(banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR)) == 1
    banco.marcar_lembretes(1, ids)
    # Sem o registro, o aviso voltaria a cada ciclo até o prazo fechar.
    assert banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR) == []


def test_so_lembra_do_que_a_pessoa_recebeu(banco):
    """O que ela nunca viu chega pelo alerta normal, já com a data à vista."""
    banco.adicionar_usuario(1, "Fulano")
    banco.atualizar_uf_usuario(1, ["bahia"])
    banco.salvar_concursos("bahia", [_concurso("Nunca enviado", 2)])

    assert banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR) == []


def test_lembrete_de_um_usuario_nao_afeta_outro(banco):
    banco.adicionar_usuario(1, "Um")
    banco.adicionar_usuario(2, "Dois")
    banco.atualizar_uf_usuario(1, ["bahia"])
    banco.atualizar_uf_usuario(2, ["bahia"])
    banco.salvar_concursos("bahia", [_concurso("Edital", 2)])
    ids = [c["id"] for c in banco.buscar_concursos(["bahia"])]
    banco.marcar_enviados(1, ids)
    banco.marcar_enviados(2, ids)

    banco.marcar_lembretes(1, ids)

    assert banco.buscar_encerrando(1, DIAS_PARA_LEMBRAR) == []
    assert len(banco.buscar_encerrando(2, DIAS_PARA_LEMBRAR)) == 1


@pytest.mark.parametrize("dias,esperado", [
    (0, "encerra HOJE"),
    (1, "encerra AMANHÃ"),
    (3, "faltam 3 dias"),
])
def test_urgencia_na_frente_da_mensagem(dias, esperado):
    texto = formatar_lembrete({"titulo": "X", "inscricoes_ate": "01/01/2030"}, dias)
    assert esperado in texto
    assert texto.startswith("⏰")


def test_lembrete_escapa_html():
    texto = formatar_lembrete({"titulo": "Saúde & Educação <SP>"}, 2)
    assert "Saúde &amp; Educação &lt;SP&gt;" in texto


def test_dias_restantes(banco):
    hoje = date.today()
    assert banco.dias_restantes(hoje.isoformat()) == 0
    assert banco.dias_restantes((hoje + timedelta(days=5)).isoformat()) == 5
    assert banco.dias_restantes((hoje - timedelta(days=1)).isoformat()) == -1
    assert banco.dias_restantes(None) is None
    assert banco.dias_restantes("nao-e-data") is None


# --------------------------------------------------------------------------- #
# Migração v3
# --------------------------------------------------------------------------- #

def test_coluna_de_lembrete_existe(banco):
    with banco.conectar() as conn:
        colunas = {r["name"] for r in conn.execute(
            "PRAGMA table_info(user_concursos_enviados)"
        )}
    assert "lembrete_em" in colunas
    assert banco.SCHEMA_VERSION == 3
