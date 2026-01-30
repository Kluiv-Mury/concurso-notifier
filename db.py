import sqlite3

DB_FILE = "concursos.db"

def criar_tabela():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS concursos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT UNIQUE,
        link TEXT,
        data TEXT
    )
    """)
    conn.commit()
    conn.close()

def adicionar_concurso(titulo: str, link: str, data: str) -> bool:
    """Adiciona concurso, retorna True se foi adicionado, False se já existia"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO concursos (titulo, link, data) VALUES (?, ?, ?)",
                       (titulo, link, data))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Já existe
        return False
    finally:
        conn.close()
