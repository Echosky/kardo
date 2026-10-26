"""SQL Lab for Kardo: a practice database, a sandboxed query runner and an exercise checker.

The practice data ("Shopwise", a fictional online shop) is generated from a fixed seed
at startup, so every run of the container has identical data and exercise answers stay
correct. Each query runs in a fresh in-memory copy of that database, so learners can
INSERT, UPDATE, DROP and CREATE freely without breaking anything for the next query.
"""
import os
import random
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

SEED = 20261026
TIMEOUT = 4.0          # seconds a query may run
SHOW_ROWS = 500        # rows sent to the phone
COMPARE_ROWS = 50000   # rows read when checking an answer
MAX_SQL = 40000
EXERCISES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lab_exercises.txt")


class LabError(Exception):
    """A problem with the learner's query or request, shown to them as a message."""
    pass


# ---------------------------------------------------------------- practice data

SCHEMA = """
create table categories(
  category_id integer primary key,
  name text not null,
  parent_id integer references categories(category_id)
);
create table products(
  product_id integer primary key,
  name text not null,
  category_id integer not null references categories(category_id),
  unit_price real not null,
  unit_cost real not null,
  launched_on text not null,
  discontinued integer not null default 0
);
create table customers(
  customer_id integer primary key,
  first_name text not null,
  last_name text not null,
  email text unique,
  city text,
  country text not null,
  segment text not null,
  signup_date text not null,
  referred_by integer references customers(customer_id)
);
create table employees(
  employee_id integer primary key,
  full_name text not null,
  title text not null,
  department text not null,
  manager_id integer references employees(employee_id),
  hire_date text not null,
  salary integer not null
);
create table orders(
  order_id integer primary key,
  customer_id integer not null references customers(customer_id),
  order_date text not null,
  status text not null,
  channel text not null,
  employee_id integer references employees(employee_id)
);
create table order_items(
  order_id integer not null references orders(order_id),
  line_no integer not null,
  product_id integer not null references products(product_id),
  quantity integer not null,
  unit_price real not null,
  discount real not null default 0,
  primary key (order_id, line_no)
);
create table payments(
  payment_id integer primary key,
  order_id integer not null references orders(order_id),
  paid_at text not null,
  amount real not null,
  method text not null
);
create table subscriptions(
  subscription_id integer primary key,
  customer_id integer not null references customers(customer_id),
  plan text not null,
  start_date text not null,
  end_date text,
  monthly_fee real not null
);
create table events(
  event_id integer primary key,
  customer_id integer not null references customers(customer_id),
  event_time text not null,
  event_type text not null,
  product_id integer references products(product_id)
);
create table daily_logins(
  customer_id integer not null references customers(customer_id),
  login_date text not null,
  primary key (customer_id, login_date)
);
create table segment_changes(
  customer_id integer not null references customers(customer_id),
  segment text not null,
  changed_at text not null
);
create table raw_crm_contacts(
  contact_id text,
  full_name text,
  email text,
  phone text,
  country_code text,
  updated_at text,
  _loaded_at text
);
create index ix_orders_customer on orders(customer_id);
create index ix_items_product on order_items(product_id);
create index ix_payments_order on payments(order_id);
create index ix_events_customer_time on events(customer_id, event_time);
"""

CATEGORIES = [
    (1, "Electronics", None), (2, "Computers", 1), (3, "Laptops", 2), (4, "Computer Accessories", 2),
    (5, "Audio", 1), (6, "Headphones", 5), (7, "Speakers", 5), (8, "Phones", 1),
    (9, "Home", None), (10, "Kitchen", 9), (11, "Furniture", 9), (12, "Office Chairs", 11),
    (13, "Outdoors", None), (14, "Camping", 13), (15, "Cycling", 13), (16, "Books", None),
]

