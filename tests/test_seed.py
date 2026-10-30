import sqlite3

import seed


def scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_row_counts_are_in_expected_range(conn):
    assert scalar(conn, "SELECT COUNT(*) FROM branches") == 5
    assert scalar(conn, "SELECT COUNT(*) FROM customers") == seed.N_CUSTOMERS
    assert scalar(conn, "SELECT COUNT(*) FROM products") == len(seed.PRODUCTS)
    assert 15_000 <= scalar(conn, "SELECT COUNT(*) FROM order_items") <= 25_000
    assert scalar(conn, "SELECT COUNT(*) FROM returns") > 0


def test_foreign_keys_hold(conn):
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_every_order_has_lines(conn):
    assert scalar(conn, """
        SELECT COUNT(*) FROM orders o
        WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.order_id)
    """) == 0


def test_orders_fall_inside_the_data_window(conn):
    first, last = conn.execute("SELECT MIN(ordered_at), MAX(ordered_at) FROM orders").fetchone()
    assert first >= "2024-01-01"
    assert last < "2026-01-01"


def test_no_order_before_branch_opened_or_customer_joined(conn):
    assert scalar(conn, """
        SELECT COUNT(*) FROM orders o JOIN branches b USING (branch_id)
        WHERE date(o.ordered_at) < b.opened_on
    """) == 0
    assert scalar(conn, """
        SELECT COUNT(*) FROM orders o JOIN customers c USING (customer_id)
        WHERE date(o.ordered_at) < c.joined_on
    """) == 0


def test_returns_are_consistent_with_their_order_lines(conn):
    assert scalar(conn, """
        SELECT COUNT(*) FROM returns r
        JOIN order_items oi USING (order_item_id)
        JOIN orders o ON o.order_id = oi.order_id
        WHERE r.quantity > oi.quantity
           OR r.refund_amount > oi.line_total + 0.005
           OR r.returned_on < date(o.ordered_at)
    """) == 0


def test_same_seed_gives_same_data(tmp_path):
    def fingerprint(path):
        conn = sqlite3.connect(path)
        try:
            return conn.execute(
                "SELECT COUNT(*), ROUND(SUM(line_total), 2), SUM(product_id * order_id) FROM order_items"
            ).fetchone()
        finally:
            conn.close()

    seed.build_database(tmp_path / "a.db", seed=1)
    seed.build_database(tmp_path / "b.db", seed=1)
    seed.build_database(tmp_path / "c.db", seed=2)
    assert fingerprint(tmp_path / "a.db") == fingerprint(tmp_path / "b.db")
    assert fingerprint(tmp_path / "a.db") != fingerprint(tmp_path / "c.db")
