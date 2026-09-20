from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import config
import db

SP = ZoneInfo("America/Sao_Paulo")

# 20/09/2026 23:30 em Brasília = 21/09/2026 02:30 em UTC.
# É a janela em que o dia já virou em UTC mas não no Brasil.
INSTANTE_CRITICO = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)


@pytest.fixture
def relogio_congelado(monkeypatch):
    """Congela o relógio no instante crítico, preservando o resto do datetime."""

    class _Congelado(datetime):
        @classmethod
        def now(cls, tz=None):
            return INSTANTE_CRITICO.astimezone(tz) if tz else INSTANTE_CRITICO

    monkeypatch.setattr(db, "datetime", _Congelado)
    return _Congelado


def _concurso(titulo, iso):
    """Grava direto, sem passar pelo parse, para fixar a data exata."""
    return {
        "titulo": titulo,
        "link": "https://exemplo",
        "inscricoes_ate": datetime.fromisoformat(iso).strftime("%d/%m/%Y"),
        "vagas": "10",
        "salario_max": "R$ 5.000,00",
        "nivel": "Superior",
    }


def test_hoje_usa_o_fuso_do_brasil_nao_o_do_servidor(relogio_congelado):
    """Às 23h30 de Brasília ainda é dia 20, mesmo que em UTC já seja 21."""
    assert INSTANTE_CRITICO.date().isoformat() == "2026-09-21"   # em UTC
    assert db.hoje() == "2026-09-20"                             # no Brasil


def test_concurso_que_encerra_hoje_sobrevive_a_janela_critica(banco, relogio_congelado):
    """Regressão do bug de fuso.

    Com `date('now','localtime')` num servidor em UTC, este concurso sumia
    das 21h às 23h59 de Brasília — justamente a última chance de se inscrever,
    e sem ninguém perceber, porque quem não vê não reclama.
    """
    banco.salvar_concursos("bahia", [
        _concurso("Encerra hoje", "2026-09-20"),
        _concurso("Encerra amanha", "2026-09-21"),
        _concurso("Encerrou ontem", "2026-09-19"),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"])}
    assert titulos == {"Encerra hoje", "Encerra amanha"}


def test_o_que_ja_encerrou_continua_fora(banco, relogio_congelado):
    banco.salvar_concursos("bahia", [_concurso("Encerrou ontem", "2026-09-19")])
    assert banco.buscar_concursos(["bahia"]) == []


def test_a_query_usa_o_relogio_do_python_nao_o_do_sqlite(banco, monkeypatch):
    """Prova que o corte de data não vem mais de `date('now')` no SQL.

    O relógio é congelado num futuro distante. Um concurso encerrado em
    relação a essa data, mas ainda aberto em relação à data real da máquina,
    precisa ficar de fora. Com `date('now','localtime')` o SQLite usaria o
    relógio real e o incluiria — este teste falha no código anterior.
    """
    futuro = datetime(2027, 3, 15, 12, 0, tzinfo=timezone.utc)

    class _Congelado(datetime):
        @classmethod
        def now(cls, tz=None):
            return futuro.astimezone(tz) if tz else futuro

    monkeypatch.setattr(db, "datetime", _Congelado)

    banco.salvar_concursos("bahia", [
        _concurso("Encerrou antes do congelado", "2027-03-10"),
        _concurso("Ainda aberto no congelado", "2027-03-20"),
    ])

    titulos = {c["titulo"] for c in banco.buscar_concursos(["bahia"])}
    assert titulos == {"Ainda aberto no congelado"}


def test_data_independe_do_tz_do_processo(monkeypatch, relogio_congelado):
    """O resultado não pode mudar com o TZ do ambiente — é o ponto da correção."""
    resultados = set()
    for tz in ("UTC", "America/Sao_Paulo", "Asia/Tokyo", "America/New_York"):
        monkeypatch.setenv("TZ", tz)
        resultados.add(db.hoje())

    assert resultados == {"2026-09-20"}


# --------------------------------------------------------------------------- #
# Configuração do fuso
# --------------------------------------------------------------------------- #

def test_padrao_e_sao_paulo(monkeypatch):
    monkeypatch.delenv("TIMEZONE", raising=False)
    assert config._fuso() == SP


def test_fuso_configuravel(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "America/Manaus")
    assert config._fuso() == ZoneInfo("America/Manaus")


def test_fuso_invalido_cai_para_utc_menos_3(monkeypatch, caplog):
    """Sem tzdata (imagem Docker slim) o ZoneInfo falha; degradar > derrubar."""
    monkeypatch.setenv("TIMEZONE", "Fuso/Inexistente")

    with caplog.at_level("ERROR"):
        fuso = config._fuso()

    assert fuso.utcoffset(None) == timedelta(hours=-3)
    assert any("tzdata" in r.message for r in caplog.records)


def test_offset_de_fallback_bate_com_sao_paulo(relogio_congelado):
    """O Brasil não tem horário de verão desde 2019, então -3 fixo equivale."""
    fixo = timezone(timedelta(hours=-3))
    assert INSTANTE_CRITICO.astimezone(fixo).date() == \
           INSTANTE_CRITICO.astimezone(SP).date()