PRODUCTS = {  # category_id: [(name, price)]
    3: [("Aero 13 Laptop", 899), ("Aero 15 Laptop", 1199), ("Forge Pro 16 Laptop", 1899), ("Student Chromebook", 329)],
    4: [("Wireless Mouse", 29), ("Mechanical Keyboard", 119), ("USB-C Hub", 49), ("27in Monitor", 279),
        ("Laptop Stand", 39), ("Webcam HD", 69), ("Mouse Pad XL", 19)],
    6: [("Studio Headphones", 199), ("Noise Cancelling Headphones", 299), ("Sport Earbuds", 79), ("Kids Headphones", 25)],
    7: [("Bluetooth Speaker Mini", 45), ("Bookshelf Speakers", 249), ("Soundbar 300", 349)],
    8: [("Nova Phone 8", 699), ("Nova Phone 8 Max", 899), ("Budget Phone A2", 199), ("Phone Case", 25), ("Fast Charger 65W", 39)],
    10: [("Espresso Machine", 449), ("Chef Knife", 89), ("Cast Iron Skillet", 49), ("Blender 1200W", 129),
         ("Coffee Grinder", 79), ("Kettle Steel", 39), ("Measuring Cups", 12)],
    11: [("Standing Desk", 549), ("Bookcase Oak", 229), ("Floor Lamp", 79), ("Side Table", 99)],
    12: [("Ergo Chair", 399), ("Task Chair Basic", 149), ("Gaming Chair", 289)],
    14: [("2-Person Tent", 189), ("Sleeping Bag -5C", 129), ("Camping Stove", 59), ("Headlamp", 29),
         ("Hiking Backpack 40L", 149), ("Water Filter", 39)],
    15: [("Road Bike Helmet", 89), ("Bike Lights Set", 35), ("Cycling Gloves", 25), ("Bike Pump", 32), ("Commuter Bike", 799)],
    16: [("SQL for Analysts", 39), ("The Data Warehouse Toolkit", 55), ("Designing Data-Intensive Applications", 49),
         ("Fundamentals of Data Engineering", 52), ("Analytics Engineering with dbt", 45), ("Python Crash Course", 35),
         ("Storytelling with Data", 29), ("Clean Code", 41)],
}

FIRST = ["Aarav", "Priya", "Liam", "Olivia", "Noah", "Emma", "Mia", "Lucas", "Sofia", "Arjun", "Ananya", "Ethan",
         "Ava", "Leo", "Isla", "Mateo", "Zoe", "Omar", "Fatima", "Hana", "Kenji", "Yuki", "Chloe", "Jack", "Grace",
         "Ravi", "Meera", "Daniel", "Sara", "Ben", "Nina", "Tom", "Lena", "Felix", "Clara", "Diego", "Lucia", "Sam",
         "Ivy", "Max", "Rohan", "Kavya", "Owen", "Ella", "Henry", "Amelia", "Jonas", "Maya", "Aiden", "Layla"]
LAST = ["Sharma", "Patel", "Smith", "Johnson", "Brown", "Garcia", "Muller", "Schmidt", "Wilson", "Taylor", "Khan",
        "Singh", "Nguyen", "Kim", "Tanaka", "Rossi", "Martin", "Lee", "Walker", "Young", "Reddy", "Iyer", "Fischer",
        "Weber", "Lopez", "Clark", "Lewis", "Hall", "Allen", "King", "Wright", "Scott", "Green", "Baker", "Adams"]
CITIES = [("New York", "US"), ("Austin", "US"), ("Chicago", "US"), ("Seattle", "US"), ("Denver", "US"),
          ("London", "UK"), ("Manchester", "UK"), ("Bristol", "UK"), ("Bengaluru", "IN"), ("Mumbai", "IN"),
          ("Pune", "IN"), ("Delhi", "IN"), ("Berlin", "DE"), ("Munich", "DE"), ("Hamburg", "DE"),
          ("Toronto", "CA"), ("Vancouver", "CA"), ("Sydney", "AU"), ("Melbourne", "AU")]

