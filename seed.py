"""Build retail.db, a sample SQLite database for a small grocery chain in Qatar.

The data is made up, but it is shaped to behave like a real chain:

* five branches, one of which (Lusail) opens in September 2024
* a loyalty programme that launches in January 2024, with a sign-up rush in
  the first few weeks and steady growth after that
* two full years of orders (2024 and 2025) where Friday and Saturday, the
  Qatari weekend, are the busiest days
* Ramadan brings more trips and bigger baskets, with dates, juices and
  frozen snacks selling far above normal; the days before each Eid spike
* a summer dip while many residents travel, and a slow shift from cash to
  card, wallet and delivery orders

Only the standard library is used. The same seed always produces the same
database, so the numbers in the README can be reproduced.

Usage:
    python seed.py
    python seed.py --db other.db --seed 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import heapq
import math
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema.sql"
DEFAULT_DB_PATH = ROOT / "retail.db"
DEFAULT_SEED = 42

START_DATE = dt.date(2024, 1, 1)
END_DATE = dt.date(2025, 12, 31)
LAST_SIGNUP_DATE = dt.date(2025, 11, 30)

N_CUSTOMERS = 400
LAUNCH_WAVE = 120          # members who sign up in the first weeks of the programme

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

BRANCHES = [
    # id, name, city, opened_on, floor area in square metres
    (1, "Al Sadd", "Doha", "2015-04-12", 1400),
    (2, "Al Wakrah", "Al Wakrah", "2017-11-02", 1100),
    (3, "Al Rayyan", "Al Rayyan", "2019-03-17", 1250),
    (4, "Al Khor", "Al Khor", "2021-02-07", 900),
    (5, "Lusail", "Lusail", "2024-09-15", 1600),
]
LUSAIL_BRANCH_ID = 5
LUSAIL_OPENED = dt.date(2024, 9, 15)

# Residential areas served by each branch, with a weight for how many
# loyalty members live there. Lusail-side residents shopped at Al Sadd
# until their own branch opened.
AREAS = {
    1: (0.30, ["Al Sadd", "Bin Mahmoud", "Fereej Bin Omran", "Al Muntazah", "Najma", "Al Hilal"]),
    2: (0.18, ["Al Wakrah", "Al Wukair", "Mesaieed", "Barwa City"]),
    3: (0.25, ["Al Rayyan", "Muaither", "Al Gharrafa", "Al Waab", "Ain Khaled"]),
    4: (0.10, ["Al Khor", "Al Thakhira", "Simaisma"]),
    5: (0.17, ["Lusail", "The Pearl", "West Bay", "Al Dafna"]),
}

CATEGORIES = [
    # id, name, sku prefix, typical gross margin
    (1, "Fresh Produce", "PRO", 0.32),
    (2, "Dairy & Eggs", "DAI", 0.18),
    (3, "Bakery", "BAK", 0.35),
    (4, "Meat & Poultry", "MEA", 0.22),
    (5, "Seafood", "SEA", 0.25),
    (6, "Rice, Grains & Pasta", "GRA", 0.15),
    (7, "Pantry & Cooking", "PAN", 0.24),
    (8, "Beverages", "BEV", 0.30),
    (9, "Snacks & Sweets", "SNK", 0.36),
    (10, "Dates & Nuts", "DAT", 0.40),
    (11, "Frozen", "FRZ", 0.27),
    (12, "Household", "HOU", 0.30),
    (13, "Personal Care", "PER", 0.34),
]

# Tags change demand at certain times of year:
#   ramadan - sells strongly during Ramadan (and goes on Ramadan promotion)
#   eid     - bought for Eid gatherings and gifts
#   lamb    - Eid al-Adha
#   summer  - hot weather favourites
#   multi   - usually bought several at a time
PRODUCTS = [
    # category prefix, name, shelf price (QAR), popularity, tags
    ("PRO", "Bananas 1kg", 6.50, 9, ""),
    ("PRO", "Tomatoes 1kg", 5.75, 9, ""),
    ("PRO", "Cucumbers 1kg", 6.25, 7, ""),
    ("PRO", "Onions 2kg", 7.00, 7, ""),
    ("PRO", "Potatoes 2kg", 8.50, 6, ""),
    ("PRO", "Lemons 500g", 4.25, 6, "ramadan"),
    ("PRO", "Red Apples 1kg", 9.75, 5, ""),
    ("PRO", "Oranges 1kg", 7.50, 5, ""),
    ("PRO", "Fresh Mint Bunch", 1.50, 5, "multi"),
    ("PRO", "Parsley Bunch", 1.50, 4, "ramadan multi"),
    ("PRO", "Watermelon Whole", 14.00, 2, "summer"),
    ("PRO", "Mangoes 1kg", 15.50, 2, "summer"),
    ("DAI", "Fresh Milk Full Fat 2L", 12.50, 9, ""),
    ("DAI", "Laban 1L", 6.00, 7, "ramadan multi"),
    ("DAI", "Plain Yoghurt 1kg", 9.25, 6, "multi"),
    ("DAI", "Eggs 30 Pack", 21.00, 8, ""),
    ("DAI", "Labneh 400g", 10.50, 5, ""),
    ("DAI", "Feta Cheese 500g", 14.75, 4, ""),
    ("DAI", "Cheddar Slices 200g", 9.00, 4, ""),
    ("DAI", "Unsalted Butter 200g", 10.25, 3, ""),
    ("DAI", "Halloumi 250g", 13.50, 3, ""),
    ("DAI", "Cream Cheese Spread 500g", 16.00, 3, ""),
    ("BAK", "Arabic Bread 6 Pieces", 2.00, 10, "multi"),
    ("BAK", "Samoon Bread 6 Pieces", 3.00, 5, "multi"),
    ("BAK", "Sliced White Bread 600g", 6.50, 5, ""),
    ("BAK", "Brown Bread 600g", 7.25, 4, ""),
    ("BAK", "Croissants 4 Pieces", 9.50, 3, ""),
    ("BAK", "Zaatar Manakeesh 4 Pieces", 8.00, 3, ""),
    ("BAK", "Date Maamoul 12 Pieces", 18.00, 1, "eid"),
    ("MEA", "Whole Chicken 1kg", 18.50, 7, "ramadan"),
    ("MEA", "Chicken Breast 1kg", 29.00, 5, ""),
    ("MEA", "Minced Beef 500g", 22.00, 4, ""),
    ("MEA", "Lamb Leg 1kg", 48.00, 2, "lamb"),
    ("MEA", "Lamb Cubes 1kg", 52.00, 2, "lamb ramadan"),
    ("MEA", "Beef Burger Patties 8 Pieces", 24.00, 2, "summer"),
    ("MEA", "Chicken Franks 400g", 9.75, 3, ""),
    ("SEA", "Hammour Fillet 1kg", 72.00, 1, ""),
    ("SEA", "Medium Shrimp 1kg", 55.00, 1, ""),
    ("SEA", "Kingfish Steaks 1kg", 45.00, 1, ""),
    ("SEA", "Safi Fish 1kg", 32.00, 1, ""),
    ("GRA", "Basmati Rice 5kg", 38.00, 6, "ramadan"),
    ("GRA", "Sella Rice 10kg", 62.00, 2, ""),
    ("GRA", "Egyptian Rice 2kg", 12.00, 3, ""),
    ("GRA", "Spaghetti 500g", 4.50, 5, ""),
    ("GRA", "Penne 500g", 4.50, 3, ""),
    ("GRA", "Vermicelli 400g", 3.75, 2, "ramadan"),
    ("GRA", "All Purpose Flour 2kg", 8.25, 3, "ramadan"),
    ("GRA", "Red Lentils 1kg", 9.50, 3, "ramadan"),
    ("GRA", "Dried Chickpeas 1kg", 8.75, 2, "ramadan"),
    ("GRA", "Rolled Oats 1kg", 13.50, 2, ""),
    ("PAN", "Sunflower Oil 1.8L", 16.50, 5, "ramadan"),
    ("PAN", "Olive Oil 1L", 34.00, 2, ""),
    ("PAN", "Tomato Paste 400g", 4.25, 5, ""),
    ("PAN", "Canned Tuna 185g", 6.25, 4, "multi"),
    ("PAN", "Foul Medames 400g", 3.50, 3, "ramadan multi"),
    ("PAN", "Hummus Tahini 400g", 7.75, 4, "ramadan"),
    ("PAN", "White Sugar 2kg", 9.00, 4, "ramadan"),
    ("PAN", "Black Tea 100 Bags", 14.25, 5, ""),
    ("PAN", "Arabic Coffee 250g", 22.00, 2, "ramadan eid"),
    ("PAN", "Cardamom 100g", 18.50, 1, "ramadan eid"),
    ("PAN", "Fine Salt 1kg", 2.25, 2, ""),
    ("PAN", "Sidr Honey 500g", 32.00, 1, ""),
    ("PAN", "Tomato Ketchup 500g", 6.00, 3, ""),
    ("PAN", "Mayonnaise 500ml", 9.50, 2, ""),
    ("BEV", "Mineral Water 12 x 500ml", 9.00, 8, "multi summer"),
    ("BEV", "Mineral Water 6 x 1.5L", 8.50, 5, "multi summer"),
    ("BEV", "Orange Juice 1L", 8.25, 5, "ramadan"),
    ("BEV", "Mango Juice 1L", 7.75, 4, "ramadan"),
    ("BEV", "Mixed Fruit Cordial 710ml", 12.50, 1, "ramadan"),
    ("BEV", "Instant Orange Drink 750g", 18.00, 1, "ramadan"),
    ("BEV", "Apricot Paste Qamar al-Din 400g", 7.50, 1, "ramadan"),
    ("BEV", "Cola 6 x 330ml", 11.00, 5, "summer"),
    ("BEV", "Lemon Mint Juice 1L", 9.00, 3, "summer"),
    ("BEV", "Karak Tea Mix 10 Sachets", 11.50, 3, ""),
    ("SNK", "Potato Chips 150g", 6.50, 5, "multi"),
    ("SNK", "Chocolate Bar 4 Pack", 10.00, 4, "eid"),
    ("SNK", "Assorted Biscuits 400g", 8.75, 4, ""),
    ("SNK", "Kunafa Dough 500g", 9.00, 1, "ramadan"),
    ("SNK", "Assorted Baklava 500g", 35.00, 1, "eid"),
    ("SNK", "Halawa with Pistachio 450g", 11.25, 2, ""),
    ("SNK", "Salted Popcorn 100g", 4.00, 2, ""),
    ("DAT", "Khalas Dates 1kg", 28.00, 3, "ramadan eid"),
    ("DAT", "Sukkari Dates 1kg", 35.00, 2, "ramadan eid"),
    ("DAT", "Medjool Dates 1kg", 65.00, 1, "ramadan eid"),
    ("DAT", "Roasted Mixed Nuts 500g", 39.00, 2, "eid"),
    ("DAT", "Salted Pistachios 500g", 44.00, 1, "eid"),
    ("DAT", "Raw Almonds 500g", 31.00, 1, ""),
    ("DAT", "Dried Apricots 500g", 22.00, 1, "ramadan"),
    ("FRZ", "Frozen Mixed Vegetables 1kg", 9.50, 3, ""),
    ("FRZ", "Frozen French Fries 2.5kg", 19.00, 4, ""),
    ("FRZ", "Frozen Samosas 24 Pieces", 17.50, 1, "ramadan"),
    ("FRZ", "Frozen Spring Rolls 20 Pieces", 15.00, 1, "ramadan"),
    ("FRZ", "Frozen Chicken Nuggets 1kg", 24.50, 3, ""),
    ("FRZ", "Frozen Paratha 20 Pieces", 14.00, 4, ""),
    ("FRZ", "Vanilla Ice Cream 2L", 21.00, 2, "summer"),
    ("HOU", "Dishwashing Liquid 1L", 8.50, 4, ""),
    ("HOU", "Laundry Detergent 3kg", 34.00, 3, ""),
    ("HOU", "Facial Tissues 5 Boxes", 12.00, 4, ""),
    ("HOU", "Toilet Rolls 12 Pack", 22.50, 4, ""),
    ("HOU", "Aluminium Foil 30m", 9.25, 2, "ramadan"),
    ("HOU", "Garbage Bags 50 Pieces", 11.00, 3, ""),
    ("HOU", "Surface Cleaner 1L", 10.75, 2, ""),
    ("HOU", "Bakhoor Incense 40g", 25.00, 1, "eid"),
    ("PER", "Shampoo 400ml", 17.50, 3, ""),
    ("PER", "Toothpaste 120ml", 8.75, 4, ""),
    ("PER", "Bath Soap 6 Pack", 13.00, 3, ""),
    ("PER", "Shower Gel 500ml", 15.25, 2, ""),
    ("PER", "Deodorant 150ml", 14.50, 2, ""),
    ("PER", "Baby Diapers 44 Pieces", 49.00, 2, ""),
    ("PER", "Sunscreen SPF50 200ml", 39.00, 1, "summer"),
]

# Products that tend to end up in the same basket. When the first product
# is picked, the second is added with the given probability.
BASKET_PAIRS = [
    ("Arabic Bread 6 Pieces", "Hummus Tahini 400g", 0.30),
    ("Arabic Bread 6 Pieces", "Labneh 400g", 0.20),
    ("Foul Medames 400g", "Arabic Bread 6 Pieces", 0.55),
    ("Spaghetti 500g", "Tomato Paste 400g", 0.50),
    ("Minced Beef 500g", "Spaghetti 500g", 0.35),
    ("Black Tea 100 Bags", "Fresh Milk Full Fat 2L", 0.45),
    ("Karak Tea Mix 10 Sachets", "Fresh Milk Full Fat 2L", 0.30),
    ("Potato Chips 150g", "Cola 6 x 330ml", 0.40),
    ("Basmati Rice 5kg", "Whole Chicken 1kg", 0.40),
    ("Frozen French Fries 2.5kg", "Tomato Ketchup 500g", 0.35),
    ("Khalas Dates 1kg", "Arabic Coffee 250g", 0.35),
    ("Sukkari Dates 1kg", "Laban 1L", 0.35),
    ("Arabic Coffee 250g", "Cardamom 100g", 0.45),
    ("Kunafa Dough 500g", "Cream Cheese Spread 500g", 0.50),
    ("Shampoo 400ml", "Shower Gel 500ml", 0.25),
    ("Red Lentils 1kg", "Lemons 500g", 0.40),
    ("Frozen Samosas 24 Pieces", "Frozen Spring Rolls 20 Pieces", 0.40),
    ("Beef Burger Patties 8 Pieces", "Cheddar Slices 200g", 0.45),
]

CALENDAR_EVENTS = [
    # name, kind, first day, last day (dates follow the announcements in Qatar)
    ("Ramadan 2024", "ramadan", "2024-03-11", "2024-04-09"),
    ("Eid al-Fitr 2024", "eid", "2024-04-10", "2024-04-12"),
    ("Eid al-Adha 2024", "eid", "2024-06-16", "2024-06-18"),
    ("Summer holidays 2024", "season", "2024-07-01", "2024-08-31"),
    ("Qatar National Day 2024", "holiday", "2024-12-18", "2024-12-18"),
    ("Ramadan 2025", "ramadan", "2025-03-01", "2025-03-29"),
    ("Eid al-Fitr 2025", "eid", "2025-03-30", "2025-04-01"),
    ("Eid al-Adha 2025", "eid", "2025-06-06", "2025-06-08"),
    ("Summer holidays 2025", "season", "2025-07-01", "2025-08-31"),
    ("Qatar National Day 2025", "holiday", "2025-12-18", "2025-12-18"),
]

# Monday is 0. Friday and Saturday are the weekend in Qatar.
WEEKDAY_FACTOR = {0: 0.85, 1: 0.85, 2: 0.90, 3: 1.10, 4: 1.35, 5: 1.30, 6: 0.90}

# Relative order volume for each opening hour, 07:00 to 23:00.
OPEN_HOURS = list(range(7, 24))
HOUR_WEIGHTS_NORMAL = [1, 2, 3, 5, 5, 4, 3, 3, 3, 4, 6, 7, 8, 8, 6, 4, 2]
# Friday mornings are quiet and trade almost stops for the midday prayer.
HOUR_WEIGHTS_FRIDAY = [1, 2, 3, 3, 1, 0.3, 2, 4, 5, 6, 7, 8, 9, 9, 7, 5, 3]
# During Ramadan the late afternoon empties out before iftar and the
# evening after it becomes the busiest part of the day.
HOUR_WEIGHTS_RAMADAN = [0, 0.5, 2, 3, 4, 4, 5, 6, 6, 3, 1, 2, 6, 10, 12, 12, 9]

RETURN_RATE = {"PRO": 0.025, "DAI": 0.02, "MEA": 0.02, "SEA": 0.03, "BAK": 0.015, "FRZ": 0.01}
DEFAULT_RETURN_RATE = 0.006
PERISHABLE = {"PRO", "DAI", "MEA", "SEA", "BAK"}

NAME_GROUPS = [
    # share of members, male first names, female first names, family names
    (0.22,
     ["Mohammed", "Abdullah", "Khalid", "Hamad", "Ali", "Jassim", "Nasser", "Saad", "Fahad", "Rashid"],
     ["Fatima", "Maryam", "Noora", "Hessa", "Aisha", "Moza", "Shaikha", "Latifa", "Reem", "Dana"],
     ["Al Kuwari", "Al Marri", "Al Mannai", "Al Sulaiti", "Al Naimi", "Al Mohannadi", "Al Hajri",
      "Al Emadi", "Al Kaabi", "Al Jaber"]),
    (0.20,
     ["Ahmed", "Mahmoud", "Omar", "Karim", "Mostafa", "Tarek", "Youssef", "Hany", "Rami", "Samer"],
     ["Nour", "Rania", "Heba", "Yasmin", "Salma", "Dina", "Lina", "Mai", "Rana", "Hala"],
     ["Hassan", "Ibrahim", "Mansour", "Farouk", "Saleh", "Haddad", "Khalil", "Nasr", "Fawzy", "Darwish"]),
    (0.18,
     ["Rahul", "Arjun", "Vikram", "Suresh", "Anil", "Sanjay", "Ravi", "Manoj"],
     ["Priya", "Anjali", "Deepa", "Lakshmi", "Neha", "Divya", "Kavya", "Sneha"],
     ["Nair", "Menon", "Sharma", "Patel", "Reddy", "Pillai", "Iyer", "Kumar"]),
    (0.12,
     ["Imran", "Bilal", "Usman", "Faisal", "Sameer", "Asif", "Zubair", "Tariq"],
     ["Ayesha", "Sana", "Fathima", "Shabana", "Hina", "Zainab", "Rukhsar", "Mehwish"],
     ["Khan", "Qureshi", "Hussain", "Iqbal", "Siddiqui", "Sheikh", "Malik", "Butt"]),
    (0.15,
     ["Jose", "Mark", "John Paul", "Carlo", "Rodel", "Jerome", "Ramon", "Arnel"],
     ["Maria", "Grace", "Joy", "Angelica", "Kristine", "Mary Ann", "Liza", "Rowena"],
     ["Santos", "Reyes", "Cruz", "Garcia", "Mendoza", "Bautista", "Villanueva", "Dela Cruz"]),
    (0.06,
     ["Bikash", "Suman", "Ramesh", "Prakash", "Dipak"],
     ["Sita", "Anita", "Sabina", "Puja", "Kamala"],
     ["Thapa", "Gurung", "Shrestha", "Tamang", "Rai"]),
    (0.07,
     ["James", "Daniel", "Thomas", "Michael", "David"],
     ["Emma", "Sophie", "Sarah", "Laura", "Hannah"],
     ["Smith", "Brown", "Wilson", "Taylor", "Murphy"]),
]


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def parse_date(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def daterange(first: dt.date, last: dt.date):
    day = first
    while day <= last:
        yield day
        day += dt.timedelta(days=1)


@dataclass(frozen=True)
class DayInfo:
    ramadan: bool = False
    ramadan_last_ten: bool = False
    before_eid_fitr: bool = False
    before_eid_adha: bool = False
    eid: bool = False
    summer: bool = False
    national_day: bool = False

    @property
    def demand_mode(self) -> str:
        """Which set of product weights applies on this day."""
        if self.before_eid_fitr:
            return "before_eid_fitr"
        if self.ramadan:
            return "ramadan"
        if self.before_eid_adha or self.eid:
            return "eid"
        if self.summer:
            return "summer"
        return "normal"


def build_calendar() -> dict[dt.date, DayInfo]:
    flags: dict[dt.date, dict[str, bool]] = {d: {} for d in daterange(START_DATE, END_DATE)}

    def mark(first: dt.date, last: dt.date, key: str) -> None:
        for d in daterange(first, last):
            if d in flags:
                flags[d][key] = True

    for name, kind, start_text, end_text in CALENDAR_EVENTS:
        first, last = parse_date(start_text), parse_date(end_text)
        if kind == "ramadan":
            mark(first, last, "ramadan")
            mark(last - dt.timedelta(days=9), last, "ramadan_last_ten")
            mark(last - dt.timedelta(days=2), last, "before_eid_fitr")
        elif kind == "eid":
            mark(first, last, "eid")
            if "Adha" in name:
                mark(first - dt.timedelta(days=4), first - dt.timedelta(days=1), "before_eid_adha")
        elif kind == "season":
            mark(first, last, "summer")
        elif kind == "holiday":
            mark(first - dt.timedelta(days=1), last, "national_day")

    # June counts as summer for product mix even though school is still on.
    for d in flags:
        if d.month == 6:
            flags[d]["summer"] = True

    return {d: DayInfo(**f) for d, f in flags.items()}


def visit_factor(day: dt.date, info: DayInfo) -> float:
    """How much more (or less) likely a member is to shop on this day."""
    factor = WEEKDAY_FACTOR[day.weekday()]
    if info.ramadan:
        factor *= 1.30 if info.ramadan_last_ten else 1.15
    if info.before_eid_fitr:
        factor *= 1.6
    if info.before_eid_adha:
        factor *= 1.4
    if info.eid:
        factor *= 0.75
    if day.month in (7, 8):
        factor *= 0.9
    if info.national_day:
        factor *= 1.2
    if day.day <= 5:
        factor *= 1.1          # salaries land at the end of the month
    return factor


def basket_factor(info: DayInfo) -> float:
    if info.before_eid_fitr:
        return 1.45
    if info.ramadan:
        return 1.30
    if info.before_eid_adha:
        return 1.20
    return 1.0


# ---------------------------------------------------------------------------
# Small random helpers (all take the shared Random instance)
# ---------------------------------------------------------------------------

def poisson(rng: random.Random, lam: float) -> int:
    """Knuth's method. Good enough for the small means used here."""
    limit = math.exp(-lam)
    k, p = 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def weighted_sample(rng: random.Random, items: list[int], weights: list[float], k: int) -> list[int]:
    """Pick k distinct items with probability proportional to weight."""
    keyed = ((rng.random() ** (1.0 / w), item) for item, w in zip(items, weights) if w > 0)
    return [item for _, item in heapq.nlargest(k, keyed)]


