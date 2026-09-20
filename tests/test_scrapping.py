from scrapping import _extrair_concursos

HTML = """
<table class="tbl-conc">
  <tr><th>Concurso</th><th>Inscrições</th><th>Vagas</th><th>Salário</th></tr>
  <tr>
    <td>
      <a href="https://exemplo/unirio"><span class="titulo">Concurso Unirio-RJ 2026</span></a>
      <span class="vagas ">Nível: Médio, Técnico e Superior</span>
    </td>
    <td>02/03/2026</td><td>49</td><td>R$ 13.288,85</td>
  </tr>
  <tr>
    <td><a href="https://exemplo/ghc"><span class="titulo">Concurso GHC-RS</span></a></td>
    <td>05/03/2026</td><td>-</td><td>-</td>
  </tr>
  <tr><td>linha malformada</td><td>x</td></tr>
</table>
"""


def test_extrai_as_linhas_validas():
    concursos = _extrair_concursos(HTML)

    # Cabeçalho e linha com menos de 4 colunas ficam de fora.
    assert len(concursos) == 2
    assert concursos[0] == {
        "titulo": "Concurso Unirio-RJ 2026",
        "link": "https://exemplo/unirio",
        "nivel": "Médio, Técnico e Superior",  # prefixo "Nível:" removido
        "inscricoes_ate": "02/03/2026",
        "vagas": "49",
        "salario_max": "R$ 13.288,85",
    }


def test_nivel_ausente_vira_none():
    assert _extrair_concursos(HTML)[1]["nivel"] is None


def test_html_sem_tabela():
    assert _extrair_concursos("<html><body>nada aqui</body></html>") == []