EMPLOYEES = [  # id, name, title, department, manager, hire_date, salary
    (1, "Helen Carter", "CEO", "Executive", None, "2018-02-01", 310000),
    (2, "Marcus Webb", "VP Sales", "Sales", 1, "2018-06-15", 210000),
    (3, "Asha Menon", "VP Operations", "Operations", 1, "2019-01-07", 195000),
    (4, "David Osei", "VP Finance", "Finance", 1, "2019-03-11", 190000),
    (5, "Ingrid Larsen", "VP Data", "Data", 1, "2020-09-01", 205000),
    (6, "Paul Novak", "Sales Manager East", "Sales", 2, "2019-05-20", 120000),
    (7, "Rita Gomez", "Sales Manager West", "Sales", 2, "2020-02-03", 118000),
    (8, "Kofi Mensah", "Store Associate", "Sales", 6, "2021-04-12", 52000),
    (9, "Laura Chen", "Store Associate", "Sales", 6, "2022-08-29", 50000),
    (10, "Tariq Aziz", "Store Associate", "Sales", 7, "2021-11-01", 51000),
    (11, "Emily Ross", "Store Associate", "Sales", 7, "2023-03-06", 48000),
    (12, "Victor Hugo", "Senior Store Associate", "Sales", 7, "2020-07-14", 61000),
    (13, "Nadia Petrova", "Warehouse Manager", "Operations", 3, "2019-10-01", 98000),
    (14, "Sean Murphy", "Warehouse Associate", "Operations", 13, "2022-01-17", 45000),
    (15, "Grace Obi", "Warehouse Associate", "Operations", 13, "2023-06-05", 44000),
    (16, "Ken Watanabe", "Logistics Analyst", "Operations", 3, "2021-09-13", 82000),
    (17, "Julia Weiss", "Controller", "Finance", 4, "2020-01-06", 140000),
    (18, "Omar Haddad", "Accountant", "Finance", 17, "2022-04-04", 76000),
    (19, "Mei Lin", "Analytics Engineering Manager", "Data", 5, "2021-02-15", 165000),
    (20, "Ravi Kumar", "Analytics Engineer", "Data", 19, "2022-05-02", 128000),
    (21, "Sophie Martin", "Analytics Engineer", "Data", 19, "2023-01-09", 121000),
    (22, "Lucas Silva", "Data Engineer", "Data", 19, "2022-10-24", 135000),
    (23, "Anna Kowalski", "Data Analyst", "Data", 5, "2023-08-14", 92000),
    (24, "Ben Adler", "Data Analyst", "Data", 5, "2024-02-26", 88000),
    (25, "Chloe Dubois", "Junior Data Analyst", "Data", 23, "2025-03-03", 68000),
]
STORE_STAFF = [8, 9, 10, 11, 12]


def _d(x):
    """Format a date as ISO text, the way the practice database stores dates."""
    return x.isoformat()


def _rand_date(rng, start, end):
    """A random date between start and end, from the seeded generator."""
    return start + timedelta(days=rng.randint(0, (end - start).days))