def round_to_quarter(value: float) -> float:
    return max(0.25, round(value * 4) / 4)


# ---------------------------------------------------------------------------
# Catalogue and customers
# ---------------------------------------------------------------------------

@dataclass
class Product:
    product_id: int
    sku: str
    name: str
    category_id: int
    category_code: str
    unit_price: float
    unit_cost: float
    popularity: float
    tags: frozenset[str]


def build_products(rng: random.Random) -> list[Product]:
    by_code = {code: (cat_id, margin) for cat_id, _, code, margin in CATEGORIES}
    counters: dict[str, int] = {}
    products = []
    for product_id, (code, name, price, popularity, tags) in enumerate(PRODUCTS, start=1):
        cat_id, margin = by_code[code]
        counters[code] = counters.get(code, 0) + 1
        cost = round(price * (1 - margin) * rng.uniform(0.92, 1.08), 2)
        cost = min(cost, round(price * 0.95, 2))
        products.append(Product(
            product_id=product_id,
            sku=f"{code}-{counters[code]:03d}",
            name=name,
            category_id=cat_id,
            category_code=code,
            unit_price=price,
            unit_cost=cost,
            popularity=float(popularity),
            tags=frozenset(tags.split()),
        ))
    return products


@dataclass
class Customer:
    customer_id: int
    first_name: str
    last_name: str
    gender: str
    birth_year: int
    area: str
    area_branch: int
    home_branch: int
    joined_on: dt.date
    visits_per_week: float
    basket_size: float
    delivery_bias: float
    cash_bias: float
    leaves_on: dt.date
    away: list[tuple[dt.date, dt.date]] = field(default_factory=list)

    def is_away(self, day: dt.date) -> bool:
        return any(first <= day <= last for first, last in self.away)


