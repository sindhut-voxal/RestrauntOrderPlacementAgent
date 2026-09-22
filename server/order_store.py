import json
import sqlite3
from pathlib import Path
from typing import Optional

from models import Order

DB_PATH = Path(__file__).parent / "data" / "orders.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def save_order(order: Order) -> None:
    if not order.order_id:
        raise ValueError("order_id is required to save an order")

    payload = json.dumps(order.to_dict())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO orders (order_id, payload)
            VALUES (?, ?)
            ON CONFLICT(order_id) DO UPDATE SET payload = excluded.payload
            """,
            (order.order_id, payload),
        )
        conn.commit()


def get_order(order_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()

    if not row:
        return None

    return json.loads(row["payload"])