def populate(con):
    """Create and fill the practice database. Deterministic: the same seed gives the same rows."""
    rng = random.Random(SEED)
    con.executescript(SCHEMA)
    con.executemany("insert into categories values (?,?,?)", CATEGORIES)
    con.executemany("insert into employees values (?,?,?,?,?,?,?)", EMPLOYEES)

    # products
    products = []
    pid = 0
    for cat, items in PRODUCTS.items():
        for name, price in items:
            pid += 1
            cost = round(price * rng.uniform(0.38, 0.72), 2)
            launched = _rand_date(rng, date(2022, 1, 1), date(2025, 6, 30))
            products.append((pid, name, cat, float(price), cost, _d(launched), 1 if rng.random() < 0.08 else 0))
    # one product with no sales yet, launched late
    products.append((pid + 1, "Smart Garden Kit", 10, 159.0, 71.5, "2025-12-20", 0))
    con.executemany("insert into products values (?,?,?,?,?,?,?)", products)
    sellable = [p for p in products if p[0] <= pid]
    weights = [3 if p[3] < 60 else 2 if p[3] < 300 else 1 for p in sellable]

    # customers
    customers = []
    used_emails = set()
    n_cust = 400
    for cid in range(1, n_cust + 1):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        email = f"{fn}.{ln}{rng.randint(1, 99)}@example.com".lower()
        while email in used_emails:
            email = f"{fn}.{ln}{rng.randint(100, 999)}@example.com".lower()
        used_emails.add(email)
        if rng.random() < 0.04:
            email = None
        city, country = rng.choice(CITIES)
        if rng.random() < 0.05:
            city = None
        seg = rng.choices(["consumer", "small_business", "enterprise"], [70, 24, 6])[0]
        signup = _rand_date(rng, date(2023, 1, 1), date(2025, 11, 30))
        customers.append([cid, fn, ln, email, city, country, seg, signup, None])
    customers.sort(key=lambda c: c[7])  # ids follow signup order
    for i, c in enumerate(customers):
        c[0] = i + 1
    for i, c in enumerate(customers):
        if i > 5 and rng.random() < 0.3:
            c[8] = rng.randint(max(1, i - 60), i)  # an earlier customer
    con.executemany("insert into customers values (?,?,?,?,?,?,?,?,?)",
                    [(c[0], c[1], c[2], c[3], c[4], c[5], c[6], _d(c[7]), c[8]) for c in customers])

    # orders, items, payments
    end = date(2025, 12, 31)
    orders, items, pays = [], [], []
    oid = 0
    pay_id = 0
    for c in customers:
        cid, signup, seg = c[0], c[7], c[6]
        if rng.random() < 0.14:
            continue  # never ordered
        n = min(30, int(rng.expovariate(1 / (9 if seg == "enterprise" else 5))) + 1)
        dates = sorted(_rand_date(rng, signup, end) for _ in range(n))
        for od in dates:
            oid += 1
            recent = (end - od).days < 21
            status = rng.choices(["completed", "shipped", "cancelled", "returned", "pending"],
                                 [76, 8, 7, 5, 4 if recent else 0])[0]
            if recent and status == "completed" and rng.random() < 0.5:
                status = "shipped"
            channel = rng.choices(["web", "app", "store"], [50, 35, 15])[0]
            emp = rng.choice(STORE_STAFF) if channel == "store" else None
            orders.append((oid, cid, _d(od), status, channel, emp))
            k = rng.choices([1, 2, 3, 4], [45, 30, 17, 8])[0]
            chosen = []
            while len(chosen) < k:
                p = rng.choices(sellable, weights)[0]
                if p not in chosen:
                    chosen.append(p)
            total = 0.0
            for ln_no, p in enumerate(chosen, 1):
                qty = rng.choices([1, 2, 3, 5], [70, 20, 7, 3])[0]
                price = p[3] if rng.random() < 0.85 else round(p[3] * rng.choice([0.9, 0.95, 1.05]), 2)
                disc = rng.choices([0.0, 0.05, 0.1, 0.2], [70, 12, 12, 6])[0]
                items.append((oid, ln_no, p[0], qty, price, disc))
                total += qty * price * (1 - disc)
            total = round(total, 2)
            if status == "cancelled":
                continue
            paid = od + timedelta(days=rng.choice([0, 0, 0, 1, 2]))
            ts = datetime(paid.year, paid.month, paid.day, rng.randint(7, 22), rng.randint(0, 59), rng.randint(0, 59))
            r = rng.random()
            if status == "pending" and r < 0.5:
                continue
            if r < 0.03:
                continue  # unpaid order
            method = rng.choices(["card", "paypal", "gift_card", "bank_transfer"], [62, 25, 8, 5])[0]
            if r < 0.10 and total > 20:
                part = round(total * rng.choice([0.3, 0.5]), 2)
                pay_id += 1
                pays.append((pay_id, oid, ts.isoformat(sep=" "), part, "gift_card"))
                pay_id += 1
                pays.append((pay_id, oid, (ts + timedelta(minutes=1)).isoformat(sep=" "), round(total - part, 2), method))
            else:
                pay_id += 1
                if rng.random() < 0.03:  # a shipping fee or partial refund that the items don't explain
                    total = round(total + rng.choice([4.99, 9.99, -10.0]), 2)
                pays.append((pay_id, oid, ts.isoformat(sep=" "), total, method))
    con.executemany("insert into orders values (?,?,?,?,?,?)", orders)
    con.executemany("insert into order_items values (?,?,?,?,?,?)", items)
    con.executemany("insert into payments values (?,?,?,?,?)", pays)

    # subscriptions (Shopwise Plus), with churn and returning members
    subs = []
    sid = 0
    for c in customers:
        if rng.random() > 0.28:
            continue
        start = max(c[7], date(2023, 3, 1)) + timedelta(days=rng.randint(0, 120))
        while start <= date(2025, 12, 15):
            sid += 1
            plan = rng.choices(["monthly", "annual"], [70, 30])[0]
            fee = 9.99 if plan == "monthly" else 8.25
            months = rng.randint(1, 18) if plan == "monthly" else 12 * rng.randint(1, 2)
            stop = start + timedelta(days=30 * months)
            if stop > date(2025, 12, 31) or rng.random() < 0.25:
                subs.append((sid, c[0], plan, _d(start), None, fee))
                break
            subs.append((sid, c[0], plan, _d(start), _d(stop), fee))
            if rng.random() < 0.55:
                break
            start = stop + timedelta(days=rng.randint(1, 200))
    con.executemany("insert into subscriptions values (?,?,?,?,?,?)", subs)

    # clickstream events for the last ten weeks
    evs = []
    eid = 0
    active = rng.sample(customers, 200)
    for c in active:
        t = datetime(2025, 10, 20, 8, 0, 0) + timedelta(minutes=rng.randint(0, 60 * 24 * 7))
        for _ in range(rng.randint(2, 14)):
            # one session
            steps = ["page_view"]
            for nxt, p in (("product_view", 0.8), ("add_to_cart", 0.45), ("checkout", 0.6), ("purchase", 0.75)):
                if rng.random() < p:
                    steps.append(nxt)
                else:
                    break
            prod = rng.choice(sellable)[0]
            for _ in range(rng.randint(0, 3)):
                steps.insert(1, "page_view")
            for s in steps:
                eid += 1
                evs.append((eid, c[0], t.isoformat(sep=" "), s, prod if s != "page_view" else None))
                t += timedelta(seconds=rng.randint(15, 600))
            t += timedelta(minutes=rng.randint(40, 60 * 24 * 6))
            if t > datetime(2025, 12, 31, 23, 0, 0):
                break
    evs.sort(key=lambda e: e[2])
    evs = [(i + 1,) + e[1:] for i, e in enumerate(evs)]
    con.executemany("insert into events values (?,?,?,?,?)", evs)

    # daily logins for streak problems
    logins = []
    for c in rng.sample(customers, 40):
        d = date(2025, 11, 1) + timedelta(days=rng.randint(0, 10))
        while d <= date(2025, 12, 31):
            logins.append((c[0], _d(d)))
            d += timedelta(days=1 if rng.random() < 0.72 else rng.randint(2, 6))
    con.executemany("insert into daily_logins values (?,?)", logins)

    # segment history (for slowly changing dimension practice)
    segs = []
    for c in customers:
        segs.append((c[0], "consumer" if c[6] != "consumer" and rng.random() < 0.6 else c[6], _d(c[7])))
        if segs[-1][1] != c[6]:
            mid = _rand_date(rng, c[7] + timedelta(days=1), max(c[7] + timedelta(days=2), date(2025, 12, 1)))
            if rng.random() < 0.3 and c[6] == "enterprise":
                segs.append((c[0], "small_business", _d(mid)))
                mid = mid + timedelta(days=rng.randint(30, 200))
            segs.append((c[0], c[6], _d(mid)))
    segs.sort(key=lambda s: (s[2], s[0]))
    con.executemany("insert into segment_changes values (?,?,?)", segs)

    # a messy CRM extract, loaded twice, with duplicates and formatting noise
    raw = []
    for c in rng.sample(customers, 120):
        base_upd = datetime(2025, 9, 1) + timedelta(hours=rng.randint(0, 24 * 60))
        for v in range(rng.choices([1, 2, 3], [60, 30, 10])[0]):
            name = f"{c[1]} {c[2]}"
            name = rng.choice([name, name.upper(), " " + name, name + "  ", name.lower()])
            email = c[3] or ""
            email = rng.choice([email, email.upper(), " " + email]) if email else rng.choice([None, ""])
            phone = rng.choice([None, f"+1-555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}",
                                f"(555) {rng.randint(100, 999)} {rng.randint(1000, 9999)}"])
            cc = rng.choice([c[5], c[5].lower(), " " + c[5]])
            upd = base_upd + timedelta(days=v * rng.randint(1, 20))
            raw.append((f"C-{c[0]:05d}", name, email, phone, cc, upd.isoformat(sep=" "),
                        rng.choice(["2025-12-01 02:00:00", "2025-12-02 02:00:00"])))
    rng.shuffle(raw)
    raw.append(("", "test user", "test@test.com", None, "US", "2025-10-01 00:00:00", "2025-12-01 02:00:00"))
    raw.append((None, None, None, None, None, None, "2025-12-02 02:00:00"))
    con.executemany("insert into raw_crm_contacts values (?,?,?,?,?,?,?)", raw)
    con.commit()