def signup_dates(rng: random.Random, calendar: dict[dt.date, DayInfo]) -> list[dt.date]:
    dates = []
    for _ in range(LAUNCH_WAVE):
        offset = min(int(rng.expovariate(1 / 12)), 45)
        dates.append(START_DATE + dt.timedelta(days=offset))

    days, weights = [], []
    for day in daterange(START_DATE + dt.timedelta(days=46), LAST_SIGNUP_DATE):
        weight = 1.0
        if calendar[day].ramadan:
            weight = 1.6
        elif day.month in (7, 8):
            weight = 0.6
        if LUSAIL_OPENED <= day < LUSAIL_OPENED + dt.timedelta(days=60):
            weight = 2.2
        days.append(day)
        weights.append(weight)
    dates.extend(rng.choices(days, weights=weights, k=N_CUSTOMERS - LAUNCH_WAVE))
    return sorted(dates)


def build_customers(rng: random.Random, calendar: dict[dt.date, DayInfo]) -> list[Customer]:
    group_weights = [g[0] for g in NAME_GROUPS]
    branch_ids = list(AREAS)
    customers = []
    for customer_id, joined in enumerate(signup_dates(rng, calendar), start=1):
        _, male, female, family = rng.choices(NAME_GROUPS, weights=group_weights)[0]
        gender = rng.choice("FM")
        first_name = rng.choice(female if gender == "F" else male)

        area_weights = [AREAS[b][0] for b in branch_ids]
        if LUSAIL_OPENED <= joined < LUSAIL_OPENED + dt.timedelta(days=60):
            area_weights[branch_ids.index(LUSAIL_BRANCH_ID)] *= 3
        area_branch = rng.choices(branch_ids, weights=area_weights)[0]
        area = rng.choice(AREAS[area_branch][1])
        home_branch = area_branch
        if area_branch == LUSAIL_BRANCH_ID and joined < LUSAIL_OPENED:
            home_branch = 1

        # About a fifth of members try the programme and drift away quickly.
        if rng.random() < 0.22:
            stays_for = rng.expovariate(1 / 45)
        else:
            stays_for = rng.expovariate(1 / 700)
        leaves_on = joined + dt.timedelta(days=int(stays_for))

        away = []
        for year in (2024, 2025):
            if rng.random() < 0.55:
                start = dt.date(year, 6, 20) + dt.timedelta(days=rng.randint(0, 50))
                away.append((start, start + dt.timedelta(days=rng.randint(21, 42))))

        customers.append(Customer(
            customer_id=customer_id,
            first_name=first_name,
            last_name=rng.choice(family),
            gender=gender,
            birth_year=min(2005, max(1955, int(rng.gauss(1987, 9)))),
            area=area,
            area_branch=area_branch,
            home_branch=home_branch,
            joined_on=joined,
            visits_per_week=rng.lognormvariate(math.log(0.27), 0.55),
            basket_size=rng.lognormvariate(math.log(3.4), 0.35),
            delivery_bias=rng.choices([0.4, 1.0, 2.2], weights=[0.4, 0.4, 0.2])[0],
            cash_bias=rng.choices([0.5, 1.0, 1.8], weights=[0.3, 0.45, 0.25])[0],
            leaves_on=leaves_on,
            away=away,
        ))
    return customers


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class OrderSimulator:
    def __init__(self, rng: random.Random, calendar: dict[dt.date, DayInfo], products: list[Product]):
        self.rng = rng
        self.calendar = calendar
        self.products = products
        self.product_ids = [p.product_id for p in products]
        self.by_id = {p.product_id: p for p in products}
        by_name = {p.name: p.product_id for p in products}
        self.pairs: dict[int, list[tuple[int, float]]] = {}
        for first, second, prob in BASKET_PAIRS:
            self.pairs.setdefault(by_name[first], []).append((by_name[second], prob))
        self.weekly_promos = self._plan_promotions()
        self._weight_cache: dict[tuple[str, tuple[int, int]], list[float]] = {}
        self.total_days = (END_DATE - START_DATE).days

    def _plan_promotions(self) -> dict[tuple[int, int], set[int]]:
        """Six products go on a 10% weekly promotion, chosen per ISO week."""
        promos = {}
        for day in daterange(START_DATE, END_DATE):
            week = day.isocalendar()[:2]
            if week not in promos:
                promos[week] = set(self.rng.sample(self.product_ids, 6))
        return promos

    def _weights(self, info: DayInfo, week: tuple[int, int]) -> list[float]:
        key = (info.demand_mode, week)
        if key not in self._weight_cache:
            mode = info.demand_mode
            promo = self.weekly_promos[week]
            weights = []
            for p in self.products:
                w = p.popularity
                if mode in ("ramadan", "before_eid_fitr") and "ramadan" in p.tags:
                    w *= 3.0
                if mode == "before_eid_fitr" and "eid" in p.tags:
                    w *= 3.0
                if mode == "eid" and "lamb" in p.tags:
                    w *= 5.0
                if mode == "eid" and "eid" in p.tags:
                    w *= 1.5
                if mode == "summer" and "summer" in p.tags:
                    w *= 2.5
                if p.product_id in promo:
                    w *= 1.7
                weights.append(w)
            self._weight_cache[key] = weights
        return self._weight_cache[key]

    def _pick_branch(self, customer: Customer, day: dt.date) -> int:
        rng = self.rng
        if customer.area_branch == LUSAIL_BRANCH_ID and day >= LUSAIL_OPENED and rng.random() < 0.7:
            return LUSAIL_BRANCH_ID
        if rng.random() < 0.85:
            return customer.home_branch
        open_branches = [b[0] for b in BRANCHES
                         if parse_date(b[3]) <= day and b[0] != customer.home_branch]
        return rng.choice(open_branches)

    def _pick_time(self, day: dt.date, info: DayInfo) -> str:
        if info.ramadan:
            weights = HOUR_WEIGHTS_RAMADAN
        elif day.weekday() == 4:
            weights = HOUR_WEIGHTS_FRIDAY
        else:
            weights = HOUR_WEIGHTS_NORMAL
        hour = self.rng.choices(OPEN_HOURS, weights=weights)[0]
        return f"{day.isoformat()} {hour:02d}:{self.rng.randrange(60):02d}"

    def _pick_channel_and_payment(self, customer: Customer, day: dt.date) -> tuple[str, str]:
        rng = self.rng
        progress = (day - START_DATE).days / self.total_days
        delivery_p = (0.07 + 0.11 * progress) * customer.delivery_bias
        if day.month in (6, 7, 8):
            delivery_p += 0.04
        channel = "delivery" if rng.random() < min(delivery_p, 0.6) else "in_store"

        if channel == "delivery":
            wallet = 0.15 + 0.10 * progress
            cash = 0.12 * customer.cash_bias
        else:
            wallet = 0.06 + 0.14 * progress
            cash = (0.34 - 0.12 * progress) * customer.cash_bias
        roll = rng.random()
        if roll < wallet:
            payment = "wallet"
        elif roll < wallet + cash:
            payment = "cash"
        else:
            payment = "card"
        return channel, payment

    def _quantity(self, product: Product) -> int:
        if "multi" in product.tags:
            return self.rng.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
        return self.rng.choices([1, 2, 3, 4], weights=[75, 18, 5, 2])[0]

    def make_order(self, customer: Customer, day: dt.date) -> dict:
        rng = self.rng
        info = self.calendar[day]
        week = day.isocalendar()[:2]
        channel, payment = self._pick_channel_and_payment(customer, day)

        mean_lines = customer.basket_size * basket_factor(info) * (1.2 if channel == "delivery" else 1.0)
        n_lines = min(1 + poisson(rng, max(0.3, mean_lines - 1)), 18)
        chosen = weighted_sample(rng, self.product_ids, self._weights(info, week), n_lines)
        for product_id in list(chosen):
            for partner, prob in self.pairs.get(product_id, []):
                if partner not in chosen and rng.random() < prob:
                    chosen.append(partner)

        promo = self.weekly_promos[week]
        lines = []
        for product_id in chosen:
            product = self.by_id[product_id]
            if day.year >= 2025:
                price, cost = product.unit_price, product.unit_cost
            else:
                # Shelf prices went up about 3% at the start of 2025.
                price = round_to_quarter(product.unit_price * 0.97)
                cost = round(product.unit_cost * 0.97, 2)
            qty = self._quantity(product)
            if info.ramadan and "ramadan" in product.tags:
                pct = 0.15
            elif product_id in promo:
                pct = 0.10
            else:
                pct = 0.0
            gross = round(qty * price, 2)
            discount = round(gross * pct, 2)
            lines.append({
                "product": product,
                "quantity": qty,
                "unit_price": price,
                "unit_cost": cost,
                "discount_amount": discount,
                "line_total": round(gross - discount, 2),
            })

        return {
            "customer_id": customer.customer_id,
            "branch_id": self._pick_branch(customer, day),
            "ordered_at": self._pick_time(day, info),
            "channel": channel,
            "payment_method": payment,
            "lines": lines,
        }

    def orders_for(self, customer: Customer) -> list[dict]:
        rng = self.rng
        last_day = min(END_DATE, customer.leaves_on)
        # Most people sign up at the till, so the first order is usually the
        # same day; the rest come back within a couple of weeks.
        if rng.random() < 0.7:
            first = customer.joined_on
        else:
            first = customer.joined_on + dt.timedelta(days=rng.randint(1, 14))
        if first > END_DATE:
            return []

        orders = [self.make_order(customer, first)]
        daily_rate = customer.visits_per_week / 7
        for day in daterange(first + dt.timedelta(days=1), last_day):
            if customer.is_away(day):
                continue
            if rng.random() < daily_rate * visit_factor(day, self.calendar[day]):
                orders.append(self.make_order(customer, day))
        return orders


