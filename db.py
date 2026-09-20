"""Camada de acesso ao SQLite.

Toda função abre a conexão pelo helper `conectar()`, que garante commit,
rollback em erro e `PRAGMA foreign_keys`. O esquema é versionado em
`schema_version` e migrado de forma idempotente por `criar_tabelas()`.

Colunas normalizadas
--------------------
O site de origem entrega tudo como texto ("R$ 13.288,85", "13/02/2026", "-").
Guardamos o texto original para exibir e uma versão normalizada para filtrar
e ordenar:

    inscricoes_ate  ->  inscricoes_ate_iso  (YYYY-MM-DD, ordenável)
    salario_max     ->  salario_num         (REAL, NULL se desconhecido)
    vagas           ->  vagas_num           (INTEGER, NULL se desconhecido)

Sem isso os filtros mentem: `CAST('R$ 13.288,85' AS INTEGER)` é 0 e, na ordem
de tipos do SQLite, o texto '-' é maior que qualquer inteiro.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from config import logger

# Caminho absoluto: relativo ao CWD, rodar o bot de outra pasta criaria
# um banco vazio novo sem nenhum aviso.
DB_FILE = str(Path(__file__).resolve().parent / "concursos.db")

SCHEMA_VERSION = 2


def _prazo_aberto(alias: str = "") -> str:
    """Condição SQL: concurso só interessa enquanto a inscrição estiver aberta."""
    coluna = f"{alias}.inscricoes_ate_iso" if alias else "inscricoes_ate_iso"
    return f"{coluna} IS NOT NULL AND {coluna} >= date('now', 'localtime')"


# --------------------------------------------------------------------------- #
# Conexão
# --------------------------------------------------------------------------- #

@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Conexão com commit/rollback automático e linhas acessíveis por nome."""
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Recomendado com WAL: no pior caso (queda de energia) perdem-se as
    # últimas transações, mas o arquivo nunca corrompe. `synchronous` é por
    # conexão, diferente de `journal_mode`, que fica gravado no banco.
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Normalização dos campos vindos do scraping
# --------------------------------------------------------------------------- #

_RE_NUMERO = re.compile(r"\d[\d.,]*")


def parse_data(valor: Optional[str]) -> Optional[str]:
    """'13/02/2026' -> '2026-02-13'. None se não for uma data dd/mm/aaaa."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def parse_salario(valor: Optional[str]) -> Optional[float]:
    """'R$ 13.288,85' -> 13288.85. Em faixas, devolve o maior valor."""
    if not valor:
        return None
    maiores = []
    for bruto in _RE_NUMERO.findall(valor):
        # Formato brasileiro: '.' é separador de milhar, ',' é decimal.
        try:
            maiores.append(float(bruto.replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return max(maiores) if maiores else None


def parse_vagas(valor: Optional[str]) -> Optional[int]:
    """'49' -> 49, '1.200' -> 1200, '-' -> None (desconhecido, não zero)."""
    if valor is None:
        return None
    if isinstance(valor, int):
        return valor
    achado = _RE_NUMERO.search(str(valor))
    if not achado:
        return None
    try:
        return int(achado.group().replace(".", "").split(",")[0])
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Esquema e migrações
# --------------------------------------------------------------------------- #

def _versao_esquema(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (versao INTEGER NOT NULL)")
    linha = conn.execute("SELECT versao FROM schema_version").fetchone()
    if linha is None:
        # Banco pré-existente (sem controle de versão) ou recém-criado.
        tabelas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='concursos'"
        ).fetchone()
        versao = 1 if tabelas else 0
        conn.execute("INSERT INTO schema_version (versao) VALUES (?)", (versao,))
        return versao
    return linha[0]


def _colunas(conn: sqlite3.Connection, tabela: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabela})")}


# DDL da tabela de concursos, parametrizado pelo nome porque a migração
# precisa materializá-la com um nome temporário antes de trocar a antiga.
_DDL_CONCURSOS = """
        CREATE TABLE IF NOT EXISTS {tabela} (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo             TEXT NOT NULL,
            link               TEXT,
            inscricoes_ate     TEXT,
            vagas              TEXT,
            salario_max        TEXT,
            nivel              TEXT,
            estado             TEXT NOT NULL,
            inscricoes_ate_iso TEXT,
            salario_num        REAL,
            vagas_num          INTEGER,
            atualizado_em      DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (titulo, estado)
        )