_master = None
_master_lock = threading.Lock()


def master():
    """The pristine practice database, built once on first use."""
    global _master
    with _master_lock:
        if _master is None:
            m = sqlite3.connect(":memory:", check_same_thread=False)
            populate(m)
            _master = m
        return _master


def fresh():
    """A private in-memory copy of the practice database for one query."""
    m = master()
    con = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    with _master_lock:
        m.backup(con)
    return con


# ---------------------------------------------------------------- running SQL

SAFE_PRAGMAS = {"table_info", "table_xinfo", "table_list", "index_list", "index_info", "index_xinfo",
                "foreign_key_list", "database_list", "compile_options"}


def _authorizer(action, arg1, arg2, dbname, source):
    """SQLite authorizer: no ATTACH/DETACH, no load_extension and only read-only PRAGMAs."""
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() not in SAFE_PRAGMAS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() == "load_extension":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def split_sql(sql):
    """Split a script into statements, respecting quotes and comments."""
    out, buf = [], ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            if buf.strip(" \t\r\n;"):
                out.append(buf.strip())
            buf = ""
    rest = re.sub(r"--[^\n]*|/\*.*?\*/", "", buf, flags=re.S).strip()
    if rest:
        out.append(buf.strip())
    return out


def _guard(con, timeout):
    """Apply the time limit, the authorizer and a size limit to a connection."""
    deadline = time.monotonic() + timeout
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 5000)
    con.set_authorizer(_authorizer)
    if hasattr(con, "setlimit"):  # keep a runaway string or blob from eating the server's memory
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 20_000_000)


