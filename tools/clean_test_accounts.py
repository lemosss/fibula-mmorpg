"""
clean_test_accounts.py — Remove contas criadas pelo smoke test (smoke*/demo*).

Uso:  python tools/clean_test_accounts.py   (com o servidor DESLIGADO,
ou aceitando que jogadores online dessas contas serão re-salvos no logout)
"""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = sqlite3.connect(os.path.join(ROOT, "data", "fibula.db"))
FILTER = ("name LIKE 'smoke%' OR name LIKE 'demo%' OR name LIKE 'warnobs%'")
cur = db.execute(
    "DELETE FROM characters WHERE account_id IN "
    f"(SELECT id FROM accounts WHERE {FILTER})")
chars = cur.rowcount
accs = db.execute(f"DELETE FROM accounts WHERE {FILTER}").rowcount
db.commit()
print(f"Removidos: {accs} conta(s), {chars} personagem(ns) de teste.")
restantes = db.execute("SELECT name, is_admin FROM accounts").fetchall()
print("Contas restantes:", restantes)
