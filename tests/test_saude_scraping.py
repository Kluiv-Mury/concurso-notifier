import pytest

from bot.jobs import LIMIAR_ESTADOS_SAUDAVEIS, ResumoColeta


def test_ciclo_saudavel_nao_acusa_nada():
    resumo = ResumoColeta(com_dados=25, vazios=2, coletados=800)
    assert resumo.diagnostico() is None


def test_estado_pequeno_vazio_e_normal():
    """Roraima e Sergipe passam dias sem concurso aberto; não é defeito."""
    resumo = ResumoColeta(com_dados=22, vazios=5, coletados=700)
    assert resumo.diagnostico() is None


def test_paginas_carregam_mas_nada_e_extraido_aponta_o_parser():
    """A falha mais provável e mais difícil de notar: layout da origem mudou.

    O site responde 200 e o parser não reconhece mais nada — indistinguível,
    no log antigo, de um dia sem concurso aberto.
    """
    resumo = ResumoColeta(vazios=27)
    problema = resumo.diagnostico()

    assert problema is not None
    assert "layout" in problema.lower()
    assert "tbl-conc" in problema  # aponta o seletor a revisar


def test_nenhuma_pagina_carrega_aponta_rede_ou_bloqueio():
    resumo = ResumoColeta(inacessiveis=27)
    problema = resumo.diagnostico()

    assert problema is not None
    assert "layout" not in problema.lower()
    assert "bloquead" in problema.lower() or "rede" in problema.lower()


def test_degradacao_parcial_e_acusada():
    """Metade dos estados falhando não pode passar por ciclo normal."""
    resumo = ResumoColeta(com_dados=5, vazios=20, inacessiveis=2, coletados=30)
    problema = resumo.diagnostico()

    assert problema is not None
    assert "5 de 27" in problema


def test_limiar_e_a_fronteira_entre_saudavel_e_degradado():
    visitados = 20
    limite = int(visitados * LIMIAR_ESTADOS_SAUDAVEIS)

    ok = ResumoColeta(com_dados=limite + 1, vazios=visitados - limite - 1)
    ruim = ResumoColeta(com_dados=limite - 1, vazios=visitados - limite + 1)

    assert ok.diagnostico() is None
    assert ruim.diagnostico() is not None


def test_ciclo_que_nao_visitou_nada():
    assert ResumoColeta().diagnostico() is not None


@pytest.mark.parametrize("resumo,esperado", [
    (ResumoColeta(com_dados=10, vazios=5, inacessiveis=2), 17),
    (ResumoColeta(), 0),
])
def test_visitados_soma_os_tres_desfechos(resumo, esperado):
    assert resumo.visitados == esperado


# --------------------------------------------------------------------------- #
# Leitura do ADMIN_CHAT_ID
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("valor,esperado", [
    ("123456", 123456),
    ("  123456  ", 123456),
    ("-100200300", -100200300),   # grupos têm id negativo
])
def test_admin_chat_id_valido(monkeypatch, valor, esperado):
    import config
    monkeypatch.setenv("ADMIN_CHAT_ID", valor)
    assert config._admin_chat_id() == esperado


def test_admin_nao_configurado_e_silencioso(monkeypatch, caplog):
    """Não configurar é escolha legítima: não pode virar warning todo boot."""
    import config
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)

    with caplog.at_level("WARNING"):
        assert config._admin_chat_id() is None
    assert caplog.records == []


def test_admin_ilegivel_avisa(monkeypatch, caplog):
    import config
    monkeypatch.setenv("ADMIN_CHAT_ID", "meu-chat")

    with caplog.at_level("WARNING"):
        assert config._admin_chat_id() is None
    assert any("ADMIN_CHAT_ID" in r.message for r in caplog.records)
