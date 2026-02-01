import sqlite3

DB_FILE = "concursos.db"

def criar_tabela_concurso():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS concursos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT UNIQUE,
        link TEXT,
        data TEXT,
        vagas TEXT,
        cargos TEXT,
        escolaridade TEXT,
        estado TEXT
    )
    """)
    conn.commit()
    conn.close()


def criar_tabela_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        nome TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def criar_tabela_user_ufs():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_ufs (
        user_id INTEGER,
        uf TEXT,
        PRIMARY KEY (user_id, uf)
    )
    """)
    conn.commit()
    conn.close()


def adicionar_uf_usuario(user_id: int, uf: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_ufs (user_id, uf)
        VALUES (?, ?)
    """, (user_id, uf.upper()))
    conn.commit()
    conn.close()

def remover_uf_usuario(user_id: int, uf: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM user_ufs
        WHERE user_id = ? AND uf = ?
    """, (user_id, uf.upper()))
    conn.commit()
    conn.close()

def obter_ufs_usuario(user_id: int) -> list[str]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uf FROM user_ufs WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]




def criar_tabela_user_concursos():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_concursos (
        user_id INTEGER,
        concurso_id INTEGER,
        enviado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, concurso_id)
    )
    """)
    conn.commit()
    conn.close()


def adicionar_usuario(chat_id: int, nome: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (chat_id, nome)
            VALUES (?, ?)
        """, (chat_id, nome))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def listar_usuarios() -> list[int]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def usuario_ja_recebeu(user_id: int, concurso_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM user_concursos
        WHERE user_id = ? AND concurso_id = ?
    """, (user_id, concurso_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def marcar_concurso_enviado(user_id: int, concurso_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_concursos (user_id, concurso_id)
        VALUES (?, ?)
    """, (user_id, concurso_id))
    conn.commit()
    conn.close()



def adicionar_concurso(
    titulo: str,
    link: str,
    data: str,
    vagas: str,
    cargos: str,
    escolaridade: str,
    estado: str
) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO concursos 
            (titulo, link, data, vagas, cargos, escolaridade, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (titulo, link, data, vagas, cargos, escolaridade, estado))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def obter_id_concurso(titulo: str) -> int:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM concursos WHERE titulo = ?",
        (titulo,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# def obter_uf_prioridade(user_id: int) -> str:
#     conn = sqlite3.connect(DB_FILE)
#     cursor = conn.cursor()
#     cursor.execute(
#         "SELECT uf_prioridade FROM users WHERE chat_id = ?",
#         (user_id,)
#     )
#     row = cursor.fetchone()
#     return row[0] if row else "RJ"


# def atualizar_uf_prioridade(user_id: int, uf: str):
#     conn = sqlite3.connect(DB_FILE)
#     cursor = conn.cursor()
#     cursor.execute(
#         "UPDATE usuarios SET uf_prioridade = ? WHERE chat_id = ?",
#         (uf.upper(), user_id)
#     )
#     conn.commit()



# def atualizar_uf_usuario(user_id: int, ufs: list[str]):
#     conn = sqlite3.connect(DB_FILE)
#     cursor = conn.cursor()

#     uf_str = ",".join(sorted(set(ufs)))

#     cursor.execute(
#         "UPDATE users SET uf_prioridade = ? WHERE chat_id = ?",
#         (uf_str, user_id)
#     )

#     conn.commit()
#     conn.close()

# def obter_ufs_usuario(user_id: int) -> list[str]:
#     conn = sqlite3.connect(DB_FILE)
#     cursor = conn.cursor()

#     cursor.execute(
#         "SELECT uf_prioridade FROM users WHERE chat_id = ?",
#         (user_id,)
#     )

#     row = cursor.fetchone()
#     conn.close()

#     if not row or not row[0]:
#         return ["RJ"]

#     return [uf.strip().upper() for uf in row[0].split(",")]

def atualizar_uf_usuario(user_id: int, ufs: list[str]):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Remove os UFs antigos
    cursor.execute("DELETE FROM user_ufs WHERE user_id = ?", (user_id,))

    # Insere os novos UFs
    for uf in sorted(set(ufs)):
        cursor.execute(
            "INSERT INTO user_ufs (chat_id, uf) VALUES (?, ?)",
            (user_id, uf.upper())
        )

    conn.commit()
    conn.close()

def obter_ufs_usuario(user_id: int) -> list[str]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT uf FROM user_ufs WHERE user_id = ?",
        (user_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return ["RJ"]  # UF padrão caso não exista

    return [row[0].strip().upper() for row in rows]

def atualizar_uf_usuario(user_id: int, ufs: list[str]):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM user_ufs WHERE user_id = ?", (user_id,))
    for uf in ufs:
        cursor.execute(
            "INSERT INTO user_ufs (user_id, uf) VALUES (?, ?)",
            (user_id, uf.upper())
        )

    conn.commit()
    conn.close()

