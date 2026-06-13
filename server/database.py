"""
database.py — Persistência em SQLite (contas e personagens).

Todo acesso acontece na thread do event loop (operações são minúsculas),
então uma única conexão é suficiente. Senhas: sha256(salt + senha).
"""
import hashlib
import json
import secrets
import sqlite3

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    salt        TEXT NOT NULL,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS characters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    name        TEXT UNIQUE NOT NULL COLLATE NOCASE,
    level       INTEGER NOT NULL DEFAULT 1,
    exp         INTEGER NOT NULL DEFAULT 0,
    hp          INTEGER NOT NULL,
    maxhp       INTEGER NOT NULL,
    mp          INTEGER NOT NULL,
    maxmp       INTEGER NOT NULL,
    x           INTEGER NOT NULL,
    y           INTEGER NOT NULL,
    z           INTEGER NOT NULL DEFAULT 0,
    vocation    TEXT NOT NULL DEFAULT 'knight',
    skills      TEXT NOT NULL DEFAULT '',
    inventory   TEXT NOT NULL DEFAULT '[]',
    equipment   TEXT NOT NULL DEFAULT '{}',
    deaths      INTEGER NOT NULL DEFAULT 0,
    last_login  TEXT
);
"""

# colunas adicionadas depois do MVP (migração de bancos antigos)
MIGRATIONS = (
    "ALTER TABLE accounts ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE characters ADD COLUMN z INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE characters ADD COLUMN vocation TEXT NOT NULL DEFAULT 'knight'",
    "ALTER TABLE characters ADD COLUMN skills TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE characters ADD COLUMN hotkeys TEXT NOT NULL DEFAULT ''",
)


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        for migration in MIGRATIONS:
            try:
                self.conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # coluna já existe
        self.conn.commit()

    # ------------------------------------------------------------- contas

    @staticmethod
    def _hash(salt: str, password: str) -> str:
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def create_account(self, name: str, password: str):
        """Cria conta. Retorna o id, ou None se o nome já existe.
        A primeira conta do servidor nasce administradora."""
        salt = secrets.token_hex(8)
        first = self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        try:
            cur = self.conn.execute(
                "INSERT INTO accounts (name, password, salt, is_admin)"
                " VALUES (?,?,?,?)",
                (name, self._hash(salt, password), salt, 1 if first else 0),
            )
        except sqlite3.IntegrityError:
            return None
        self.conn.commit()
        return cur.lastrowid

    def check_login(self, name: str, password: str):
        """Valida credenciais. Retorna a row da conta (com is_admin) ou None."""
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE name = ?", (name,)
        ).fetchone()
        if row and self._hash(row["salt"], password) == row["password"]:
            return row
        return None

    def is_admin(self, account_id: int) -> bool:
        row = self.conn.execute(
            "SELECT is_admin FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return bool(row and row["is_admin"])

    # -------------------------------------------------------- personagens

    def create_character(self, account_id: int, name: str, x: int, y: int,
                         maxhp: int, maxmp: int, inventory, equipment,
                         vocation: str = "knight"):
        """Cria personagem com kit inicial. Retorna id ou None se nome em uso."""
        try:
            cur = self.conn.execute(
                "INSERT INTO characters (account_id,name,hp,maxhp,mp,maxmp,x,y,"
                "vocation,inventory,equipment) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (account_id, name, maxhp, maxhp, maxmp, maxmp, x, y, vocation,
                 json.dumps(inventory), json.dumps(equipment)),
            )
        except sqlite3.IntegrityError:
            return None
        self.conn.commit()
        return cur.lastrowid

    def character_name_exists(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM characters WHERE name = ?", (name,)
        ).fetchone()
        return row is not None

    def get_character_by_account(self, account_id: int):
        """Retorna o personagem da conta (uma conta = um personagem no MVP)."""
        return self.conn.execute(
            "SELECT * FROM characters WHERE account_id = ? ORDER BY id LIMIT 1",
            (account_id,),
        ).fetchone()

    def save_character(self, char_id: int, p) -> None:
        """Grava o estado atual de um Player (objeto de entities.py)."""
        self.conn.execute(
            "UPDATE characters SET level=?, exp=?, hp=?, maxhp=?, mp=?, maxmp=?,"
            " x=?, y=?, z=?, vocation=?, skills=?, hotkeys=?, inventory=?,"
            " equipment=?, deaths=?, last_login=datetime('now') WHERE id=?",
            (p.level, p.exp, p.hp, p.maxhp, p.mp, p.maxmp, p.x, p.y, p.z,
             p.vocation, json.dumps(p.skills), json.dumps(p.hotkeys),
             json.dumps(p.inventory), json.dumps(p.equipment), p.deaths,
             char_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