def run_script(con, sql, limit):
    """Run every statement; return the last result set and notes about the others."""
    stmts = split_sql(sql)
    if not stmts:
        raise LabError("Type a query first.")
    result, notes = None, []
    for i, st in enumerate(stmts):
        try:
            cur = con.execute(st)
        except sqlite3.Error as e:
            msg = str(e)
            if msg == "interrupted":
                msg = f"Stopped after {TIMEOUT:g} seconds. Check for a runaway recursive CTE or a missing join condition."
            elif msg == "not authorized":
                msg = "That statement isn't allowed in the lab (ATTACH and most PRAGMAs are switched off)."
            where = f" (statement {i + 1} of {len(stmts)})" if len(stmts) > 1 else ""
            raise LabError(f"{msg}{where}")
        if cur.description:
            cols = [d[0] for d in cur.description]
            try:
                rows = cur.fetchmany(limit + 1)
            except sqlite3.Error as e:
                raise LabError("Stopped while reading rows: " + str(e))
            result = (cols, [list(r) for r in rows])
        elif cur.rowcount >= 0:
            notes.append(f"{cur.rowcount} row{'s' if cur.rowcount != 1 else ''} affected")
        else:
            notes.append(st.split(None, 2)[0].upper() + " done")
    return result, notes


def execute(sql, limit=SHOW_ROWS, then=None):
    """Run SQL on a fresh copy and return (result, notes). `then` runs afterwards on the same copy."""
    if len(sql) > MAX_SQL:
        raise LabError("That query is too long for the lab.")
    con = fresh()
    try:
        _guard(con, TIMEOUT)
        result, notes = run_script(con, sql, limit)
        if then:  # check query for DML / DDL exercises, run after the learner's statements
            result, _ = run_script(con, then, limit)
        return result, notes
    finally:
        con.close()


