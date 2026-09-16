# database/db.py demo
import sqlite3

def init_db():
    conn = sqlite3.connect("argos.db")
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT,
        descripcion TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def guardar_evento(tipo, descripcion):
    conn = sqlite3.connect("argos.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO eventos (tipo, descripcion)
    VALUES (?, ?)
    """, (tipo, descripcion))

    conn.commit()
    conn.close()

init_db()