"""

_DDL_RESTANTE = (
    """
        CREATE TABLE IF NOT EXISTS users (
            chat_id             INTEGER PRIMARY KEY,
            nome                TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            salario_min         INTEGER,
            nivel               TEXT,
            vagas_min           INTEGER,
            notificacoes_ativas INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS user_ufs (
            user_id INTEGER NOT NULL,
            uf      TEXT NOT NULL,
            PRIMARY KEY (user_id, uf),
            FOREIGN KEY (user_id) REFERENCES users (chat_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_concursos_enviados (
            user_id     INTEGER NOT NULL,
            concurso_id INTEGER NOT NULL,
            enviado_em  DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, concurso_id),
            FOREIGN KEY (user_id) REFERENCES users (chat_id) ON DELETE CASCADE,
            FOREIGN KEY (concurso_id) REFERENCES concursos (id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_user_concurso
            ON user_concursos_enviados (user_id, concurso_id);
        CREATE INDEX IF NOT EXISTS idx_concursos_estado_prazo
            ON concursos (estado, inscricoes_ate_iso);
        """
    )


def _executar_ddl(conn: sqlite3.Connection, script: str) -> None:
    """Executa um script DDL comando a comando.

    `executescript` daria um COMMIT implícito antes de rodar, encerrando a
    transação da migração no meio do caminho.
    """
    for comando in filter(None, (c.strip() for c in script.split(";"))):
        conn.execute(comando)


def _criar_esquema_base(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL_CONCURSOS.format(tabela="concursos"))
    _executar_ddl(conn, _DDL_RESTANTE)


def _migrar_para_v2(conn: sqlite3.Connection) -> None:
    """Adiciona as colunas de filtro e troca UNIQUE(titulo) por UNIQUE(titulo, estado).

    O UNIQUE antigo era global: um concurso nacional listado nos 27 estados
    ficava gravado só no primeiro que o scraping visitasse, e usuários dos
    outros 26 nunca o viam.
    """
    logger.info("Migrando banco para o esquema v2...")

    # 1) Colunas que o código já usava mas nenhuma migração criava.
    cols_users = _colunas(conn, "users")
    for coluna, definicao in (
        ("salario_min", "INTEGER"),
        ("nivel", "TEXT"),
        ("vagas_min", "INTEGER"),
        ("notificacoes_ativas", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if coluna not in cols_users:
            conn.execute(f"ALTER TABLE users ADD COLUMN {coluna} {definicao}")
            logger.info("users.%s criada.", coluna)

    # 2) Reconstrói `concursos` com as colunas normalizadas e o UNIQUE correto.
    #    `UNIQUE` de coluna vira um sqlite_autoindex, que não dá para dropar
    #    sem recriar a tabela.
    #
    #    A ordem importa: criar a nova com nome temporário, copiar, dropar a
    #    antiga e só então renomear. Renomear `concursos` primeiro faria o
    #    SQLite reescrever o `REFERENCES concursos` de
    #    `user_concursos_enviados` para apontar à tabela temporária, e o DROP
    #    seguinte levaria junto todo o histórico de envios.
    _executar_ddl(conn, "DROP TABLE IF EXISTS concursos_nova")
    conn.execute(_DDL_CONCURSOS.format(tabela="concursos_nova"))

    conn.execute(
        """
        INSERT OR IGNORE INTO concursos_nova
            (id, titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado)
        SELECT id, titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado
        FROM concursos
        """
    )
    copiados = conn.execute("SELECT COUNT(*) FROM concursos_nova").fetchone()[0]

    conn.execute("DROP TABLE concursos")
    conn.execute("ALTER TABLE concursos_nova RENAME TO concursos")
    _criar_esquema_base(conn)
    logger.info("Tabela concursos reconstruída: %d registros preservados.", copiados)

    # 3) Backfill dos campos normalizados a partir do texto já gravado.
    linhas = conn.execute(
        "SELECT id, inscricoes_ate, salario_max, vagas FROM concursos"
    ).fetchall()
    conn.executemany(
        """
        UPDATE concursos
           SET inscricoes_ate_iso = ?, salario_num = ?, vagas_num = ?
         WHERE id = ?
        """,
        [
            (
                parse_data(r["inscricoes_ate"]),
                parse_salario(r["salario_max"]),
                parse_vagas(r["vagas"]),
                r["id"],
            )
            for r in linhas
        ],
    )
    logger.info("Backfill concluído em %d concursos.", len(linhas))

    # 4) Tabela órfã de uma versão antiga do projeto, sem uso no código.
    conn.execute("DROP TABLE IF EXISTS user_concursos")


def criar_tabelas() -> None:
    """Cria o esquema e aplica migrações pendentes. Idempotente.

    Roda com `foreign_keys = OFF`, como manda a receita de rebuild de tabela
    do SQLite. Com as FKs ligadas, o `ALTER TABLE ... RENAME` reescreveria as
    cláusulas REFERENCES das outras tabelas para apontar para a tabela
    temporária, e o `DROP` seguinte apagaria em cascata todo o histórico de
    `user_concursos_enviados` — os usuários receberiam a base inteira de novo.
    """
    conn = sqlite3.connect(DB_FILE, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        # Impede que o RENAME final saia reescrevendo REFERENCES alheias.
        conn.execute("PRAGMA legacy_alter_table = ON")

        # WAL: leitor não bloqueia escritor nem vice-versa. No modo `delete`
        # (padrão), o job de scraping trancava o banco inteiro enquanto
        # gravava e um /todos simultâneo ficava esperando. É gravado dentro
        # do arquivo do banco, então basta aplicar uma vez — e precisa ser
        # fora de transação.
        modo = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if modo.lower() != "wal":
            logger.warning("journal_mode ficou em '%s' (WAL indisponível).", modo)

        conn.execute("BEGIN")
        try:
            versao = _versao_esquema(conn)

            if versao == 0:
                _criar_esquema_base(conn)
            elif versao < 2:
                _migrar_para_v2(conn)

            if versao < SCHEMA_VERSION:
                conn.execute("UPDATE schema_version SET versao = ?", (SCHEMA_VERSION,))
                logger.info("Esquema do banco em v%d.", SCHEMA_VERSION)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        violacoes = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violacoes:
            logger.error("Integridade referencial violada após migrar: %s", violacoes)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Usuários
# --------------------------------------------------------------------------- #

def adicionar_usuario(chat_id: int, nome: Optional[str]) -> None:
    with conectar() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (chat_id, nome) VALUES (?, ?)", (chat_id, nome)
        )


def usuario_ja_registrado(chat_id: int) -> bool:
    with conectar() as conn:
        return conn.execute(
            "SELECT 1 FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone() is not None


def listar_usuarios() -> list[int]:
    """Usuários com notificações ligadas e ao menos uma UF registrada."""
    with conectar() as conn:
        linhas = conn.execute(
            """
            SELECT DISTINCT u.chat_id
              FROM users u
              JOIN user_ufs uf ON uf.user_id = u.chat_id
             WHERE u.notificacoes_ativas = 1
            """
        ).fetchall()
    return [linha["chat_id"] for linha in linhas]


def atualizar_uf_usuario(user_id: int, ufs: Sequence[str]) -> None:
    with conectar() as conn:
        conn.execute("DELETE FROM user_ufs WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO user_ufs (user_id, uf) VALUES (?, ?)",
            [(user_id, uf) for uf in ufs],
        )


def obter_ufs_usuario(user_id: int) -> list[str]:
    with conectar() as conn:
        linhas = conn.execute(
            "SELECT uf FROM user_ufs WHERE user_id = ? ORDER BY uf", (user_id,)
        ).fetchall()
    return [linha["uf"] for linha in linhas]


def obter_filtros(user_id: int) -> tuple[Optional[int], Optional[str], Optional[int]]:
    with conectar() as conn:
        linha = conn.execute(
            "SELECT salario_min, nivel, vagas_min FROM users WHERE chat_id = ?",
            (user_id,),
        ).fetchone()
    if linha is None:
        return (None, None, None)
    return (linha["salario_min"], linha["nivel"], linha["vagas_min"])


def atualizar_filtros(
    user_id: int,
    salario: Optional[int] = None,
    nivel: Optional[str] = None,
    vagas: Optional[int] = None,
) -> None:
    """Grava os filtros informados. Sem nenhum argumento, zera os três."""
    with conectar() as conn:
        if salario is None and nivel is None and vagas is None:
            conn.execute(
                "UPDATE users SET salario_min = NULL, nivel = NULL, vagas_min = NULL"
                " WHERE chat_id = ?",
                (user_id,),
            )
            return

        campos, valores = [], []
        for coluna, valor in (
            ("salario_min", salario),
            ("nivel", nivel),
            ("vagas_min", vagas),
        ):
            if valor is not None:
                campos.append(f"{coluna} = ?")
                valores.append(valor)

        valores.append(user_id)
        conn.execute(
            f"UPDATE users SET {', '.join(campos)} WHERE chat_id = ?", valores
        )


def notificacoes_ativas(user_id: int) -> bool:
    with conectar() as conn:
        linha = conn.execute(
            "SELECT notificacoes_ativas FROM users WHERE chat_id = ?", (user_id,)
        ).fetchone()
    return True if linha is None else bool(linha["notificacoes_ativas"])


def atualizar_notificacoes_usuario(user_id: int, ativas: bool) -> None:
    with conectar() as conn:
        conn.execute(
            "UPDATE users SET notificacoes_ativas = ? WHERE chat_id = ?",
            (int(ativas), user_id),
        )


# --------------------------------------------------------------------------- #
# Concursos
# --------------------------------------------------------------------------- #

def salvar_concursos(estado: str, concursos: Iterable[dict]) -> int:
    """Insere ou atualiza os concursos de um estado. Devolve quantos eram novos.

    Atualizar importa: prazo prorrogado, vagas retificadas e salário corrigido
    acontecem o tempo todo e a versão anterior ignorava o registro existente.
    """
    linhas = []
    for c in concursos:
        titulo = (c.get("titulo") or "").strip()
        iso = parse_data(c.get("inscricoes_ate"))
        if not titulo or iso is None:
            # Sem título ou sem prazo utilizável não há como filtrar nem exibir.
            continue
        linhas.append(
            (
                titulo,
                c.get("link"),
                c.get("inscricoes_ate"),
                c.get("vagas"),
                c.get("salario_max"),
                c.get("nivel"),
                estado,
                iso,
                parse_salario(c.get("salario_max")),
                parse_vagas(c.get("vagas")),
            )
        )

    if not linhas:
        return 0

    with conectar() as conn:
        antes = conn.execute(
            "SELECT COUNT(*) AS n FROM concursos WHERE estado = ?", (estado,)
        ).fetchone()["n"]

        conn.executemany(
            """
            INSERT INTO concursos
                (titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado,
                 inscricoes_ate_iso, salario_num, vagas_num)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (titulo, estado) DO UPDATE SET
                link               = excluded.link,
                inscricoes_ate     = excluded.inscricoes_ate,
                vagas              = excluded.vagas,
                salario_max        = excluded.salario_max,
                nivel              = excluded.nivel,
                inscricoes_ate_iso = excluded.inscricoes_ate_iso,
                salario_num        = excluded.salario_num,
                vagas_num          = excluded.vagas_num,
                atualizado_em      = CURRENT_TIMESTAMP
            """,
            linhas,
        )

        depois = conn.execute(
            "SELECT COUNT(*) AS n FROM concursos WHERE estado = ?", (estado,)
        ).fetchone()["n"]

    return depois - antes


def buscar_concursos(
    ufs: Sequence[str],
    salario: Optional[int] = None,
    nivel: Optional[str] = None,
    vagas: Optional[int] = None,
    nao_enviados_para: Optional[int] = None,
    limite: Optional[int] = None,
) -> list[dict]:
    """Concursos com inscrição aberta nas UFs do usuário, aplicando os filtros.

    `nao_enviados_para` exclui, na própria query, o que aquele usuário já
    recebeu — antes isso era um SELECT por concurso, cada um abrindo sua
    própria conexão.
    """
    if not ufs:
        return []

    placeholders = ",".join("?" for _ in ufs)
    condicoes = [f"c.estado IN ({placeholders})", _prazo_aberto("c")]
    params: list = list(ufs)

    if salario is not None:
        condicoes.append("c.salario_num IS NOT NULL AND c.salario_num >= ?")
        params.append(salario)

    if nivel is not None:
        condicoes.append("c.nivel IS NOT NULL AND LOWER(c.nivel) LIKE LOWER(?)")
        params.append(f"%{nivel}%")

    if vagas is not None:
        # `vagas_num IS NULL` = quantidade não divulgada. Antes essas linhas
        # passavam em qualquer mínimo porque o texto '-' > inteiro no SQLite.
        condicoes.append("c.vagas_num IS NOT NULL AND c.vagas_num >= ?")
        params.append(vagas)

    if nao_enviados_para is not None:
        condicoes.append(
            "NOT EXISTS (SELECT 1 FROM user_concursos_enviados e"
            " WHERE e.user_id = ? AND e.concurso_id = c.id)"
        )
        params.append(nao_enviados_para)

    query = f"""
        SELECT c.id, c.titulo, c.link, c.inscricoes_ate, c.vagas,
               c.salario_max, c.nivel, c.estado
          FROM concursos c
         WHERE {' AND '.join(condicoes)}
         ORDER BY c.salario_num IS NULL, c.salario_num DESC, c.inscricoes_ate_iso ASC
    """
    if limite is not None:
        query += " LIMIT ?"
        params.append(limite)

    with conectar() as conn:
        linhas = conn.execute(query, params).fetchall()

    return [dict(linha) for linha in linhas]


# --------------------------------------------------------------------------- #
# Backup
# --------------------------------------------------------------------------- #

MAX_BACKUPS = 7
_PADRAO_BACKUP = "concursos-*.db"


def _dir_backup() -> Path:
    """Resolvido em tempo de chamada, para acompanhar o DB_FILE em uso."""
    return Path(DB_FILE).resolve().parent / "backups"


def _podar_backups(manter: int) -> int:
    """Apaga os backups mais antigos, preservando os `manter` mais recentes."""
    if manter < 1:
        return 0
    # O carimbo de data no nome faz a ordem alfabética ser a cronológica.
    antigos = sorted(_dir_backup().glob(_PADRAO_BACKUP))[:-manter]
    for arquivo in antigos:
        arquivo.unlink()
    return len(antigos)


def fazer_backup(manter: int = MAX_BACKUPS) -> Path:
    """Cópia consistente do banco, com o bot rodando. Devolve o caminho.

    Usa a API `Connection.backup()` do SQLite, não uma cópia do arquivo:
    copiar no meio de uma escrita captura um estado inconsistente, e em WAL
    ainda deixaria de fora o que está no `-wal` e não foi para o banco.
    """
    destino_dir = _dir_backup()
    destino_dir.mkdir(parents=True, exist_ok=True)

    # O carimbo tem resolução de segundo: duas chamadas dentro do mesmo
    # segundo colidiriam e a segunda sobrescreveria a primeira sem avisar —
    # num backup, perder silenciosamente é o pior desfecho possível.
    carimbo = f"{datetime.now():%Y%m%d-%H%M%S}"
    destino = destino_dir / f"concursos-{carimbo}.db"
    sufixo = 1
    while destino.exists():
        destino = destino_dir / f"concursos-{carimbo}-{sufixo}.db"
        sufixo += 1

    origem = sqlite3.connect(DB_FILE, timeout=30)
    try:
        copia = sqlite3.connect(destino)
        try:
            origem.backup(copia)
        finally:
            copia.close()
    finally:
        origem.close()

    removidos = _podar_backups(manter)
    logger.info(
        "Backup em %s (%.1f KB); %d antigo(s) removido(s).",
        destino.name, destino.stat().st_size / 1024, removidos,
    )
    return destino


def marcar_enviados(user_id: int, concurso_ids: Sequence[int]) -> None:
    """Registra em lote o que já foi entregue — chamar só após o envio dar certo."""
    if not concurso_ids:
        return
    with conectar() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO user_concursos_enviados (user_id, concurso_id)"
            " VALUES (?, ?)",
            [(user_id, cid) for cid in concurso_ids],
        )