def jsonable(v):
    """Make a value safe to send as JSON (blobs are summarised)."""
    if isinstance(v, bytes):
        return "<blob %d bytes>" % len(v)
    return v


def run_for_display(sql, explain=False, setup="", check=""):
    """Run the learner's SQL and return its last result set. For DML/DDL exercises with
    no SELECT of their own, show what the checker's query sees instead."""
    t0 = time.monotonic()
    stmts = split_sql(sql)
    if explain and stmts:
        if not stmts[-1].upper().startswith("EXPLAIN"):
            stmts[-1] = "EXPLAIN QUERY PLAN " + stmts[-1]
        sql = "\n".join(s if s.rstrip().endswith(";") else s + ";" for s in stmts)
    if len(sql) > MAX_SQL:
        raise LabError("That query is too long for the lab.")
    con = fresh()
    try:
        _guard(con, TIMEOUT)
        if setup:
            run_script(con, setup, 0)
        result, notes = run_script(con, sql, SHOW_ROWS)
        from_check = False
        if not result and check:
            result, _ = run_script(con, check, SHOW_ROWS)
            from_check = True
    finally:
        con.close()
    ms = int((time.monotonic() - t0) * 1000)
    if not result:
        return {"columns": [], "rows": [], "truncated": False, "notes": notes, "ms": ms}
    cols, rows = result
    if from_check:
        notes.append("Showing what the checker's query sees after your statements")
    return {"columns": cols, "rows": [[jsonable(v) for v in r] for r in rows[:SHOW_ROWS]],
            "truncated": len(rows) > SHOW_ROWS, "notes": notes, "ms": ms, "from_check": from_check}


def schema_info():
    """Tables, columns, keys and row counts of the practice database, for the Tables screen."""
    m = master()
    out = []
    with _master_lock:
        tables = [r[0] for r in m.execute("select name from sqlite_master where type='table' order by rowid")]
        for t in tables:
            cols = [{"name": r[1], "type": r[2], "pk": bool(r[5]), "notnull": bool(r[3])}
                    for r in m.execute(f"pragma table_info({t})")]
            fks = {r[3]: f"{r[2]}.{r[4]}" for r in m.execute(f"pragma foreign_key_list({t})")}
            for c in cols:
                if c["name"] in fks:
                    c["ref"] = fks[c["name"]]
            n = m.execute(f"select count(*) from {t}").fetchone()[0]
            out.append({"name": t, "rows": n, "columns": cols})
    return out


# ---------------------------------------------------------------- exercises