def make_return(rng: random.Random, order: dict, line: dict) -> dict | None:
    product: Product = line["product"]
    rate = RETURN_RATE.get(product.category_code, DEFAULT_RETURN_RATE)
    if order["channel"] == "delivery":
        rate *= 1.5
    if rng.random() >= rate:
        return None

    order_day = parse_date(order["ordered_at"][:10])
    perishable = product.category_code in PERISHABLE
    returned_on = order_day + dt.timedelta(days=rng.randint(0, 2 if perishable else 6))
    if order["channel"] == "delivery" and rng.random() < 0.3:
        reason = "Missing or wrong item"
    elif perishable:
        reason = rng.choices(["Expired or spoiled", "Damaged packaging", "Quality complaint"],
                             weights=[5, 2, 3])[0]
    else:
        reason = rng.choices(["Damaged packaging", "Changed mind", "Wrong item"], weights=[4, 3, 2])[0]

    qty = line["quantity"] if line["quantity"] == 1 else rng.randint(1, line["quantity"])
    refund = round(line["line_total"] * qty / line["quantity"], 2)
    return {"returned_on": returned_on.isoformat(), "quantity": qty,
            "refund_amount": refund, "reason": reason}


# ---------------------------------------------------------------------------
# Writing the database
# ---------------------------------------------------------------------------

