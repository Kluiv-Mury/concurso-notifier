from bot.formatacao import (
    LIMITE_MENSAGEM,
    agrupar_em_mensagens,
    formatar_concurso,
    formatar_ufs,
)


def _concurso(**extra):
    base = {
        "id": 1,
        "titulo": "Concurso X",
        "link": "https://exemplo/x",
        "inscricoes_ate": "13/02/2026",
        "vagas": "49",
        "salario_max": "R$ 13.288,85",
        "nivel": "Superior",
        "estado": "bahia",
    }
    return base | extra


def test_escapa_html_do_titulo():
    """Título com & ou < derruba a mensagem inteira no parse_mode=HTML."""
    texto = formatar_concurso(_concurso(titulo="Saúde & Educação <SP>"))

    assert "Saúde &amp; Educação &lt;SP&gt;" in texto
    assert "<SP>" not in texto


def test_campos_vazios_viram_texto_legivel():
    texto = formatar_concurso(_concurso(salario_max="-", vagas="", nivel=None))
    assert texto.count("não informado") == 3


def test_mostra_a_uf_do_concurso():
    assert "(BA)" in formatar_concurso(_concurso())


def test_sem_link_nao_deixa_linha_solta():
    assert "🔗" not in formatar_concurso(_concurso(link=""))


def test_agrupa_respeitando_o_limite_do_telegram():
    concursos = [_concurso(id=i, titulo=f"Concurso {i}") for i in range(60)]
    mensagens = list(agrupar_em_mensagens(concursos))

    assert len(mensagens) > 1  # precisa quebrar, senão estoura a API
    assert all(len(texto) <= LIMITE_MENSAGEM + 200 for texto, _ in mensagens)


def test_ids_acompanham_a_mensagem_em_que_saem():
    """Quem envia só marca como entregue os ids da mensagem que deu certo."""
    concursos = [_concurso(id=i, titulo=f"Concurso {i}") for i in range(60)]
    mensagens = list(agrupar_em_mensagens(concursos))

    ids_por_mensagem = [ids for _, ids in mensagens]
    todos = [i for ids in ids_por_mensagem for i in ids]

    assert todos == list(range(60))
    for texto, ids in mensagens:
        for i in ids:
            assert f"Concurso {i}</b>" in texto


def test_lista_vazia_nao_gera_mensagem():
    assert list(agrupar_em_mensagens([])) == []


def test_formatar_ufs_converte_slug_em_sigla():
    assert formatar_ufs(["bahia", "sao-paulo"]) == "BA, SP"
