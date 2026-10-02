"""Generate a synthetic printserver_win SQLite copy for browser import tests."""

import json
import sqlite3
import sys
from pathlib import Path


def create(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS templates
            (id INTEGER PRIMARY KEY, name TEXT, width_mm REAL, height_mm REAL, elements TEXT);
            CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, product_code TEXT, qr_content TEXT,
            text_content TEXT, text2 TEXT, text3 TEXT, text4 TEXT, side TEXT, highlight_right INTEGER, template_id INTEGER);""")
        elements = [
            {
                "type": "qr",
                "name": "QR",
                "x": 2,
                "y": 2,
                "w": 20,
                "h": 20,
                "content": "{qr_content}",
            },
            {
                "type": "text",
                "name": "Text",
                "x": 24,
                "y": 2,
                "w": 34,
                "h": 8,
                "font_size": 10,
                "content": "{product_code}",
            },
        ]
        db.execute(
            "INSERT OR IGNORE INTO templates VALUES (42,?,?,?,?)",
            ("Imported standard", 60, 40, json.dumps(elements)),
        )
        db.execute(
            "INSERT OR IGNORE INTO products VALUES (1,?,?,?,?,?,?,?,?,?)",
            (
                "IMPORTED-001",
                "IMPORTED-QR",
                "Imported description",
                "text2",
                "text3",
                "text4",
                "R",
                1,
                42,
            ),
        )


if __name__ == "__main__":
    create(sys.argv[1])