def build_database(db_path: str | Path = DEFAULT_DB_PATH, seed: int = DEFAULT_SEED) -> dict[str, int]:
    """Create a fresh database at db_path and return row counts per table."""
    rng = random.Random(seed)
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()

    calendar = build_calendar()
    products = build_products(rng)
    customers = build_customers(rng, calendar)
    simulator = OrderSimulator(rng, calendar, products)

    orders = []
    for customer in customers:
        orders.extend(simulator.orders_for(customer))
    # Number orders in time order, as a till system would.
    orders.sort(key=lambda o: (o["ordered_at"], o["customer_id"]))

    order_rows, item_rows, return_rows = [], [], []
    item_id = 0
    for order_id, order in enumerate(orders, start=1):
        order_rows.append((order_id, order["customer_id"], order["branch_id"], order["ordered_at"],
                           order["channel"], order["payment_method"]))
        for line in order["lines"]:
            item_id += 1
            item_rows.append((item_id, order_id, line["product"].product_id, line["quantity"],
                              line["unit_price"], line["unit_cost"], line["discount_amount"],
                              line["line_total"]))
            ret = make_return(rng, order, line)
            if ret:
                return_rows.append((len(return_rows) + 1, item_id, ret["returned_on"], ret["quantity"],
                                    ret["refund_amount"], ret["reason"]))

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executemany("INSERT INTO branches VALUES (?, ?, ?, ?, ?)", BRANCHES)
        conn.executemany("INSERT INTO categories VALUES (?, ?)",
                         [(cat_id, name) for cat_id, name, _, _ in CATEGORIES])
        conn.executemany(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)",
            [(p.product_id, p.sku, p.name, p.category_id, p.unit_price, p.unit_cost) for p in products],
        )
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(c.customer_id, c.first_name, c.last_name, c.gender, c.birth_year, c.area,
              c.home_branch, c.joined_on.isoformat()) for c in customers],
        )
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", order_rows)
        conn.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)", item_rows)
        conn.executemany("INSERT INTO returns VALUES (?, ?, ?, ?, ?, ?)", return_rows)
        conn.executemany(
            "INSERT INTO calendar_events (name, kind, start_date, end_date) VALUES (?, ?, ?, ?)",
            CALENDAR_EVENTS,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "branches": len(BRANCHES),
        "categories": len(CATEGORIES),
        "products": len(products),
        "customers": len(customers),
        "orders": len(order_rows),
        "order_items": len(item_rows),
        "returns": len(return_rows),
        "calendar_events": len(CALENDAR_EVENTS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the sample retail database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="output path (default: retail.db)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default: 42)")
    args = parser.parse_args()

    counts = build_database(args.db, args.seed)
    print(f"Wrote {args.db}")
    for table, count in counts.items():
        print(f"  {table:<16}{count:>8,}")


if __name__ == "__main__":
    main()
