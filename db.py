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
        inscricoes_ate TEXT,
        vagas TEXT,
        salario_max TEXT,
        nivel TEXT, 
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

def criar_tabela_user_concursos_enviados():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_concursos_enviados (
            user_id INTEGER,
            concurso_id INTEGER,
            PRIMARY KEY (user_id, concurso_id),
            FOREIGN KEY (user_id) REFERENCES users (chat_id) ON DELETE CASCADE,
            FOREIGN KEY (concurso_id) REFERENCES concursos (id) ON DELETE CASCADE
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

def atualizar_uf_usuario(user_id: int, ufs: list[str]):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM user_ufs WHERE user_id = ?", (user_id,))

    for uf in ufs:
        cursor.execute(
            "INSERT INTO user_ufs (user_id, uf) VALUES (?, ?)",
            (user_id, uf)  
        )

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

    return [row[0] for row in rows]

from datetime import datetime

def adicionar_concurso(
    titulo: str,
    link: str,
    inscricoes_ate: str,
    vagas: str,
    salario_max: str,
    nivel: str,
    estado: str
) -> int:

    try:
        data_inscricao = datetime.strptime(inscricoes_ate, "%d/%m/%Y")  
        if data_inscricao < datetime.now():  
            return None  
    except ValueError:
        return None 

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO concursos 
            (titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado))

        concurso_id = cursor.lastrowid
        conn.commit()
        return concurso_id
    except sqlite3.IntegrityError:
        cursor.execute("SELECT id FROM concursos WHERE titulo = ?", (titulo,))
        row = cursor.fetchone()
        return row[0] if row else None  
    finally:
        conn.close()




def adicionar_concurso_enviado(user_id: int, concurso_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_concursos_enviados (user_id, concurso_id)
        VALUES (?, ?)
    """, (user_id, concurso_id))
    conn.commit()
    conn.close()

def listar_concursos() -> list[dict]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM concursos
    """)
    rows = cursor.fetchall()
    conn.close()

    return [{
        "id": row[0],
        "titulo": row[1],
        "link": row[2],
        "data": row[3],
        "vagas": row[4],
        "cargos": row[5],
        "escolaridade": row[6],
        "estado": row[7]
    } for row in rows]

def concurso_ja_enviado(user_id: int, concurso_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM user_concursos_enviados
        WHERE user_id = ? AND concurso_id = ?
    """, (user_id, concurso_id))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

async def listar_usuarios():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT chat_id FROM users")
    usuarios = cursor.fetchall()

    conn.close()

    
    return [usuario[0] for usuario in usuarios]



def adicionar_usuario(chat_id: int, nome: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (chat_id, nome)
        VALUES (?, ?)
    """, (chat_id, nome))
    conn.commit()
    conn.close()    


def usuario_ja_registrado(chat_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE chat_id = ?", (chat_id,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None


def criar_indice_user_concursos_enviados():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_concurso
    ON user_concursos_enviados(user_id, concurso_id);
    """)

    conn.commit()
    conn.close()

def buscar_concursos_por_ufs(ufs):
    placeholders = ",".join("?" for _ in ufs)

    query = f"""
        SELECT id, titulo, link, inscricoes_ate, vagas, salario_max, nivel
        FROM concursos
        WHERE estado IN ({placeholders})
          AND date(substr(inscricoes_ate, 7, 4) || '-' ||
                   substr(inscricoes_ate, 4, 2) || '-' ||
                   substr(inscricoes_ate, 1, 2)) >= date('now')
    """

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, ufs)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "titulo": r[1],
            "link": r[2],
            "inscricoes_ate": r[3],
            "vagas": r[4],
            "salario_max": r[5],
            "nivel": r[6]
        }
        for r in rows
    ]


def buscar_concursos_filtrados(ufs, salario=None, nivel=None, vagas=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if salario is not None and not isinstance(salario, int):
        print("Erro: 'salario' deve ser um número inteiro ou None.")
        return []

    if nivel is not None and not isinstance(nivel, str):
        print("Erro: 'nivel' deve ser uma string ou None.")
        return []

    if vagas is not None and not isinstance(vagas, int):
        print("Erro: 'vagas' deve ser um número inteiro ou None.")
        return []

    if not ufs:
        print("Nenhum estado registrado. Retornando lista vazia.")
        return []   

    query = """
        SELECT id, titulo, link, inscricoes_ate, vagas, salario_max, nivel, estado
        FROM concursos
        WHERE estado IN ({})
    """.format(",".join("?" * len(ufs)))  

    params = list(ufs)

    if salario is not None:
        query += " AND CAST(REPLACE(REPLACE(REPLACE(salario_max, 'R$', ''), '.', ''), ',', '.') AS DECIMAL) >= ?"
        params.append(salario) 

    if nivel is not None:
        query += " AND LOWER(nivel) LIKE LOWER(?)"
        params.append(f"%{nivel}%")  

    if vagas is not None:
        query += " AND vagas >= ?"
        params.append(vagas)

    query += " ORDER BY CAST(salario_max AS INTEGER) DESC"

    print(f"Executando query: {query}")
    print(f"Parâmetros: {params}")

    try:
        cursor.execute(query, params)
        print(f'query de salario: {query}')
        rows = cursor.fetchall()
        
        print(f"Resultados encontrados: {rows}")
    except sqlite3.Error as e:
        print(f"Erro ao executar a query: {e}")
        return []  

    conn.close()

    if not rows:
        print("Nenhum concurso encontrado com os filtros aplicados.")

    return [
        {
            "id": r[0],
            "titulo": r[1],
            "link": r[2],
            "inscricoes_ate": r[3],
            "vagas": r[4],
            "salario_max": r[5],
            "nivel": r[6],
            "estado": r[7],
        }
        for r in rows
    ]


def atualizar_filtros(user_id, salario=None, nivel=None, vagas=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if salario is None and nivel is None and vagas is None:
        cursor.execute("""
            UPDATE users 
            SET salario_min = NULL, nivel = NULL, vagas_min = NULL
            WHERE chat_id = ?
        """, (user_id,))
    else:
        if salario is not None:
            cursor.execute("""
                UPDATE users 
                SET salario_min = ? 
                WHERE chat_id = ?
            """, (salario, user_id))

        if nivel is not None:
            cursor.execute("""
                UPDATE users 
                SET nivel = ? 
                WHERE chat_id = ?
            """, (nivel, user_id))

        if vagas is not None:
            cursor.execute("""
                UPDATE users 
                SET vagas_min = ? 
                WHERE chat_id = ?
            """, (vagas, user_id))

    conn.commit()
    conn.close()


def obter_filtros(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT salario_min, nivel, vagas_min
        FROM users
        WHERE chat_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row if row else (None, None, None)  