"""Seed a demo business with 90 days of realistic sales history.

Run from the repository root:

    python scripts/seed_demo.py           # seed (aborts if demo already exists)
    python scripts/seed_demo.py --force   # wipe and re-seed the demo business

Demo login: demo@smartstock.app / SmartStockDemo!2026
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402

DEMO_EMAIL = "demo@smartstock.app"
DEMO_PASSWORD = "SmartStockDemo!2026"
DEMO_BUSINESS = "Grace Provisions Store"
DEMO_TIMEZONE = "Africa/Lagos"
HISTORY_DAYS = 90

WEEKDAY_FACTORS = {0: 0.9, 1: 0.8, 2: 0.9, 3: 1.0, 4: 1.1, 5: 1.5, 6: 1.0}

# sku, name, category, buying, selling, base units/day, current stock
PRODUCTS = [
    ("SP-001", "Golden Penny Semovita 1kg", "Staples", 1200, 1500, 3.0, 40),
    ("IN-002", "Indomie Chicken Noodles (carton)", "Noodles", 6500, 7800, 2.0, 25),
    ("PK-003", "Peak Milk Sachet (carton)", "Dairy", 8500, 9900, 1.5, 18),
    ("GS-004", "Golden Star Rice 5kg", "Staples", 7500, 9000, 1.2, 4),
    ("BU-005", "Bua Sugar 1kg", "Staples", 900, 1200, 2.0, 60),
    ("MG-006", "Mama Gold Garri 1kg", "Staples", 700, 1000, 2.5, 80),
    ("RY-007", "Royco Mchuzi Mix 200g", "Spices", 550, 800, 1.0, 50),
    ("VO-008", "Kano Line Vegetable Oil 1L", "Cooking Oil", 2100, 2600, 1.5, 30),
    ("PO-009", "Palm Oil 750ml", "Cooking Oil", 1800, 2300, 1.0, 22),
    ("KV-010", "Kings Vegetable Oil 500ml", "Cooking Oil", 1300, 1700, 1.0, 35),
    ("EB-011", "Elephant Beans 1kg", "Staples", 1500, 1900, 0.8, 45),
    ("TR-012", "Toughon Rice 5kg", "Staples", 6800, 8200, 0.7, 10),
    ("OM-013", "Oatmeal 500g", "Breakfast", 1600, 2100, 0.5, 5),
    ("ML-014", "Milo Refill 500g", "Beverages", 3200, 3900, 1.2, 24),
    ("NC-015", "Nescafe Sachet (10s)", "Beverages", 2400, 3000, 0.7, 16),
    ("LC-016", "La Casera 75cl (crate)", "Drinks", 4800, 6000, 1.0, 3),
    ("BM-017", "Bullet Malt (crate)", "Drinks", 5200, 6500, 1.0, 14),
    ("DT-018", "Dettol Soap 70g", "Toiletries", 950, 1300, 1.8, 48),
    ("CP-019", "Colgate Toothpaste 100ml", "Toiletries", 1400, 1850, 0.9, 30),
    ("AS-020", "Always Sanitary Pack", "Toiletries", 2600, 3300, 0.6, 12),
]

# sku -> (days_ago the change started, multiplier on the base rate)
SPIKES = {"LC-016": (7, 4.5)}
DROPS = {"BU-005": (10, 0.25)}
# sku -> stop selling entirely this many days ago
STOPS = {"TR-012": 14}
# sku -> days_ago values on which a below-cost sale is forced (triggers anomaly)
BELOW_COST = {"OM-013": {4, 11, 18, 25}}


def poissonish(rng: random.Random, expected: float) -> int:
    if expected <= 0:
        return 0
    low = max(0, int(expected - 1))
    high = int(expected) + 3
    weights = [
        (expected ** k) / 2.718281828 ** expected if expected > 0 else (1 if k == 0 else 0)
        for k in range(low, high + 1)
    ]
    total = sum(weights) or 1.0
    pick = rng.uniform(0, total)
    running = 0.0
    for offset, weight in enumerate(weights):
        running += weight
        if pick <= running:
            return low + offset
    return low


def delete_existing_demo(connection) -> None:
    user = connection.execute(
        "SELECT id FROM users WHERE lower(email) = %s", (DEMO_EMAIL,)
    ).fetchone()
    if user is None:
        return
    business = connection.execute(
        "SELECT id FROM businesses WHERE owner_user_id = %s", (user["id"],)
    ).fetchone()
    if business is not None:
        connection.execute("DELETE FROM sales WHERE business_id = %s", (business["id"],))
        connection.execute(
            "DELETE FROM business_invitations WHERE business_id = %s", (business["id"],)
        )
        connection.execute("DELETE FROM businesses WHERE id = %s", (business["id"],))
    connection.execute("DELETE FROM users WHERE id = %s", (user["id"],))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Smart Stock demo business.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and re-seed the demo business if it already exists.",
    )
    args = parser.parse_args()

    if not settings.database_url:
        print("DATABASE_URL is not configured (backend/.env).")
        raise SystemExit(1)

    rng = random.Random(42)
    zone = ZoneInfo(DEMO_TIMEZONE)
    today = datetime.now(zone).date()
    hashed_password = hash_password(DEMO_PASSWORD)

    connection = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        with connection.transaction():
            existing = connection.execute(
                "SELECT id FROM users WHERE lower(email) = %s", (DEMO_EMAIL,)
            ).fetchone()
            if existing is not None:
                if not args.force:
                    print(
                        "Demo business already exists. "
                        "Run with --force to wipe and re-seed it."
                    )
                    return
                delete_existing_demo(connection)

            user = connection.execute(
                """
                INSERT INTO users (full_name, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                ("Grace Adeniyi", DEMO_EMAIL, hashed_password),
            ).fetchone()
            business = connection.execute(
                """
                INSERT INTO businesses (name, owner_user_id, low_stock_threshold, timezone)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (DEMO_BUSINESS, user["id"], 5, DEMO_TIMEZONE),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO business_memberships (user_id, business_id, role)
                VALUES (%s, %s, 'owner')
                """,
                (user["id"], business["id"]),
            )

            product_ids: dict[str, object] = {}
            for sku, name, category, buying, selling, _rate, stock in PRODUCTS:
                product = connection.execute(
                    """
                    INSERT INTO products
                        (business_id, sku, name, category, buying_price,
                         selling_price, stock_quantity)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (business["id"], sku, name, category, buying, selling, stock),
                ).fetchone()
                product_ids[sku] = product["id"]
                connection.execute(
                    """
                    INSERT INTO product_sku_registry (business_id, sku)
                    VALUES (%s, %s)
                    """,
                    (business["id"], sku),
                )

            sales_rows = []
            for sku, _name, _category, buying, selling, rate, _stock in PRODUCTS:
                product_id = product_ids[sku]
                for days_ago in range(HISTORY_DAYS - 1, -1, -1):
                    day = today - timedelta(days=days_ago)
                    if sku in STOPS and days_ago < STOPS[sku]:
                        continue

                    expected = rate * WEEKDAY_FACTORS[day.weekday()]
                    if sku in SPIKES:
                        start_days, multiplier = SPIKES[sku]
                        if days_ago < start_days:
                            expected *= multiplier
                    if sku in DROPS:
                        start_days, multiplier = DROPS[sku]
                        if days_ago < start_days:
                            expected *= multiplier

                    units = poissonish(rng, expected)
                    below_cost = 0
                    if days_ago in BELOW_COST.get(sku, ()):
                        units = max(units, 1)
                        below_cost = 1
                    if units <= 0:
                        continue
                    units = min(units, 12)

                    item_selling = round(buying * 0.85, 2) if below_cost else selling
                    hour = rng.randint(8, 19)
                    minute = rng.randint(0, 59)
                    created_at = datetime.combine(
                        day, time(hour, minute), tzinfo=zone
                    )
                    total = round(item_selling * units, 2)
                    profit = round((item_selling - buying) * units, 2)
                    sales_rows.append(
                        (
                            business["id"],
                            product_id,
                            user["id"],
                            units,
                            item_selling,
                            buying,
                            profit,
                            total,
                            created_at,
                        )
                    )

            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO sales
                        (business_id, product_id, recorded_by_user_id, quantity,
                         selling_price, buying_price, profit, total_amount, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    sales_rows,
                )
    finally:
        connection.close()

    total_revenue = sum(row[7] for row in sales_rows)
    print("Demo business seeded.")
    print(f"  business: {DEMO_BUSINESS}")
    print(f"  login:    {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  products: {len(PRODUCTS)}")
    print(f"  sales:    {len(sales_rows)} rows over {HISTORY_DAYS} days")
    print(f"  revenue:  NGN {total_revenue:,.2f}")


if __name__ == "__main__":
    main()
