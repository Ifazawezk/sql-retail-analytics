-- Schema for a small grocery chain in Qatar.
-- All money columns are in Qatari riyals (QAR). Dates are ISO 8601 text,
-- which sorts correctly and works with SQLite's date functions.

PRAGMA foreign_keys = ON;

CREATE TABLE branches (
    branch_id       INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    city            TEXT    NOT NULL,
    opened_on       TEXT    NOT NULL,                 -- YYYY-MM-DD
    floor_area_sqm  INTEGER NOT NULL CHECK (floor_area_sqm > 0)
);

CREATE TABLE categories (
    category_id     INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY,
    sku             TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories (category_id),
    unit_price      REAL    NOT NULL CHECK (unit_price > 0),   -- current shelf price
    unit_cost       REAL    NOT NULL CHECK (unit_cost > 0),    -- current supplier cost
    CHECK (unit_cost < unit_price)
);

CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    gender          TEXT    NOT NULL CHECK (gender IN ('F', 'M')),
    birth_year      INTEGER CHECK (birth_year BETWEEN 1940 AND 2010),
    area            TEXT    NOT NULL,                 -- district the customer lives in
    home_branch_id  INTEGER NOT NULL REFERENCES branches (branch_id),
    joined_on       TEXT    NOT NULL                  -- loyalty sign-up date
);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers (customer_id),
    branch_id       INTEGER NOT NULL REFERENCES branches (branch_id),
    ordered_at      TEXT    NOT NULL,                 -- YYYY-MM-DD HH:MM, local time
    channel         TEXT    NOT NULL CHECK (channel IN ('in_store', 'delivery')),
    payment_method  TEXT    NOT NULL CHECK (payment_method IN ('card', 'cash', 'wallet'))
);

-- One row per product per order. Prices and costs are copied from the
-- product at the time of sale, so later price changes do not rewrite history.
CREATE TABLE order_items (
    order_item_id   INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders (order_id),
    product_id      INTEGER NOT NULL REFERENCES products (product_id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      REAL    NOT NULL CHECK (unit_price > 0),
    unit_cost       REAL    NOT NULL CHECK (unit_cost > 0),
    discount_amount REAL    NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    line_total      REAL    NOT NULL CHECK (line_total >= 0),
    UNIQUE (order_id, product_id),
    CHECK (abs(line_total - (quantity * unit_price - discount_amount)) < 0.005)
);

CREATE TABLE returns (
    return_id       INTEGER PRIMARY KEY,
    order_item_id   INTEGER NOT NULL REFERENCES order_items (order_item_id),
    returned_on     TEXT    NOT NULL,                 -- YYYY-MM-DD
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    refund_amount   REAL    NOT NULL CHECK (refund_amount >= 0),
    reason          TEXT    NOT NULL
);

-- Ramadan, Eid and other dates that move demand. Used by the seasonal queries.
CREATE TABLE calendar_events (
    event_id        INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    kind            TEXT    NOT NULL CHECK (kind IN ('ramadan', 'eid', 'holiday', 'season')),
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    CHECK (end_date >= start_date)
);

-- The UNIQUE constraint on order_items already gives an index that starts
-- with order_id, so only the product side needs its own index.
CREATE INDEX idx_products_category      ON products (category_id);
CREATE INDEX idx_customers_home_branch  ON customers (home_branch_id);
CREATE INDEX idx_orders_customer        ON orders (customer_id, ordered_at);
CREATE INDEX idx_orders_branch          ON orders (branch_id, ordered_at);
CREATE INDEX idx_orders_ordered_at      ON orders (ordered_at);
CREATE INDEX idx_order_items_product    ON order_items (product_id);
CREATE INDEX idx_returns_order_item     ON returns (order_item_id);
CREATE INDEX idx_calendar_events_dates  ON calendar_events (start_date, end_date);