def parse_exercises(path=EXERCISES_FILE):
    """Read lab_exercises.txt (format described at the top of that file)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    exercises = []
    for chunk in re.split(r"^=== ", text, flags=re.M)[1:]:
        head, _, body = chunk.partition("\n")
        ex_id, track, title = [x.strip() for x in head.split("|", 2)]
        sections = re.split(r"^--- (\w+)\s*$", body, flags=re.M)
        ex = {"id": ex_id, "track": track, "title": title, "prompt": sections[0].strip(),
              "hint": "", "solution": "", "check": "", "ordered": False, "setup": ""}
        for name, val in zip(sections[1::2], sections[2::2]):
            val = val.strip()
            if name == "options":
                ex["ordered"] = "ordered" in val
            else:
                ex[name] = val
        if not ex["solution"]:
            raise ValueError(f"exercise {ex_id} has no solution")
        exercises.append(ex)
    ids = [e["id"] for e in exercises]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate exercise ids")
    return exercises


_exercises = None
_expected = {}


def exercises():
    """All exercises, parsed once."""
    global _exercises
    if _exercises is None:
        _exercises = parse_exercises()
    return _exercises


def get_exercise(ex_id):
    """(index, exercise) for an id."""
    for i, e in enumerate(exercises()):
        if e["id"] == ex_id:
            return i, e
    raise LabError("exercise not found")


def expected(ex):
    """Result of the reference solution for an exercise, cached."""
    if ex["id"] not in _expected:
        sql = (ex["setup"] + ";\n" if ex["setup"] else "") + ex["solution"]
        result, _ = execute(sql, COMPARE_ROWS, then=ex["check"] or None)
        if not result:
            raise LabError(f"exercise {ex['id']} has a solution with no result")
        _expected[ex["id"]] = result
    return _expected[ex["id"]]


def _norm(v):
    """Normalise a value for comparison: whole floats become ints, others are rounded to 2 places."""
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 2)
    return v


def _key(row):
    """Sort key that orders rows of mixed types without raising."""
    return tuple((0, 0) if v is None else (1, v) if isinstance(v, (int, float)) else (2, str(v)) for v in row)


def _same(a, b):
    """Compare two values, allowing a small tolerance for numbers."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.0101
    return a == b


def _rows_equal(r1, r2):
    """True if two lists of rows match value by value."""
    return all(len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b)) for a, b in zip(r1, r2))


def check_answer(ex, sql):
    """Compare the learner's result with the reference solution and explain any difference."""
    exp_cols, exp_rows = expected(ex)
    full = (ex["setup"] + ";\n" if ex["setup"] else "") + sql
    result, notes = execute(full, COMPARE_ROWS, then=ex["check"] or None)
    if not result:
        return {"ok": False, "message": "Your SQL ran but didn't return any rows to check. Finish with a SELECT."}
    cols, rows = result
    if len(rows) > COMPARE_ROWS:
        return {"ok": False, "message": "Your query returns far more rows than expected. Is a join condition missing?"}
    if len(cols) != len(exp_cols):
        return {"ok": False, "message": f"Expected {len(exp_cols)} column{'s' if len(exp_cols) != 1 else ''} "
                f"({', '.join(exp_cols)}), but your query returns {len(cols)}."}
    if len(rows) != len(exp_rows):
        return {"ok": False, "message": f"Expected {len(exp_rows)} row{'s' if len(exp_rows) != 1 else ''}, "
                f"your query returns {len(rows)}."}
    mine = [[_norm(v) for v in r] for r in rows]
    theirs = [[_norm(v) for v in r] for r in exp_rows]
    if ex["ordered"]:
        if _rows_equal(mine, theirs):
            return {"ok": True, "message": "Correct!"}
        if _rows_equal(sorted(mine, key=_key), sorted(theirs, key=_key)):
            return {"ok": False, "message": "The right rows, but in the wrong order. Check your ORDER BY."}
    elif _rows_equal(sorted(mine, key=_key), sorted(theirs, key=_key)):
        return {"ok": True, "message": "Correct!"}
    sm, st = sorted(mine, key=_key), sorted(theirs, key=_key)
    for i, (a, b) in enumerate(zip(sm, st)):
        if not _rows_equal([a], [b]):
            bad = [exp_cols[j] for j in range(len(a)) if not _same(a[j], b[j])]
            return {"ok": False, "message": f"Same number of rows, but some values differ (for example in "
                    f"column{'s' if len(bad) > 1 else ''} {', '.join(bad[:3])}). Columns are compared in order: "
                    f"{', '.join(exp_cols)}."}
    return {"ok": False, "message": "Not quite. Compare your output with the expected result."}
