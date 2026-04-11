from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"


def column_is_not_null(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for row in rows:
        if row[1] == column:
            return row[3] == 1
    raise RuntimeError(f"未找到字段 {table}.{column}")


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"数据库不存在：{DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        old_target_required = column_is_not_null(conn, "orders", "target_account_id")
        old_payout_amount_required = column_is_not_null(conn, "orders", "payout_amount")
        old_payout_currency_required = column_is_not_null(conn, "orders", "payout_currency")
        if not any((old_target_required, old_payout_amount_required, old_payout_currency_required)):
            print("当前数据库已是新结构，无需迁移。")
            return

        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")

        conn.execute(
            """
            CREATE TABLE orders_new (
                id INTEGER PRIMARY KEY,
                order_type VARCHAR(20) NOT NULL,
                customer_id INTEGER NOT NULL,
                supplier_id INTEGER,
                company_account_id INTEGER NOT NULL,
                target_account_id INTEGER,
                deposit_amount NUMERIC(18, 2) NOT NULL,
                deposit_currency VARCHAR(8) NOT NULL,
                payout_amount NUMERIC(18, 2),
                payout_currency VARCHAR(8),
                status VARCHAR(20) NOT NULL,
                notes TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers (id),
                FOREIGN KEY(supplier_id) REFERENCES suppliers (id),
                FOREIGN KEY(company_account_id) REFERENCES company_accounts (id),
                FOREIGN KEY(target_account_id) REFERENCES customer_target_accounts (id)
            )
            """
        )

        conn.execute(
            """
            INSERT INTO orders_new (
                id, order_type, customer_id, supplier_id, company_account_id,
                target_account_id, deposit_amount, deposit_currency,
                payout_amount, payout_currency, status, notes, created_at, updated_at
            )
            SELECT
                id, order_type, customer_id, supplier_id, company_account_id,
                target_account_id, deposit_amount, deposit_currency,
                payout_amount, payout_currency, status, notes, created_at, updated_at
            FROM orders
            """
        )

        conn.execute("DROP TABLE orders")
        conn.execute("ALTER TABLE orders_new RENAME TO orders")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_orders_customer_id ON orders (customer_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_orders_company_account_id ON orders (company_account_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_orders_target_account_id ON orders (target_account_id)"
        )
        conn.commit()
        print("迁移完成：orders.target_account_id / payout_amount / payout_currency 已改为可为空。")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()


if __name__ == "__main__":
    main()
