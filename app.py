
# from flask import (
#     Flask, render_template, request, redirect, url_for,
#     flash, jsonify, make_response, session, g, abort
# )
# from functools import wraps
# from werkzeug.security import generate_password_hash, check_password_hash
# import sqlite3
# import math
# import csv
# import io
# from pathlib import Path
# from datetime import date, datetime, timedelta
# from contextlib import closing

# app = Flask(__name__)
# app.secret_key = __import__("os").environ.get("EXPIRYGUARD_SECRET_KEY", "dev-only-change-this-secret-key-before-deployment")
# app.config["SESSION_COOKIE_HTTPONLY"] = True
# app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# BASE_DIR = Path(__file__).resolve().parent
# DB_PATH = BASE_DIR / "expiryguard.db"


# # ============================================================
# # DATABASE
# # ============================================================

# def get_db():
#     conn = sqlite3.connect(DB_PATH, timeout=10)
#     conn.row_factory = sqlite3.Row
#     conn.execute("PRAGMA foreign_keys = ON")
#     return conn


# def column_exists(conn, table, column):
#     return any(
#         row["name"] == column
#         for row in conn.execute(f"PRAGMA table_info({table})")
#     )


# def init_db():
#     with closing(get_db()) as conn:
#         conn.executescript("""
#             CREATE TABLE IF NOT EXISTS batches (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 product_name TEXT NOT NULL,
#                 category TEXT NOT NULL,
#                 batch_number TEXT NOT NULL,
#                 quantity INTEGER NOT NULL DEFAULT 0
#                     CHECK(quantity >= 0),
#                 purchase_price REAL NOT NULL DEFAULT 0
#                     CHECK(purchase_price >= 0),
#                 selling_price REAL NOT NULL DEFAULT 0
#                     CHECK(selling_price >= 0),
#                 expiry_date TEXT NOT NULL,
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 UNIQUE(product_name, batch_number)
#             );

#             CREATE TABLE IF NOT EXISTS sales (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 batch_id INTEGER NOT NULL,
#                 quantity INTEGER NOT NULL CHECK(quantity > 0),
#                 sold_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );

#             CREATE TABLE IF NOT EXISTS stock_movements (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 batch_id INTEGER NOT NULL,
#                 movement_type TEXT NOT NULL,
#                 quantity_change INTEGER NOT NULL,
#                 note TEXT DEFAULT '',
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );

#             CREATE TABLE IF NOT EXISTS users (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 username TEXT NOT NULL COLLATE NOCASE UNIQUE,
#                 email TEXT NOT NULL COLLATE NOCASE UNIQUE,
#                 password_hash TEXT NOT NULL,
#                 role TEXT NOT NULL CHECK(role IN ('Admin', 'Manager', 'Staff')),
#                 status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#             );
#         """)

#         # Add missing columns without deleting existing inventory.
#         additions = {
#             "barcode": "TEXT",
#             "stock_entry_date": "TEXT",
#         }

#         for column, definition in additions.items():
#             if not column_exists(conn, "batches", column):
#                 conn.execute(
#                     f"ALTER TABLE batches ADD COLUMN {column} {definition}"
#                 )

#         # Existing records get a reasonable entry date.
#         conn.execute("""
#             UPDATE batches
#             SET stock_entry_date = COALESCE(
#                 stock_entry_date,
#                 date(created_at),
#                 date('now')
#             )
#             WHERE stock_entry_date IS NULL OR stock_entry_date = ''
#         """)

#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_batches_expiry
#             ON batches(expiry_date)
#         """)
#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_sales_date
#             ON sales(sold_at)
#         """)
#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_movements_date
#             ON stock_movements(created_at)
#         """)

#         conn.commit()


# # ============================================================
# # AUTHENTICATION
# # ============================================================

# @app.before_request
# def require_login():
#     if request.endpoint in {"login", "static"} or request.endpoint is None:
#         return None
#     if not session.get("user_id"):
#         return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
#     with closing(get_db()) as conn:
#         user = conn.execute(
#             "SELECT id, username, email, role, status FROM users WHERE id = ?",
#             (session["user_id"],)
#         ).fetchone()
#     if not user or user["status"] != "Active":
#         session.clear()
#         return redirect(url_for("login"))
#     g.current_user = dict(user)


# @app.context_processor
# def inject_current_user():
#     return {"current_user": getattr(g, "current_user", None)}


# def admin_required(view):
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         if not getattr(g, "current_user", None) or g.current_user["role"] != "Admin":
#             abort(403)
#         return view(*args, **kwargs)
#     return wrapped


# def manager_required(view):
#     """Allow Admin and Manager to perform operational stock management."""
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         user = getattr(g, "current_user", None)
#         if not user or user["role"] not in {"Admin", "Manager"}:
#             abort(403)
#         return view(*args, **kwargs)
#     return wrapped


# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if session.get("user_id"):
#         return redirect(url_for("dashboard"))
#     error = None
#     if request.method == "POST":
#         identity = request.form.get("identity", "").strip()
#         password = request.form.get("password", "")
#         with closing(get_db()) as conn:
#             user = conn.execute(
#                 "SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1",
#                 (identity, identity)
#             ).fetchone()
#         if user and user["status"] == "Active" and check_password_hash(user["password_hash"], password):
#             session.clear()
#             session["user_id"] = user["id"]
#             session["username"] = user["username"]
#             session["role"] = user["role"]
#             destination = request.args.get("next", "")
#             if not destination.startswith("/") or destination.startswith("//"):
#                 destination = url_for("dashboard")
#             return redirect(destination)
#         error = "Invalid username/email or password, or the account is inactive."
#     return render_template("login.html", error=error)


# @app.route("/logout", methods=["POST"])
# def logout():
#     session.clear()
#     return redirect(url_for("login"))


# @app.route("/users/create", methods=["POST"])
# @admin_required
# def create_user():
#     username = request.form.get("username", "").strip()
#     email = request.form.get("email", "").strip().lower()
#     password = request.form.get("password", "")
#     role = request.form.get("role", "Staff")
#     status = request.form.get("status", "Active")
#     if not username or not email or len(password) < 8 or role not in {"Admin", "Manager", "Staff"} or status not in {"Active", "Inactive"}:
#         flash("Enter valid user details. Password must contain at least 8 characters.", "error")
#         return redirect(url_for("dashboard") + "#users")
#     try:
#         with closing(get_db()) as conn:
#             conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
#                          (username, email, generate_password_hash(password), role, status))
#             conn.commit()
#         flash(f"Account created for {username}.", "success")
#     except sqlite3.IntegrityError:
#         flash("Username or email already exists.", "error")
#     return redirect(url_for("dashboard") + "#users")


# @app.route("/users/<int:user_id>/edit", methods=["POST"])
# @admin_required
# def edit_user(user_id):
#     username = request.form.get("username", "").strip()
#     email = request.form.get("email", "").strip().lower()
#     role = request.form.get("role", "")

#     if not username or not email or role not in {"Admin", "Manager", "Staff"}:
#         flash("Enter a valid username, email and role.", "error")
#         return redirect(url_for("dashboard") + "#users")

#     if user_id == g.current_user["id"] and role != "Admin":
#         flash("You cannot remove Admin access from your own account.", "error")
#         return redirect(url_for("dashboard") + "#users")

#     try:
#         with closing(get_db()) as conn:
#             cursor = conn.execute(
#                 "UPDATE users SET username = ?, email = ?, role = ? WHERE id = ?",
#                 (username, email, role, user_id)
#             )
#             if cursor.rowcount == 0:
#                 flash("User not found.", "error")
#             else:
#                 conn.commit()
#                 flash("User details and role updated.", "success")
#     except sqlite3.IntegrityError:
#         flash("Username or email already exists.", "error")
#     except sqlite3.Error:
#         app.logger.exception("User update failed")
#         flash("Database error while updating the user.", "error")

#     return redirect(url_for("dashboard") + "#users")


# @app.route("/users/<int:user_id>/status", methods=["POST"])
# @admin_required
# def update_user_status(user_id):
#     status = request.form.get("status")
#     if status not in {"Active", "Inactive"}:
#         abort(400)
#     if user_id == g.current_user["id"] and status == "Inactive":
#         flash("You cannot deactivate your own account.", "error")
#     else:
#         with closing(get_db()) as conn:
#             conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
#             conn.commit()
#         flash("User status updated.", "success")
#     return redirect(url_for("dashboard") + "#users")


# @app.cli.command("create-admin")
# def create_admin_command():
#     """Create the first Admin account interactively; password is never stored in plain text."""
#     import getpass
#     username = input("Admin username: ").strip()
#     email = input("Admin email: ").strip().lower()
#     password = getpass.getpass("Admin password (minimum 8 characters): ")
#     confirm = getpass.getpass("Confirm password: ")
#     if not username or not email or len(password) < 8 or password != confirm:
#         print("Invalid details or passwords do not match.")
#         return
#     with closing(get_db()) as conn:
#         exists = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0]
#         if exists:
#             print("An Admin account already exists. Use the Users page to create accounts.")
#             return
#         try:
#             conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, 'Admin', 'Active')",
#                          (username, email, generate_password_hash(password)))
#             conn.commit()
#             print("Admin account created successfully. You can now log in.")
#         except sqlite3.IntegrityError:
#             print("That username or email is already in use.")


# # ============================================================
# # HELPERS
# # ============================================================

# def get_status(expiry_date):
#     days_left = (date.fromisoformat(str(expiry_date)[:10]) -
#                  date.today()).days

#     if days_left < 0:
#         status = "Expired"
#     elif days_left == 0:
#         status = "Expires Today"
#     elif days_left <= 7:
#         status = "Urgent"
#     elif days_left <= 30:
#         status = "Warning"
#     else:
#         status = "Safe"

#     return days_left, status


# def enrich_batch(batch):
#     item = dict(batch)
#     item["days_left"], item["status"] = get_status(item["expiry_date"])
#     item["stock_value"] = item["quantity"] * item["purchase_price"]
#     return item


# def get_product_sales(conn):
#     rows = conn.execute("""
#         SELECT
#             LOWER(TRIM(b.product_name)) AS product_key,
#             MIN(b.product_name) AS product_name,
#             SUM(b.quantity) AS total_stock,
#             COALESCE((
#                 SELECT SUM(s.quantity)
#                 FROM sales s
#                 JOIN batches bx ON bx.id = s.batch_id
#                 WHERE LOWER(TRIM(bx.product_name)) =
#                       LOWER(TRIM(b.product_name))
#                   AND date(s.sold_at) >= date('now', '-6 days')
#                   AND date(s.sold_at) <= date('now')
#             ), 0) AS sold_7_days
#         FROM batches b
#         GROUP BY LOWER(TRIM(b.product_name))
#     """).fetchall()

#     return {
#         row["product_key"]: {
#             "product_name": row["product_name"],
#             "total_stock": row["total_stock"] or 0,
#             "sold_7_days": row["sold_7_days"] or 0,
#         }
#         for row in rows
#     }


# def generate_recommendations(batches, product_sales):
#     recommendations = []

#     for batch in batches:
#         quantity = max(0, int(batch["quantity"]))
#         days = batch["days_left"]
#         key = batch["product_name"].strip().casefold()
#         sales_info = product_sales.get(key, {})
#         sold = float(sales_info.get("sold_7_days", 0))
#         daily = sold / 7
#         value = round(quantity * batch["purchase_price"], 2)

#         def add(level, title, detail, action, stock_value=value):
#             recommendations.append({
#                 "level": level,
#                 "title": title,
#                 "product": batch["product_name"],
#                 "batch": batch["batch_number"],
#                 "days_left": days,
#                 "detail": detail,
#                 "action": action,
#                 "stock_value": stock_value,
#             })

#         if quantity <= 0:
#             continue

#         if days < 0:
#             add(
#                 "critical", "Expired Stock",
#                 f"{quantity} units expired {abs(days)} day(s) ago.",
#                 "Remove from sale and follow disposal procedures."
#             )
#             continue

#         if days == 0:
#             add(
#                 "critical", "Expires Today",
#                 f"{quantity} units reach their expiry date today.",
#                 "Review immediately; do not sell once expired."
#             )
#         elif days <= 3:
#             add(
#                 "critical", "Critical Expiry Risk",
#                 f"{quantity} units remain and expire in {days} day(s).",
#                 "Review immediately and prioritize eligible stock."
#             )
#         elif days <= 7:
#             add(
#                 "urgent", "Urgent Expiry Risk",
#                 f"{quantity} units remain and expire in {days} days.",
#                 "Prioritize this batch using FEFO."
#             )
#         elif days <= 30:
#             add(
#                 "warning", "Upcoming Expiry",
#                 f"{quantity} units expire in {days} days.",
#                 "Monitor sales and replenishment."
#             )

#         if days > 0 and daily > 0:
#             at_risk = max(0, min(quantity, math.ceil(quantity - daily * days)))
#             if at_risk:
#                 add(
#                     "warning", "Potential Expiry Loss",
#                     f"Recent sales suggest approximately {at_risk} "
#                     "unit(s) may remain unsold by expiry.",
#                     "Review sales, stock placement and future orders.",
#                     round(at_risk * batch["purchase_price"], 2)
#                 )
#         elif days > 0 and sold == 0:
#             add(
#                 "info", "No Recent Sales",
#                 "No sales were recorded for this product in the last 7 days.",
#                 "Review demand manually."
#             )

#     for info in product_sales.values():
#         stock = max(0, int(info["total_stock"]))
#         daily = float(info["sold_7_days"]) / 7

#         if daily <= 0:
#             continue

#         cover = stock / daily

#         if stock > 0 and cover <= 3:
#             recommendations.append({
#                 "level": "info",
#                 "title": "Low Stock — Review Restocking",
#                 "product": info["product_name"],
#                 "batch": "All batches",
#                 "days_left": 0,
#                 "detail": f"{stock} units remain, about {cover:.1f} "
#                           "days of sales.",
#                 "action": "Review replenishment and expiry dates.",
#                 "stock_value": 0,
#             })
#         elif cover > 30:
#             recommendations.append({
#                 "level": "warning",
#                 "title": "Possible Overstock",
#                 "product": info["product_name"],
#                 "batch": "All batches",
#                 "days_left": 0,
#                 "detail": f"Current stock represents about {cover:.0f} "
#                           "days of sales.",
#                 "action": "Review purchase orders.",
#                 "stock_value": 0,
#             })

#     priority = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
#     recommendations.sort(key=lambda x: priority.get(x["level"], 4))
#     return recommendations


# def dashboard_data():
#     with closing(get_db()) as conn:
#         raw_batches = conn.execute("""
#             SELECT * FROM batches
#             ORDER BY expiry_date ASC, product_name ASC
#         """).fetchall()

#         product_sales = get_product_sales(conn)

#         categories = [
#             row["category"]
#             for row in conn.execute("""
#                 SELECT DISTINCT category FROM batches
#                 ORDER BY category
#             """).fetchall()
#         ]

#         product_names = [
#             row["product_name"]
#             for row in conn.execute("""
#                 SELECT MIN(product_name) AS product_name
#                 FROM batches
#                 GROUP BY LOWER(TRIM(product_name))
#                 ORDER BY product_name
#             """).fetchall()
#         ]

#         movements = conn.execute("""
#             SELECT sm.*, b.product_name, b.batch_number
#             FROM stock_movements sm
#             JOIN batches b ON b.id = sm.batch_id
#             ORDER BY sm.id DESC
#             LIMIT 50
#         """).fetchall()

#     batches = [enrich_batch(row) for row in raw_batches]
#     recommendations = generate_recommendations(batches, product_sales)

#     summary = {
#         "total_batches": len(batches),
#         "total_units": sum(b["quantity"] for b in batches),
#         "safe": sum(b["status"] == "Safe" for b in batches),
#         "warning": sum(b["status"] == "Warning" for b in batches),
#         "urgent": sum(
#             b["status"] in ("Urgent", "Expires Today") for b in batches
#         ),
#         "expired": sum(b["status"] == "Expired" for b in batches),
#         "potential_loss": round(sum(
#             b["stock_value"] for b in batches
#             if b["status"] in ("Urgent", "Expires Today", "Expired")
#         ), 2),
#         "average_daily_sales": round(
#             sum(x["sold_7_days"] for x in product_sales.values()) / 7, 2
#         ),
#     }

#     return {
#         "batches": batches,
#         "summary": summary,
#         "recommendations": recommendations,
#         "categories": categories,
#         "product_names": product_names,
#         "movements": [dict(m) for m in movements],
#         "today": date.today().isoformat(),
#     }


# # ============================================================
# # DASHBOARD AND MODULE ROUTES
# # ============================================================

# @app.route("/")
# def dashboard():
#     data = dashboard_data()
#     if g.current_user["role"] == "Admin":
#         with closing(get_db()) as conn:
#             data["users"] = [dict(row) for row in conn.execute(
#                 "SELECT id, username, email, role, status, created_at FROM users ORDER BY id"
#             ).fetchall()]
#     else:
#         data["users"] = []
#     return render_template("dashboard.html", **data)


# @app.route("/module/<module_name>")
# def module_view(module_name):
#     allowed = {
#         "dashboard", "inventory", "sales", "recommendations",
#         "alerts", "reports", "products"
#     }
#     if module_name not in allowed:
#         flash("That module does not exist.", "error")
#         return redirect(url_for("dashboard"))
#     return redirect(url_for("dashboard") + "#" + module_name)


# # ============================================================
# # ADD BATCH
# # ============================================================

# @app.route("/add", methods=["POST"])
# @manager_required
# def add_batch():
#     product_name = request.form.get("product_name", "").strip()
#     category = request.form.get("category", "").strip()
#     batch_number = request.form.get("batch_number", "").strip()
#     barcode = request.form.get("barcode", "").strip() or None
#     expiry = request.form.get("expiry_date", "").strip()

#     try:
#         quantity = int(request.form.get("quantity", ""))
#         purchase = float(request.form.get("purchase_price", ""))
#         selling = float(request.form.get("selling_price", ""))

#         if not all((product_name, category, batch_number, expiry)):
#             raise ValueError("Fill in all required fields.")

#         date.fromisoformat(expiry)

#         if expiry < date.today().isoformat():
#             raise ValueError("Expiry date cannot be in the past.")
#         if quantity <= 0:
#             raise ValueError("Quantity must be greater than zero.")
#         if not all(map(math.isfinite, [purchase, selling])):
#             raise ValueError("Enter valid prices.")
#         if purchase < 0 or selling < 0:
#             raise ValueError("Prices cannot be negative.")

#     except (ValueError, OverflowError):
#         flash("Enter valid batch details, quantity, dates and prices.", "error")
#         return redirect(url_for("dashboard"))

#     try:
#         with closing(get_db()) as conn:
#             existing_product = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 ORDER BY id LIMIT 1
#             """, (product_name,)).fetchone()

#             if existing_product:
#                 product_name = existing_product["product_name"]
#                 stock = conn.execute("""
#                     SELECT COALESCE(SUM(quantity), 0) AS total
#                     FROM batches WHERE LOWER(TRIM(product_name)) =
#                     LOWER(TRIM(?))
#                 """, (product_name,)).fetchone()["total"]

#                 sales = conn.execute("""
#                     SELECT COALESCE(SUM(s.quantity), 0) AS sold,
#                            COUNT(s.id) AS records
#                     FROM sales s JOIN batches b ON b.id = s.batch_id
#                     WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
#                     AND date(s.sold_at) >= date('now', '-6 days')
#                     AND date(s.sold_at) <= date('now')
#                 """, (product_name,)).fetchone()

#                 if sales["records"] > 0:
#                     required = sales["sold"]
#                     if stock >= required:
#                         flash(
#                             f"Enough stock available for {product_name}. "
#                             f"Current stock: {stock}; seven-day sales: "
#                             f"{required}. Addition blocked by the "
#                             "seven-day stock rule.",
#                             "warning"
#                         )
#                         return redirect(url_for("dashboard"))
#                     flash(
#                         f"Low stock alert for {product_name}. "
#                         f"Current stock: {stock}; seven-day sales: "
#                         f"{required}.",
#                         "warning"
#                     )
#                 else:
#                     flash(
#                         "No sales recorded in the last seven days; "
#                         "demand cannot be estimated reliably.",
#                         "warning"
#                     )

#             existing_batch = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 AND LOWER(TRIM(batch_number)) = LOWER(TRIM(?))
#                 LIMIT 1
#             """, (product_name, batch_number)).fetchone()

#             if existing_batch:
#                 if existing_batch["expiry_date"] != expiry:
#                     flash(
#                         "This batch number already exists with a "
#                         "different expiry date.",
#                         "error"
#                     )
#                     return redirect(url_for("dashboard"))

#                 conn.execute("""
#                     UPDATE batches SET quantity = quantity + ?
#                     WHERE id = ?
#                 """, (quantity, existing_batch["id"]))
#                 batch_id = existing_batch["id"]
#                 movement_type = "PURCHASE"
#             else:
#                 cursor = conn.execute("""
#                     INSERT INTO batches (
#                         product_name, category, batch_number, barcode,
#                         quantity, purchase_price, selling_price,
#                         stock_entry_date, expiry_date
#                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                 """, (
#                     product_name, category, batch_number, barcode,
#                     quantity, purchase, selling,
#                     date.today().isoformat(), expiry
#                 ))
#                 batch_id = cursor.lastrowid
#                 movement_type = "PURCHASE"

#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, ?, ?, ?)
#             """, (batch_id, movement_type, quantity, "Stock added"))
#             conn.commit()

#         flash(f"Stock saved for {product_name}, batch {batch_number}.",
#               "success")

#     except sqlite3.IntegrityError:
#         flash(
#             "Could not save the batch. Check duplicate batch numbers "
#             "and barcode values.",
#             "error"
#         )
#     except sqlite3.Error:
#         app.logger.exception("Could not add batch")
#         flash("Database error while adding stock.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # PRODUCT INSIGHTS AND BARCODE LOOKUP
# # ============================================================

# @app.route("/product-insight")
# def product_insight():
#     name = request.args.get("name", "").strip()
#     barcode = request.args.get("barcode", "").strip()

#     if not name and not barcode:
#         return jsonify({"found": False, "message": "Enter a product name or barcode."})

#     with closing(get_db()) as conn:
#         if barcode:
#             rows = conn.execute("""
#                 SELECT * FROM batches WHERE barcode = ?
#                 ORDER BY expiry_date, id
#             """, (barcode,)).fetchall()
#         else:
#             rows = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 ORDER BY expiry_date, id
#             """, (name,)).fetchall()

#         if not rows:
#             return jsonify({"found": False})

#         product_name = rows[0]["product_name"]
#         sold = conn.execute("""
#             SELECT COALESCE(SUM(s.quantity), 0) AS sold
#             FROM sales s JOIN batches b ON b.id = s.batch_id
#             WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
#             AND date(s.sold_at) >= date('now', '-6 days')
#             AND date(s.sold_at) <= date('now')
#         """, (product_name,)).fetchone()["sold"] or 0

#     total_stock = sum(r["quantity"] for r in rows)
#     average = sold / 7
#     cover = round(total_stock / average, 1) if average else None

#     if total_stock == 0:
#         advice = "No stock remains. Review demand before replenishing."
#     elif average == 0:
#         advice = "No recent sales recorded. Review demand and expiry dates."
#     elif cover <= 3:
#         advice = "Low stock cover. Review whether replenishment is needed."
#     elif cover > 30:
#         advice = "Stock may cover over 30 days of sales. Review expiry dates."
#     else:
#         advice = "Stock appears sufficient at the recent sales rate."

#     return jsonify({
#         "found": True,
#         "product_name": product_name,
#         "category": rows[0]["category"],
#         "barcode": rows[0]["barcode"],
#         "purchase_price": rows[0]["purchase_price"],
#         "selling_price": rows[0]["selling_price"],
#         "total_stock": total_stock,
#         "total_sold": sold,
#         "total_sold_7_days": sold,
#         "average_daily_sales": round(average, 2) if sold else None,
#         "stock_cover_days": cover,
#         "batches": [{
#             "batch_number": r["batch_number"],
#             "quantity": r["quantity"],
#             "expiry_date": r["expiry_date"],
#             "status": get_status(r["expiry_date"])[1]
#         } for r in rows],
#         "advice": advice
#     })


# @app.route("/barcode-lookup")
# def barcode_lookup():
#     code = request.args.get("code", "").strip()
#     if not code:
#         flash("Enter or scan a barcode.", "error")
#         return redirect(url_for("dashboard"))

#     with closing(get_db()) as conn:
#         matches = conn.execute("""
#             SELECT id FROM batches WHERE barcode = ? ORDER BY expiry_date
#         """, (code,)).fetchall()

#     if not matches:
#         flash("No batch found for that barcode.", "error")
#         return redirect(url_for("dashboard"))

#     return redirect(url_for("batch_sales", batch_id=matches[0]["id"]))


# # Keep a route name compatible with templates that use barcode_lookup.
# # ============================================================
# # UPDATE STOCK / RECORD SALES
# # ============================================================

# @app.route("/stock/<int:batch_id>", methods=["POST"])
# @manager_required
# def update_stock(batch_id):
#     try:
#         quantity = int(request.form.get("quantity", ""))
#         if quantity < 0:
#             raise ValueError

#         note = request.form.get("note", "").strip()

#         with closing(get_db()) as conn:
#             batch = conn.execute(
#                 "SELECT quantity FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()
#             if not batch:
#                 flash("Batch not found.", "error")
#                 return redirect(url_for("dashboard"))

#             change = quantity - batch["quantity"]
#             conn.execute(
#                 "UPDATE batches SET quantity = ? WHERE id = ?",
#                 (quantity, batch_id)
#             )
#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, 'ADJUSTMENT', ?, ?)
#             """, (batch_id, change, note))
#             conn.commit()

#         flash("Stock quantity updated.", "success")
#     except ValueError:
#         flash("Enter a valid non-negative quantity.", "error")
#     except sqlite3.Error:
#         app.logger.exception("Stock update failed")
#         flash("Database error while updating stock.", "error")

#     return redirect(url_for("dashboard"))


# @app.route("/sell/<int:batch_id>", methods=["POST"])
# def record_sale(batch_id):
#     try:
#         quantity = int(request.form.get("quantity_sold", ""))
#         if quantity <= 0:
#             raise ValueError("Sale quantity must be greater than zero.")

#         with closing(get_db()) as conn:
#             conn.execute("BEGIN IMMEDIATE")
#             batch = conn.execute(
#                 "SELECT * FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()

#             if batch is None:
#                 raise ValueError("Batch not found.")
#             if date.fromisoformat(batch["expiry_date"]) <= date.today():
#                 raise ValueError(
#                     "Sales are blocked for batches that expire today "
#                     "or have expired."
#                 )
#             if quantity > batch["quantity"]:
#                 raise ValueError("Not enough stock available.")

#             conn.execute("""
#                 UPDATE batches SET quantity = quantity - ? WHERE id = ?
#             """, (quantity, batch_id))
#             conn.execute("""
#                 INSERT INTO sales (batch_id, quantity) VALUES (?, ?)
#             """, (batch_id, quantity))
#             conn.commit()

#         flash("Sale recorded and stock updated.", "success")
#     except ValueError as exc:
#         flash(str(exc), "error")
#     except sqlite3.Error:
#         app.logger.exception("Sale recording failed")
#         flash("Database error while recording the sale.", "error")

#     return redirect(url_for("dashboard"))


# @app.route("/sales/batch/<int:batch_id>")
# def batch_sales(batch_id):
#     with closing(get_db()) as conn:
#         batch = conn.execute(
#             "SELECT * FROM batches WHERE id = ?", (batch_id,)
#         ).fetchone()
#         if not batch:
#             flash("Batch not found.", "error")
#             return redirect(url_for("dashboard"))

#         sales = conn.execute("""
#             SELECT * FROM sales WHERE batch_id = ?
#             ORDER BY sold_at DESC
#         """, (batch_id,)).fetchall()

#     html = """
#     <!doctype html><html lang="en"><head>
#     <meta charset="utf-8"><meta name="viewport" content="width=device-width">
#     <title>Batch Sales History | ExpiryGuard</title>
#     <style>
#     body{font-family:Arial;background:#f3f7f3;color:#20352a;margin:0;padding:24px}
#     main{max-width:900px;margin:auto;background:white;padding:24px;border-radius:12px}
#     a,button{background:#176b45;color:white;padding:10px 14px;border-radius:7px;text-decoration:none}
#     table{width:100%;border-collapse:collapse;margin-top:20px}
#     td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}
#     </style></head><body><main>
#     <h1>🌿 ExpiryGuard</h1><h2>Sales History</h2>
#     <p>Product: {{ batch['product_name'] }} · Batch: {{ batch['batch_number'] }}</p>
#     <p>Remaining stock: {{ batch['quantity'] }}</p>
#     <a href="{{ url_for('dashboard') }}">Back to Dashboard</a>
#     <table><thead><tr><th>Sale ID</th><th>Quantity</th><th>Sold at</th></tr></thead>
#     <tbody>{% for s in sales %}
#     <tr><td>{{ s['id'] }}</td><td>{{ s['quantity'] }}</td><td>{{ s['sold_at'] }}</td></tr>
#     {% else %}<tr><td colspan="3">No sales recorded for this batch.</td></tr>
#     {% endfor %}</tbody></table></main></body></html>
#     """
#     return render_template_string_compat(html, batch=batch, sales=sales)


# def render_template_string_compat(template, **context):
#     from flask import render_template_string
#     return render_template_string(template, **context)


# # ============================================================
# # STOCK MOVEMENTS
# # ============================================================

# @app.route("/stock-movement/<int:batch_id>", methods=["POST"])
# @manager_required
# def add_stock_movement(batch_id):
#     movement_type = request.form.get("movement_type", "").strip().upper()
#     note = request.form.get("note", "").strip()
#     allowed = {
#         "PURCHASE", "RETURN_IN", "DAMAGE",
#         "EXPIRED", "RETURN_OUT", "OTHER"
#     }

#     try:
#         quantity = int(request.form.get("quantity", ""))
#         if quantity <= 0:
#             raise ValueError("Quantity must be greater than zero.")
#         if movement_type not in allowed:
#             raise ValueError("Invalid stock movement type.")

#         with closing(get_db()) as conn:
#             conn.execute("BEGIN IMMEDIATE")
#             batch = conn.execute(
#                 "SELECT * FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()

#             if not batch:
#                 raise ValueError("Batch not found.")

#             if movement_type in ("PURCHASE", "RETURN_IN"):
#                 change = quantity
#             else:
#                 change = -quantity

#             new_stock = batch["quantity"] + change
#             if new_stock < 0:
#                 raise ValueError("Movement exceeds available stock.")

#             conn.execute(
#                 "UPDATE batches SET quantity = ? WHERE id = ?",
#                 (new_stock, batch_id)
#             )
#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, ?, ?, ?)
#             """, (batch_id, movement_type, change, note))
#             conn.commit()

#         flash("Stock movement recorded.", "success")
#     except ValueError as exc:
#         flash(str(exc), "error")
#     except sqlite3.Error:
#         app.logger.exception("Stock movement failed")
#         flash("Database error while recording stock movement.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # CSV IMPORT / TEMPLATE
# # ============================================================

# CSV_HEADERS = [
#     "product_name", "category", "batch_number", "barcode",
#     "quantity", "purchase_price", "selling_price", "expiry_date"
# ]


# @app.route("/download-template")
# def download_template():
#     output = io.StringIO()
#     writer = csv.writer(output)
#     writer.writerow(CSV_HEADERS)
#     writer.writerow([
#         "Rice", "Food", "RICE-001", "1234567890123",
#         "50", "40.00", "50.00", date.today().isoformat()
#     ])

#     response = make_response("\ufeff" + output.getvalue())
#     response.headers["Content-Type"] = "text/csv; charset=utf-8"
#     response.headers["Content-Disposition"] = (
#         "attachment; filename=expiryguard_inventory_template.csv"
#     )
#     return response


# @app.route("/import-csv", methods=["POST"])
# @manager_required
# def import_csv():
#     uploaded = request.files.get("file")

#     if not uploaded or not uploaded.filename:
#         flash("Choose a CSV file to import.", "error")
#         return redirect(url_for("dashboard"))

#     try:
#         content = uploaded.stream.read().decode("utf-8-sig")
#         reader = csv.DictReader(io.StringIO(content))

#         if not reader.fieldnames:
#             raise ValueError("CSV file is empty.")

#         headers = {h.strip().lower() for h in reader.fieldnames if h}
#         required = set(CSV_HEADERS) - {"barcode"}
#         if not required.issubset(headers):
#             raise ValueError(
#                 "CSV headers are missing. Download the template "
#                 "and use its column names."
#             )

#         imported = 0
#         skipped = 0
#         errors = []

#         with closing(get_db()) as conn:
#             for line_no, row in enumerate(reader, start=2):
#                 row = {
#                     (k or "").strip().lower(): (v or "").strip()
#                     for k, v in row.items()
#                 }

#                 try:
#                     name = row.get("product_name", "")
#                     category = row.get("category", "")
#                     batch_no = row.get("batch_number", "")
#                     barcode = row.get("barcode") or None
#                     qty = int(row.get("quantity", ""))
#                     purchase = float(row.get("purchase_price", ""))
#                     selling = float(row.get("selling_price", ""))
#                     expiry = row.get("expiry_date", "")

#                     if not all([name, category, batch_no, expiry]):
#                         raise ValueError("Required field missing.")
#                     date.fromisoformat(expiry)
#                     if expiry < date.today().isoformat():
#                         raise ValueError("Expiry date is in the past.")
#                     if qty <= 0 or purchase < 0 or selling < 0:
#                         raise ValueError("Invalid quantity or price.")
#                     if not math.isfinite(purchase + selling):
#                         raise ValueError("Invalid price.")

#                     duplicate = conn.execute("""
#                         SELECT id FROM batches
#                         WHERE LOWER(TRIM(product_name)) =
#                               LOWER(TRIM(?))
#                           AND LOWER(TRIM(batch_number)) =
#                               LOWER(TRIM(?))
#                     """, (name, batch_no)).fetchone()

#                     if duplicate:
#                         skipped += 1
#                         continue

#                     cursor = conn.execute("""
#                         INSERT INTO batches (
#                             product_name, category, batch_number, barcode,
#                             quantity, purchase_price, selling_price,
#                             stock_entry_date, expiry_date
#                         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                     """, (
#                         name, category, batch_no, barcode, qty,
#                         purchase, selling, date.today().isoformat(), expiry
#                     ))

#                     conn.execute("""
#                         INSERT INTO stock_movements (
#                             batch_id, movement_type, quantity_change, note
#                         ) VALUES (?, 'PURCHASE', ?, ?)
#                     """, (cursor.lastrowid, qty, "CSV import"))
#                     imported += 1

#                 except (ValueError, OverflowError) as exc:
#                     errors.append(f"Row {line_no}: {exc}")

#             conn.commit()

#         flash(
#             f"CSV import complete. Imported: {imported}; "
#             f"duplicates skipped: {skipped}; invalid rows: {len(errors)}.",
#             "success" if not errors else "warning"
#         )

#         for error in errors[:10]:
#             flash(error, "error")

#     except (UnicodeDecodeError, csv.Error, ValueError) as exc:
#         flash(f"CSV import failed: {exc}", "error")
#     except sqlite3.Error:
#         app.logger.exception("CSV import failed")
#         flash("Database error while importing CSV.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # START APPLICATION
# # ============================================================

# init_db()

# if __name__ == "__main__":
#     app.run(debug=True)














# from flask import (
#     Flask, render_template, request, redirect, url_for,
#     flash, jsonify, make_response, session, g, abort
# )
# from functools import wraps
# from werkzeug.security import generate_password_hash, check_password_hash
# import sqlite3
# import math
# import csv
# import io
# from pathlib import Path
# from datetime import date, datetime, timedelta
# from contextlib import closing

# app = Flask(__name__)
# app.secret_key = __import__("os").environ.get("EXPIRYGUARD_SECRET_KEY", "dev-only-change-this-secret-key-before-deployment")
# app.config["SESSION_COOKIE_HTTPONLY"] = True
# app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# app.config["SESSION_COOKIE_SECURE"] = __import__("os").environ.get("EXPIRYGUARD_HTTPS", "0") == "1"
# app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
# app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# BASE_DIR = Path(__file__).resolve().parent
# DB_PATH = BASE_DIR / "expiryguard.db"


# # ============================================================
# # DATABASE
# # ============================================================

# def get_db():
#     conn = sqlite3.connect(DB_PATH, timeout=10)
#     conn.row_factory = sqlite3.Row
#     conn.execute("PRAGMA foreign_keys = ON")
#     return conn


# def column_exists(conn, table, column):
#     return any(
#         row["name"] == column
#         for row in conn.execute(f"PRAGMA table_info({table})")
#     )


# def init_db():
#     with closing(get_db()) as conn:
#         conn.executescript("""
#             CREATE TABLE IF NOT EXISTS batches (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 product_name TEXT NOT NULL,
#                 category TEXT NOT NULL,
#                 batch_number TEXT NOT NULL,
#                 quantity INTEGER NOT NULL DEFAULT 0
#                     CHECK(quantity >= 0),
#                 purchase_price REAL NOT NULL DEFAULT 0
#                     CHECK(purchase_price >= 0),
#                 selling_price REAL NOT NULL DEFAULT 0
#                     CHECK(selling_price >= 0),
#                 expiry_date TEXT NOT NULL,
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 UNIQUE(product_name, batch_number)
#             );

#             CREATE TABLE IF NOT EXISTS sales (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 batch_id INTEGER NOT NULL,
#                 quantity INTEGER NOT NULL CHECK(quantity > 0),
#                 sold_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );

#             CREATE TABLE IF NOT EXISTS stock_movements (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 batch_id INTEGER NOT NULL,
#                 movement_type TEXT NOT NULL,
#                 quantity_change INTEGER NOT NULL,
#                 note TEXT DEFAULT '',
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );

#             CREATE TABLE IF NOT EXISTS users (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 username TEXT NOT NULL COLLATE NOCASE UNIQUE,
#                 email TEXT NOT NULL COLLATE NOCASE UNIQUE,
#                 password_hash TEXT NOT NULL,
#                 role TEXT NOT NULL CHECK(role IN ('Admin', 'Manager', 'Staff')),
#                 status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#             );
#         """)

#         # Add missing columns without deleting existing inventory.
#         additions = {
#             "barcode": "TEXT",
#             "stock_entry_date": "TEXT",
#         }

#         for column, definition in additions.items():
#             if not column_exists(conn, "batches", column):
#                 conn.execute(
#                     f"ALTER TABLE batches ADD COLUMN {column} {definition}"
#                 )

#         # Existing records get a reasonable entry date.
#         conn.execute("""
#             UPDATE batches
#             SET stock_entry_date = COALESCE(
#                 stock_entry_date,
#                 date(created_at),
#                 date('now')
#             )
#             WHERE stock_entry_date IS NULL OR stock_entry_date = ''
#         """)

#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_batches_expiry
#             ON batches(expiry_date)
#         """)
#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_sales_date
#             ON sales(sold_at)
#         """)
#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_movements_date
#             ON stock_movements(created_at)
#         """)

#         conn.executescript("""
#             CREATE TABLE IF NOT EXISTS suppliers (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 name TEXT NOT NULL, contact_person TEXT DEFAULT '',
#                 phone TEXT DEFAULT '', email TEXT DEFAULT '',
#                 address TEXT DEFAULT '', notes TEXT DEFAULT '',
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#             );
#             CREATE TABLE IF NOT EXISTS invoices (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 invoice_number TEXT NOT NULL UNIQUE,
#                 customer_name TEXT DEFAULT '', customer_contact TEXT DEFAULT '',
#                 subtotal REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0,
#                 created_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(created_by) REFERENCES users(id)
#             );
#             CREATE TABLE IF NOT EXISTS invoice_items (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL,
#                 batch_id INTEGER, product_name TEXT NOT NULL, batch_number TEXT DEFAULT '',
#                 quantity INTEGER NOT NULL, unit_price REAL NOT NULL, line_total REAL NOT NULL,
#                 FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );
#             CREATE TABLE IF NOT EXISTS login_attempts (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT, identity TEXT NOT NULL,
#                 attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, succeeded INTEGER NOT NULL DEFAULT 0
#             );
#             CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);
#             CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(created_at);
#         """)
#         conn.commit()


# # ============================================================
# # AUTHENTICATION
# # ============================================================

# @app.before_request
# def load_current_user():
#     """Load and validate the signed-in user before every protected request."""
#     if request.endpoint in {"login", "static"} or request.endpoint is None:
#         return None
#     if not session.get("user_id"):
#         return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
#     with closing(get_db()) as conn:
#         user = conn.execute(
#             "SELECT id, username, email, role, status FROM users WHERE id = ?",
#             (session["user_id"],)
#         ).fetchone()
#     if not user or user["status"] != "Active":
#         session.clear()
#         return redirect(url_for("login"))
#     g.current_user = dict(user)


# def require_login(view):
#     """Route decorator; global authentication is loaded by load_current_user."""
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         if not getattr(g, "current_user", None):
#             return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
#         return view(*args, **kwargs)
#     return wrapped


# @app.context_processor
# def inject_current_user():
#     return {"current_user": getattr(g, "current_user", None)}


# def admin_required(view):
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         if not getattr(g, "current_user", None) or g.current_user["role"] != "Admin":
#             abort(403)
#         return view(*args, **kwargs)
#     return wrapped


# def manager_or_admin_required(view):
#     """Allow operational inventory management to Admins and Managers only."""
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         user = getattr(g, "current_user", None)
#         if not user or user["role"] not in {"Admin", "Manager"}:
#             abort(403)
#         return view(*args, **kwargs)
#     return wrapped


# def role_view_allowed(role, module_name):
#     """Staff can view operational screens and sales, but not reports/recommendations/users."""
#     if module_name == "users":
#         return role == "Admin"
#     if module_name in {"reports", "recommendations"}:
#         return role in {"Admin", "Manager"}
#     return module_name in {"dashboard", "inventory", "products", "sales", "alerts"}


# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if session.get("user_id"):
#         return redirect(url_for("dashboard"))
#     error = None
#     if request.method == "POST":
#         identity = request.form.get("identity", "").strip()
#         password = request.form.get("password", "")
#         with closing(get_db()) as conn:
#             recent_failures = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE identity = ? AND succeeded = 0 AND attempted_at >= datetime('now', '-15 minutes')", (identity,)).fetchone()[0]
#             if recent_failures >= 8:
#                 error = "Too many unsuccessful attempts. Please wait 15 minutes before trying again."
#                 return render_template("login.html", error=error), 429
#             user = conn.execute(
#                 "SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1",
#                 (identity, identity)
#             ).fetchone()
#         if user and user["status"] == "Active" and check_password_hash(user["password_hash"], password):
#             with closing(get_db()) as conn:
#                 conn.execute("INSERT INTO login_attempts(identity, succeeded) VALUES (?, 1)", (identity,))
#                 conn.commit()
#             session.clear()
#             session.permanent = True
#             session["user_id"] = user["id"]
#             session["username"] = user["username"]
#             session["role"] = user["role"]
#             destination = request.args.get("next", "")
#             if not destination.startswith("/") or destination.startswith("//"):
#                 destination = url_for("dashboard")
#             return redirect(destination)
#         with closing(get_db()) as conn:
#             conn.execute("INSERT INTO login_attempts(identity, succeeded) VALUES (?, 0)", (identity,))
#             conn.commit()
#         error = "Invalid username/email or password, or the account is inactive."
#     return render_template("login.html", error=error)


# @app.route("/logout", methods=["POST"])
# def logout():
#     session.clear()
#     return redirect(url_for("login"))


# @app.route("/users/create", methods=["POST"])
# @admin_required
# def create_user():
#     username = request.form.get("username", "").strip()
#     email = request.form.get("email", "").strip().lower()
#     password = request.form.get("password", "")
#     role = request.form.get("role", "Staff")
#     status = request.form.get("status", "Active")
#     if (not username or len(username) > 50 or not email or len(email) > 254
#             or "@" not in email or any(ch.isspace() for ch in email)
#             or len(password) < 8
#             or role not in {"Admin", "Manager", "Staff"}
#             or status not in {"Active", "Inactive"}):
#         flash("Enter valid user details. Password must contain at least 8 characters.", "error")
#         return redirect(url_for("dashboard") + "#users")
#     try:
#         with closing(get_db()) as conn:
#             conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
#                          (username, email, generate_password_hash(password), role, status))
#             conn.commit()
#         flash(f"Account created for {username}.", "success")
#     except sqlite3.IntegrityError:
#         flash("Username or email already exists.", "error")
#     return redirect(url_for("dashboard") + "#users")


# @app.route("/users/<int:user_id>/edit", methods=["POST"])
# @admin_required
# def edit_user(user_id):
#     username = request.form.get("username", "").strip()
#     email = request.form.get("email", "").strip().lower()
#     role = request.form.get("role", "Staff")
#     password = request.form.get("password", "")

#     if (not username or len(username) > 50 or not email or len(email) > 254
#             or "@" not in email or any(ch.isspace() for ch in email)
#             or role not in {"Admin", "Manager", "Staff"}
#             or (password and len(password) < 8)):
#         flash("Enter valid user details. A new password must contain at least 8 characters.", "error")
#         return redirect(url_for("dashboard") + "#users")

#     # Prevent an administrator from accidentally removing their own admin access.
#     if user_id == g.current_user["id"] and role != "Admin":
#         flash("You cannot change your own role from Admin.", "error")
#         return redirect(url_for("dashboard") + "#users")

#     try:
#         with closing(get_db()) as conn:
#             target = conn.execute(
#                 "SELECT id, role, status FROM users WHERE id = ?", (user_id,)
#             ).fetchone()
#             if not target:
#                 flash("User not found.", "error")
#                 return redirect(url_for("dashboard") + "#users")

#             if target["role"] == "Admin" and target["status"] == "Active" and role != "Admin":
#                 active_admins = conn.execute(
#                     "SELECT COUNT(*) FROM users WHERE role = 'Admin' AND status = 'Active'"
#                 ).fetchone()[0]
#                 if active_admins <= 1:
#                     flash("The last active Admin cannot be demoted.", "error")
#                     return redirect(url_for("dashboard") + "#users")

#             if password:
#                 conn.execute(
#                     "UPDATE users SET username = ?, email = ?, role = ?, password_hash = ? WHERE id = ?",
#                     (username, email, role, generate_password_hash(password), user_id)
#                 )
#             else:
#                 conn.execute(
#                     "UPDATE users SET username = ?, email = ?, role = ? WHERE id = ?",
#                     (username, email, role, user_id)
#                 )
#             conn.commit()
#         flash("User details updated successfully.", "success")
#     except sqlite3.IntegrityError:
#         flash("That username or email is already in use.", "error")
#     return redirect(url_for("dashboard") + "#users")


# @app.route("/users/<int:user_id>/status", methods=["POST"])
# @admin_required
# def update_user_status(user_id):
#     status = request.form.get("status")
#     if status not in {"Active", "Inactive"}:
#         abort(400)
#     with closing(get_db()) as conn:
#         target = conn.execute(
#             "SELECT id, role, status FROM users WHERE id = ?", (user_id,)
#         ).fetchone()
#         if not target:
#             flash("User not found.", "error")
#         elif user_id == g.current_user["id"] and status == "Inactive":
#             flash("You cannot deactivate your own account.", "error")
#         elif target["role"] == "Admin" and target["status"] == "Active" and status == "Inactive" and conn.execute(
#             "SELECT COUNT(*) FROM users WHERE role = 'Admin' AND status = 'Active'"
#         ).fetchone()[0] <= 1:
#             flash("The last active Admin cannot be deactivated.", "error")
#         else:
#             conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
#             conn.commit()
#             flash("User status updated.", "success")
#     return redirect(url_for("dashboard") + "#users")


# @app.cli.command("create-admin")
# def create_admin_command():
#     """Create the first Admin account interactively; password is never stored in plain text."""
#     import getpass
#     username = input("Admin username: ").strip()
#     email = input("Admin email: ").strip().lower()
#     password = getpass.getpass("Admin password (minimum 8 characters): ")
#     confirm = getpass.getpass("Confirm password: ")
#     if not username or not email or len(password) < 8 or password != confirm:
#         print("Invalid details or passwords do not match.")
#         return
#     with closing(get_db()) as conn:
#         exists = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0]
#         if exists:
#             print("An Admin account already exists. Use the Users page to create accounts.")
#             return
#         try:
#             conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, 'Admin', 'Active')",
#                          (username, email, generate_password_hash(password)))
#             conn.commit()
#             print("Admin account created successfully. You can now log in.")
#         except sqlite3.IntegrityError:
#             print("That username or email is already in use.")


# # ============================================================
# # HELPERS
# # ============================================================

# def get_status(expiry_date):
#     days_left = (date.fromisoformat(str(expiry_date)[:10]) -
#                  date.today()).days

#     if days_left < 0:
#         status = "Expired"
#     elif days_left == 0:
#         status = "Expires Today"
#     elif days_left <= 7:
#         status = "Urgent"
#     elif days_left <= 30:
#         status = "Warning"
#     else:
#         status = "Safe"

#     return days_left, status


# def enrich_batch(batch):
#     item = dict(batch)
#     item["days_left"], item["status"] = get_status(item["expiry_date"])
#     item["stock_value"] = item["quantity"] * item["purchase_price"]
#     return item


# def get_product_sales(conn):
#     rows = conn.execute("""
#         SELECT
#             LOWER(TRIM(b.product_name)) AS product_key,
#             MIN(b.product_name) AS product_name,
#             SUM(b.quantity) AS total_stock,
#             COALESCE((
#                 SELECT SUM(s.quantity)
#                 FROM sales s
#                 JOIN batches bx ON bx.id = s.batch_id
#                 WHERE LOWER(TRIM(bx.product_name)) =
#                       LOWER(TRIM(b.product_name))
#                   AND date(s.sold_at) >= date('now', '-6 days')
#                   AND date(s.sold_at) <= date('now')
#             ), 0) AS sold_7_days
#         FROM batches b
#         GROUP BY LOWER(TRIM(b.product_name))
#     """).fetchall()

#     return {
#         row["product_key"]: {
#             "product_name": row["product_name"],
#             "total_stock": row["total_stock"] or 0,
#             "sold_7_days": row["sold_7_days"] or 0,
#         }
#         for row in rows
#     }


# def generate_recommendations(batches, product_sales):
#     recommendations = []

#     for batch in batches:
#         quantity = max(0, int(batch["quantity"]))
#         days = batch["days_left"]
#         key = batch["product_name"].strip().casefold()
#         sales_info = product_sales.get(key, {})
#         sold = float(sales_info.get("sold_7_days", 0))
#         daily = sold / 7
#         value = round(quantity * batch["purchase_price"], 2)

#         def add(level, title, detail, action, stock_value=value):
#             recommendations.append({
#                 "level": level,
#                 "title": title,
#                 "product": batch["product_name"],
#                 "batch": batch["batch_number"],
#                 "days_left": days,
#                 "detail": detail,
#                 "action": action,
#                 "stock_value": stock_value,
#             })

#         if quantity <= 0:
#             continue

#         if days < 0:
#             add(
#                 "critical", "Expired Stock",
#                 f"{quantity} units expired {abs(days)} day(s) ago.",
#                 "Remove from sale and follow disposal procedures."
#             )
#             continue

#         if days == 0:
#             add(
#                 "critical", "Expires Today",
#                 f"{quantity} units reach their expiry date today.",
#                 "Review immediately; do not sell once expired."
#             )
#         elif days <= 3:
#             add(
#                 "critical", "Critical Expiry Risk",
#                 f"{quantity} units remain and expire in {days} day(s).",
#                 "Review immediately and prioritize eligible stock."
#             )
#         elif days <= 7:
#             add(
#                 "urgent", "Urgent Expiry Risk",
#                 f"{quantity} units remain and expire in {days} days.",
#                 "Prioritize this batch using FEFO."
#             )
#         elif days <= 30:
#             add(
#                 "warning", "Upcoming Expiry",
#                 f"{quantity} units expire in {days} days.",
#                 "Monitor sales and replenishment."
#             )

#         if days > 0 and daily > 0:
#             at_risk = max(0, min(quantity, math.ceil(quantity - daily * days)))
#             if at_risk:
#                 add(
#                     "warning", "Potential Expiry Loss",
#                     f"Recent sales suggest approximately {at_risk} "
#                     "unit(s) may remain unsold by expiry.",
#                     "Review sales, stock placement and future orders.",
#                     round(at_risk * batch["purchase_price"], 2)
#                 )
#         elif days > 0 and sold == 0:
#             add(
#                 "info", "No Recent Sales",
#                 "No sales were recorded for this product in the last 7 days.",
#                 "Review demand manually."
#             )

#     for info in product_sales.values():
#         stock = max(0, int(info["total_stock"]))
#         daily = float(info["sold_7_days"]) / 7

#         if daily <= 0:
#             continue

#         cover = stock / daily

#         if stock > 0 and cover <= 3:
#             recommendations.append({
#                 "level": "info",
#                 "title": "Low Stock — Review Restocking",
#                 "product": info["product_name"],
#                 "batch": "All batches",
#                 "days_left": 0,
#                 "detail": f"{stock} units remain, about {cover:.1f} "
#                           "days of sales.",
#                 "action": "Review replenishment and expiry dates.",
#                 "stock_value": 0,
#             })
#         elif cover > 30:
#             recommendations.append({
#                 "level": "warning",
#                 "title": "Possible Overstock",
#                 "product": info["product_name"],
#                 "batch": "All batches",
#                 "days_left": 0,
#                 "detail": f"Current stock represents about {cover:.0f} "
#                           "days of sales.",
#                 "action": "Review purchase orders.",
#                 "stock_value": 0,
#             })

#     priority = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
#     recommendations.sort(key=lambda x: priority.get(x["level"], 4))
#     return recommendations


# def build_alerts(batches, recommendations):
#     """Build the dashboard alert feed from existing expiry statuses and recommendations.

#     Expiry dates/statuses are not recalculated here: enrich_batch/get_status remains
#     the single source of truth for Safe, Warning, Urgent, Expires Today and Expired.
#     """
#     alerts = []

#     for batch in batches:
#         quantity = max(0, int(batch.get("quantity", 0) or 0))
#         if quantity <= 0 or batch["days_left"] > 30:
#             continue

#         status = batch["status"]
#         if status == "Expired":
#             title, severity = "Expired stock", "critical"
#             detail = f"{quantity} units are past their expiry date."
#         elif status == "Expires Today":
#             title, severity = "Expires today", "critical"
#             detail = f"{quantity} units reach their expiry date today."
#         elif status == "Urgent":
#             title, severity = "Expiring within 7 days", "urgent"
#             detail = f"{quantity} units expire in {batch['days_left']} day(s)."
#         elif status == "Warning":
#             title, severity = "Expiring within 30 days", "warning"
#             detail = f"{quantity} units expire in {batch['days_left']} days."
#         else:
#             continue

#         alerts.append({
#             "title": title, "severity": severity,
#             "product": batch["product_name"], "batch": batch["batch_number"],
#             "detail": detail, "target": "inventory",
#         })

#     # Reuse existing recommendation output for stock and demand signals.
#     # Do not introduce new thresholds or a second stock/expiry calculation.
#     for item in recommendations:
#         title = item["title"]
#         if title in {"Low Stock — Review Restocking", "Possible Overstock"}:
#             alerts.append({
#                 "title": title, "severity": item["level"],
#                 "product": item["product"], "batch": item["batch"],
#                 "detail": item["detail"], "target": "recommendations",
#             })
#         elif title == "No Recent Sales":
#             alerts.append({
#                 "title": "Slow-moving signal — no recent sales",
#                 "severity": "info", "product": item["product"],
#                 "batch": item["batch"], "detail": item["detail"],
#                 "target": "recommendations",
#             })
#         elif title == "Potential Expiry Loss":
#             alerts.append({
#                 "title": title, "severity": item["level"],
#                 "product": item["product"], "batch": item["batch"],
#                 "detail": item["detail"], "target": "recommendations",
#             })

#     severity_order = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
#     alerts.sort(key=lambda item: severity_order.get(item["severity"], 4))
#     return alerts


# def dashboard_data():
#     with closing(get_db()) as conn:
#         raw_batches = conn.execute("""
#             SELECT * FROM batches
#             ORDER BY expiry_date ASC, product_name ASC
#         """).fetchall()

#         product_sales = get_product_sales(conn)

#         categories = [
#             row["category"]
#             for row in conn.execute("""
#                 SELECT DISTINCT category FROM batches
#                 ORDER BY category
#             """).fetchall()
#         ]

#         product_names = [
#             row["product_name"]
#             for row in conn.execute("""
#                 SELECT MIN(product_name) AS product_name
#                 FROM batches
#                 GROUP BY LOWER(TRIM(product_name))
#                 ORDER BY product_name
#             """).fetchall()
#         ]

#         movements = conn.execute("""
#             SELECT sm.*, b.product_name, b.batch_number
#             FROM stock_movements sm
#             JOIN batches b ON b.id = sm.batch_id
#             ORDER BY sm.id DESC
#             LIMIT 50
#         """).fetchall()

#     batches = [enrich_batch(row) for row in raw_batches]
#     recommendations = generate_recommendations(batches, product_sales)
#     alerts = build_alerts(batches, recommendations)

#     summary = {
#         "total_batches": len(batches),
#         "total_units": sum(b["quantity"] for b in batches),
#         "safe": sum(b["status"] == "Safe" for b in batches),
#         "warning": sum(b["status"] == "Warning" for b in batches),
#         "urgent": sum(
#             b["status"] in ("Urgent", "Expires Today") for b in batches
#         ),
#         "expired": sum(b["status"] == "Expired" for b in batches),
#         "potential_loss": round(sum(
#             b["stock_value"] for b in batches
#             if b["status"] in ("Urgent", "Expires Today", "Expired")
#         ), 2),
#         "average_daily_sales": round(
#             sum(x["sold_7_days"] for x in product_sales.values()) / 7, 2
#         ),
#     }

#     return {
#         "batches": batches,
#         "summary": summary,
#         "recommendations": recommendations,
#         "alerts": alerts,
#         "alert_count": len(alerts),
#         "categories": categories,
#         "product_names": product_names,
#         "movements": [dict(m) for m in movements],
#         "today": date.today().isoformat(),
#     }


# # ============================================================
# # DASHBOARD AND MODULE ROUTES
# # ============================================================

# @app.route("/")
# def dashboard():
#     data = dashboard_data()
#     if g.current_user["role"] == "Admin":
#         with closing(get_db()) as conn:
#             data["users"] = [dict(row) for row in conn.execute(
#                 "SELECT id, username, email, role, status, created_at FROM users ORDER BY id"
#             ).fetchall()]
#     else:
#         data["users"] = []
#     if g.current_user["role"] == "Staff":
#         data["recommendations"] = []
#         # Preserve existing Staff restrictions: recommendation-derived alerts
#         # are visible only to Admin and Manager roles.
#         data["alerts"] = [item for item in data["alerts"]
#                           if item["target"] != "recommendations"]
#         data["alert_count"] = len(data["alerts"])
#     return render_template("dashboard.html", **data)


# @app.route("/module/<module_name>")
# def module_view(module_name):
#     allowed = {
#         "dashboard", "inventory", "sales", "recommendations",
#         "alerts", "reports", "products", "users"
#     }
#     if module_name not in allowed or not role_view_allowed(g.current_user["role"], module_name):
#         abort(403)
#     return redirect(url_for("dashboard") + "#" + module_name)


# # ============================================================
# # ADD BATCH
# # ============================================================

# @app.route("/add", methods=["POST"])
# @manager_or_admin_required
# def add_batch():
#     product_name = request.form.get("product_name", "").strip()
#     category = request.form.get("category", "").strip()
#     batch_number = request.form.get("batch_number", "").strip()
#     barcode = request.form.get("barcode", "").strip() or None
#     expiry = request.form.get("expiry_date", "").strip()

#     try:
#         quantity = int(request.form.get("quantity", ""))
#         purchase = float(request.form.get("purchase_price", ""))
#         selling = float(request.form.get("selling_price", ""))

#         if not all((product_name, category, batch_number, expiry)):
#             raise ValueError("Fill in all required fields.")

#         date.fromisoformat(expiry)

#         if expiry < date.today().isoformat():
#             raise ValueError("Expiry date cannot be in the past.")
#         if quantity <= 0:
#             raise ValueError("Quantity must be greater than zero.")
#         if not all(map(math.isfinite, [purchase, selling])):
#             raise ValueError("Enter valid prices.")
#         if purchase < 0 or selling < 0:
#             raise ValueError("Prices cannot be negative.")

#     except (ValueError, OverflowError):
#         flash("Enter valid batch details, quantity, dates and prices.", "error")
#         return redirect(url_for("dashboard"))

#     try:
#         with closing(get_db()) as conn:
#             existing_product = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 ORDER BY id LIMIT 1
#             """, (product_name,)).fetchone()

#             if existing_product:
#                 product_name = existing_product["product_name"]
#                 stock = conn.execute("""
#                     SELECT COALESCE(SUM(quantity), 0) AS total
#                     FROM batches WHERE LOWER(TRIM(product_name)) =
#                     LOWER(TRIM(?))
#                 """, (product_name,)).fetchone()["total"]

#                 sales = conn.execute("""
#                     SELECT COALESCE(SUM(s.quantity), 0) AS sold,
#                            COUNT(s.id) AS records
#                     FROM sales s JOIN batches b ON b.id = s.batch_id
#                     WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
#                     AND date(s.sold_at) >= date('now', '-6 days')
#                     AND date(s.sold_at) <= date('now')
#                 """, (product_name,)).fetchone()

#                 if sales["records"] > 0:
#                     required = sales["sold"]
#                     if stock >= required:
#                         flash(
#                             f"Enough stock available for {product_name}. "
#                             f"Current stock: {stock}; seven-day sales: "
#                             f"{required}. Addition blocked by the "
#                             "seven-day stock rule.",
#                             "warning"
#                         )
#                         return redirect(url_for("dashboard"))
#                     flash(
#                         f"Low stock alert for {product_name}. "
#                         f"Current stock: {stock}; seven-day sales: "
#                         f"{required}.",
#                         "warning"
#                     )
#                 else:
#                     flash(
#                         "No sales recorded in the last seven days; "
#                         "demand cannot be estimated reliably.",
#                         "warning"
#                     )

#             existing_batch = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 AND LOWER(TRIM(batch_number)) = LOWER(TRIM(?))
#                 LIMIT 1
#             """, (product_name, batch_number)).fetchone()

#             if existing_batch:
#                 if existing_batch["expiry_date"] != expiry:
#                     flash(
#                         "This batch number already exists with a "
#                         "different expiry date.",
#                         "error"
#                     )
#                     return redirect(url_for("dashboard"))

#                 conn.execute("""
#                     UPDATE batches SET quantity = quantity + ?
#                     WHERE id = ?
#                 """, (quantity, existing_batch["id"]))
#                 batch_id = existing_batch["id"]
#                 movement_type = "PURCHASE"
#             else:
#                 cursor = conn.execute("""
#                     INSERT INTO batches (
#                         product_name, category, batch_number, barcode,
#                         quantity, purchase_price, selling_price,
#                         stock_entry_date, expiry_date
#                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                 """, (
#                     product_name, category, batch_number, barcode,
#                     quantity, purchase, selling,
#                     date.today().isoformat(), expiry
#                 ))
#                 batch_id = cursor.lastrowid
#                 movement_type = "PURCHASE"

#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, ?, ?, ?)
#             """, (batch_id, movement_type, quantity, "Stock added"))
#             conn.commit()

#         flash(f"Stock saved for {product_name}, batch {batch_number}.",
#               "success")

#     except sqlite3.IntegrityError:
#         flash(
#             "Could not save the batch. Check duplicate batch numbers "
#             "and barcode values.",
#             "error"
#         )
#     except sqlite3.Error:
#         app.logger.exception("Could not add batch")
#         flash("Database error while adding stock.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # PRODUCT INSIGHTS AND BARCODE LOOKUP
# # ============================================================

# @app.route("/product-insight")
# def product_insight():
#     name = request.args.get("name", "").strip()
#     barcode = request.args.get("barcode", "").strip()

#     if not name and not barcode:
#         return jsonify({"found": False, "message": "Enter a product name or barcode."})

#     with closing(get_db()) as conn:
#         if barcode:
#             rows = conn.execute("""
#                 SELECT * FROM batches WHERE barcode = ?
#                 ORDER BY expiry_date, id
#             """, (barcode,)).fetchall()
#         else:
#             rows = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 ORDER BY expiry_date, id
#             """, (name,)).fetchall()

#         if not rows:
#             return jsonify({"found": False})

#         product_name = rows[0]["product_name"]
#         sold = conn.execute("""
#             SELECT COALESCE(SUM(s.quantity), 0) AS sold
#             FROM sales s JOIN batches b ON b.id = s.batch_id
#             WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
#             AND date(s.sold_at) >= date('now', '-6 days')
#             AND date(s.sold_at) <= date('now')
#         """, (product_name,)).fetchone()["sold"] or 0

#     total_stock = sum(r["quantity"] for r in rows)
#     average = sold / 7
#     cover = round(total_stock / average, 1) if average else None

#     if total_stock == 0:
#         advice = "No stock remains. Review demand before replenishing."
#     elif average == 0:
#         advice = "No recent sales recorded. Review demand and expiry dates."
#     elif cover <= 3:
#         advice = "Low stock cover. Review whether replenishment is needed."
#     elif cover > 30:
#         advice = "Stock may cover over 30 days of sales. Review expiry dates."
#     else:
#         advice = "Stock appears sufficient at the recent sales rate."

#     return jsonify({
#         "found": True,
#         "product_name": product_name,
#         "category": rows[0]["category"],
#         "barcode": rows[0]["barcode"],
#         "purchase_price": rows[0]["purchase_price"],
#         "selling_price": rows[0]["selling_price"],
#         "total_stock": total_stock,
#         "total_sold": sold,
#         "total_sold_7_days": sold,
#         "average_daily_sales": round(average, 2) if sold else None,
#         "stock_cover_days": cover,
#         "batches": [{
#             "batch_number": r["batch_number"],
#             "quantity": r["quantity"],
#             "expiry_date": r["expiry_date"],
#             "status": get_status(r["expiry_date"])[1]
#         } for r in rows],
#         "advice": advice
#     })


# @app.route("/barcode-lookup")
# def barcode_lookup():
#     code = request.args.get("code", "").strip()
#     if not code:
#         flash("Enter or scan a barcode.", "error")
#         return redirect(url_for("dashboard"))

#     with closing(get_db()) as conn:
#         matches = conn.execute("""
#             SELECT id FROM batches WHERE barcode = ? ORDER BY expiry_date
#         """, (code,)).fetchall()

#     if not matches:
#         flash("No batch found for that barcode.", "error")
#         return redirect(url_for("dashboard"))

#     return redirect(url_for("batch_sales", batch_id=matches[0]["id"]))


# # Keep a route name compatible with templates that use barcode_lookup.
# # ============================================================
# # UPDATE STOCK / RECORD SALES
# # ============================================================

# @app.route("/stock/<int:batch_id>", methods=["POST"])
# @manager_or_admin_required
# def update_stock(batch_id):
#     try:
#         quantity = int(request.form.get("quantity", ""))
#         if quantity < 0:
#             raise ValueError

#         note = request.form.get("note", "").strip()

#         with closing(get_db()) as conn:
#             batch = conn.execute(
#                 "SELECT quantity FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()
#             if not batch:
#                 flash("Batch not found.", "error")
#                 return redirect(url_for("dashboard"))

#             change = quantity - batch["quantity"]
#             conn.execute(
#                 "UPDATE batches SET quantity = ? WHERE id = ?",
#                 (quantity, batch_id)
#             )
#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, 'ADJUSTMENT', ?, ?)
#             """, (batch_id, change, note))
#             conn.commit()

#         flash("Stock quantity updated.", "success")
#     except ValueError:
#         flash("Enter a valid non-negative quantity.", "error")
#     except sqlite3.Error:
#         app.logger.exception("Stock update failed")
#         flash("Database error while updating stock.", "error")

#     return redirect(url_for("dashboard"))


# @app.route("/sell/<int:batch_id>", methods=["POST"])
# def record_sale(batch_id):
#     try:
#         quantity = int(request.form.get("quantity_sold", ""))
#         if quantity <= 0:
#             raise ValueError("Sale quantity must be greater than zero.")

#         with closing(get_db()) as conn:
#             conn.execute("BEGIN IMMEDIATE")
#             batch = conn.execute(
#                 "SELECT * FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()

#             if batch is None:
#                 raise ValueError("Batch not found.")
#             if date.fromisoformat(batch["expiry_date"]) <= date.today():
#                 raise ValueError(
#                     "Sales are blocked for batches that expire today "
#                     "or have expired."
#                 )
#             if quantity > batch["quantity"]:
#                 raise ValueError("Not enough stock available.")

#             conn.execute("""
#                 UPDATE batches SET quantity = quantity - ? WHERE id = ?
#             """, (quantity, batch_id))
#             conn.execute("""
#                 INSERT INTO sales (batch_id, quantity) VALUES (?, ?)
#             """, (batch_id, quantity))
#             conn.commit()

#         flash("Sale recorded and stock updated.", "success")
#     except ValueError as exc:
#         flash(str(exc), "error")
#     except sqlite3.Error:
#         app.logger.exception("Sale recording failed")
#         flash("Database error while recording the sale.", "error")

#     return redirect(url_for("dashboard"))


# @app.route("/sales/batch/<int:batch_id>")
# def batch_sales(batch_id):
#     with closing(get_db()) as conn:
#         batch = conn.execute(
#             "SELECT * FROM batches WHERE id = ?", (batch_id,)
#         ).fetchone()
#         if not batch:
#             flash("Batch not found.", "error")
#             return redirect(url_for("dashboard"))

#         sales = conn.execute("""
#             SELECT * FROM sales WHERE batch_id = ?
#             ORDER BY sold_at DESC
#         """, (batch_id,)).fetchall()

#     html = """
#     <!doctype html><html lang="en"><head>
#     <meta charset="utf-8"><meta name="viewport" content="width=device-width">
#     <title>Batch Sales History | ExpiryGuard</title>
#     <style>
#     body{font-family:Arial;background:#f3f7f3;color:#20352a;margin:0;padding:24px}
#     main{max-width:900px;margin:auto;background:white;padding:24px;border-radius:12px}
#     a,button{background:#176b45;color:white;padding:10px 14px;border-radius:7px;text-decoration:none}
#     table{width:100%;border-collapse:collapse;margin-top:20px}
#     td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}
#     </style></head><body><main>
#     <h1>🌿 ExpiryGuard</h1><h2>Sales History</h2>
#     <p>Product: {{ batch['product_name'] }} · Batch: {{ batch['batch_number'] }}</p>
#     <p>Remaining stock: {{ batch['quantity'] }}</p>
#     <a href="{{ url_for('dashboard') }}">Back to Dashboard</a>
#     <table><thead><tr><th>Sale ID</th><th>Quantity</th><th>Sold at</th></tr></thead>
#     <tbody>{% for s in sales %}
#     <tr><td>{{ s['id'] }}</td><td>{{ s['quantity'] }}</td><td>{{ s['sold_at'] }}</td></tr>
#     {% else %}<tr><td colspan="3">No sales recorded for this batch.</td></tr>
#     {% endfor %}</tbody></table></main></body></html>
#     """
#     return render_template_string_compat(html, batch=batch, sales=sales)


# def render_template_string_compat(template, **context):
#     from flask import render_template_string
#     return render_template_string(template, **context)


# # ============================================================
# # STOCK MOVEMENTS
# # ============================================================

# @app.route("/stock-movement/<int:batch_id>", methods=["POST"])
# @manager_or_admin_required
# def add_stock_movement(batch_id):
#     movement_type = request.form.get("movement_type", "").strip().upper()
#     note = request.form.get("note", "").strip()
#     allowed = {
#         "PURCHASE", "RETURN_IN", "DAMAGE",
#         "EXPIRED", "RETURN_OUT", "OTHER"
#     }

#     try:
#         quantity = int(request.form.get("quantity", ""))
#         if quantity <= 0:
#             raise ValueError("Quantity must be greater than zero.")
#         if movement_type not in allowed:
#             raise ValueError("Invalid stock movement type.")

#         with closing(get_db()) as conn:
#             conn.execute("BEGIN IMMEDIATE")
#             batch = conn.execute(
#                 "SELECT * FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()

#             if not batch:
#                 raise ValueError("Batch not found.")

#             if movement_type in ("PURCHASE", "RETURN_IN"):
#                 change = quantity
#             else:
#                 change = -quantity

#             new_stock = batch["quantity"] + change
#             if new_stock < 0:
#                 raise ValueError("Movement exceeds available stock.")

#             conn.execute(
#                 "UPDATE batches SET quantity = ? WHERE id = ?",
#                 (new_stock, batch_id)
#             )
#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, ?, ?, ?)
#             """, (batch_id, movement_type, change, note))
#             conn.commit()

#         flash("Stock movement recorded.", "success")
#     except ValueError as exc:
#         flash(str(exc), "error")
#     except sqlite3.Error:
#         app.logger.exception("Stock movement failed")
#         flash("Database error while recording stock movement.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # CSV IMPORT / TEMPLATE
# # ============================================================

# CSV_HEADERS = [
#     "product_name", "category", "batch_number", "barcode",
#     "quantity", "purchase_price", "selling_price", "expiry_date"
# ]


# @app.route("/download-template")
# @manager_or_admin_required
# def download_template():
#     output = io.StringIO()
#     writer = csv.writer(output)
#     writer.writerow(CSV_HEADERS)
#     writer.writerow([
#         "Rice", "Food", "RICE-001", "1234567890123",
#         "50", "40.00", "50.00", date.today().isoformat()
#     ])

#     response = make_response("\ufeff" + output.getvalue())
#     response.headers["Content-Type"] = "text/csv; charset=utf-8"
#     response.headers["Content-Disposition"] = (
#         "attachment; filename=expiryguard_inventory_template.csv"
#     )
#     return response


# @app.route("/import-csv", methods=["POST"])
# @manager_or_admin_required
# def import_csv():
#     uploaded = request.files.get("file")

#     if not uploaded or not uploaded.filename:
#         flash("Choose a CSV file to import.", "error")
#         return redirect(url_for("dashboard"))

#     try:
#         content = uploaded.stream.read().decode("utf-8-sig")
#         reader = csv.DictReader(io.StringIO(content))

#         if not reader.fieldnames:
#             raise ValueError("CSV file is empty.")

#         headers = {h.strip().lower() for h in reader.fieldnames if h}
#         required = set(CSV_HEADERS) - {"barcode"}
#         if not required.issubset(headers):
#             raise ValueError(
#                 "CSV headers are missing. Download the template "
#                 "and use its column names."
#             )

#         imported = 0
#         skipped = 0
#         errors = []

#         with closing(get_db()) as conn:
#             for line_no, row in enumerate(reader, start=2):
#                 row = {
#                     (k or "").strip().lower(): (v or "").strip()
#                     for k, v in row.items()
#                 }

#                 try:
#                     name = row.get("product_name", "")
#                     category = row.get("category", "")
#                     batch_no = row.get("batch_number", "")
#                     barcode = row.get("barcode") or None
#                     qty = int(row.get("quantity", ""))
#                     purchase = float(row.get("purchase_price", ""))
#                     selling = float(row.get("selling_price", ""))
#                     expiry = row.get("expiry_date", "")

#                     if not all([name, category, batch_no, expiry]):
#                         raise ValueError("Required field missing.")
#                     date.fromisoformat(expiry)
#                     if expiry < date.today().isoformat():
#                         raise ValueError("Expiry date is in the past.")
#                     if qty <= 0 or purchase < 0 or selling < 0:
#                         raise ValueError("Invalid quantity or price.")
#                     if not math.isfinite(purchase + selling):
#                         raise ValueError("Invalid price.")

#                     duplicate = conn.execute("""
#                         SELECT id FROM batches
#                         WHERE LOWER(TRIM(product_name)) =
#                               LOWER(TRIM(?))
#                           AND LOWER(TRIM(batch_number)) =
#                               LOWER(TRIM(?))
#                     """, (name, batch_no)).fetchone()

#                     if duplicate:
#                         skipped += 1
#                         continue

#                     cursor = conn.execute("""
#                         INSERT INTO batches (
#                             product_name, category, batch_number, barcode,
#                             quantity, purchase_price, selling_price,
#                             stock_entry_date, expiry_date
#                         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                     """, (
#                         name, category, batch_no, barcode, qty,
#                         purchase, selling, date.today().isoformat(), expiry
#                     ))

#                     conn.execute("""
#                         INSERT INTO stock_movements (
#                             batch_id, movement_type, quantity_change, note
#                         ) VALUES (?, 'PURCHASE', ?, ?)
#                     """, (cursor.lastrowid, qty, "CSV import"))
#                     imported += 1

#                 except (ValueError, OverflowError) as exc:
#                     errors.append(f"Row {line_no}: {exc}")

#             conn.commit()

#         flash(
#             f"CSV import complete. Imported: {imported}; "
#             f"duplicates skipped: {skipped}; invalid rows: {len(errors)}.",
#             "success" if not errors else "warning"
#         )

#         for error in errors[:10]:
#             flash(error, "error")

#     except (UnicodeDecodeError, csv.Error, ValueError) as exc:
#         flash(f"CSV import failed: {exc}", "error")
#     except sqlite3.Error:
#         app.logger.exception("CSV import failed")
#         flash("Database error while importing CSV.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # ADDITIONAL EXPIRYGUARD FEATURES (additive; existing routes retained)
# # ============================================================

# @app.route("/suppliers", methods=["GET", "POST"])
# @manager_or_admin_required
# def suppliers():
#     with closing(get_db()) as conn:
#         if request.method == "POST":
#             name = request.form.get("name", "").strip()
#             if not name:
#                 flash("Supplier name is required.", "error")
#             else:
#                 conn.execute("INSERT INTO suppliers(name, contact_person, phone, email, address, notes) VALUES (?, ?, ?, ?, ?, ?)", (name, request.form.get("contact_person", "").strip(), request.form.get("phone", "").strip(), request.form.get("email", "").strip(), request.form.get("address", "").strip(), request.form.get("notes", "").strip()))
#                 conn.commit()
#                 flash("Supplier saved successfully.", "success")
#                 return redirect(url_for("suppliers"))
#         rows = [dict(r) for r in conn.execute("SELECT * FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()]
#     return render_template("suppliers.html", suppliers=rows)

# @app.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
# @admin_required
# def delete_supplier(supplier_id):
#     with closing(get_db()) as conn:
#         conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
#         conn.commit()
#     flash("Supplier deleted if it existed.", "success")
#     return redirect(url_for("suppliers"))

# @app.route("/export/inventory.csv")
# @manager_or_admin_required
# def export_inventory_csv():
#     with closing(get_db()) as conn:
#         rows = conn.execute("SELECT product_name, category, batch_number, barcode, quantity, purchase_price, selling_price, stock_entry_date, expiry_date FROM batches ORDER BY product_name, expiry_date").fetchall()
#     output = io.StringIO(newline="")
#     writer = csv.writer(output)
#     writer.writerow(["product_name", "category", "batch_number", "barcode", "quantity", "purchase_price", "selling_price", "stock_entry_date", "expiry_date"])
#     writer.writerows([tuple(row) for row in rows])
#     response = make_response(output.getvalue())
#     response.headers["Content-Type"] = "text/csv; charset=utf-8"
#     response.headers["Content-Disposition"] = "attachment; filename=expiryguard_inventory.csv"
#     return response

# @app.route("/export/inventory.xlsx")
# @manager_or_admin_required
# def export_inventory_xlsx():
#     try:
#         from openpyxl import Workbook
#         from openpyxl.utils import get_column_letter
#     except ImportError:
#         flash("Excel export requires openpyxl. Install it with: pip install openpyxl", "error")
#         return redirect(url_for("dashboard"))
#     with closing(get_db()) as conn:
#         rows = conn.execute("SELECT product_name, category, batch_number, barcode, quantity, purchase_price, selling_price, stock_entry_date, expiry_date FROM batches ORDER BY product_name, expiry_date").fetchall()
#     wb = Workbook(); ws = wb.active; ws.title = "Inventory"
#     ws.append(["Product", "Category", "Batch", "Barcode", "Quantity", "Purchase Price", "Selling Price", "Stock Entry Date", "Expiry Date"])
#     for row in rows: ws.append(list(row))
#     for col in ws.columns:
#         ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(max(len(str(c.value or "")) for c in col) + 2, 12), 32)
#     buf = io.BytesIO(); wb.save(buf); buf.seek(0)
#     response = make_response(buf.getvalue()); response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; response.headers["Content-Disposition"] = "attachment; filename=expiryguard_inventory.xlsx"
#     return response

# @app.route("/invoices/create", methods=["GET", "POST"])
# @require_login
# def create_invoice():
#     if request.method == "GET":
#         with closing(get_db()) as conn:
#             batches = [dict(r) for r in conn.execute("SELECT id, product_name, batch_number, quantity, selling_price FROM batches WHERE quantity > 0 ORDER BY product_name").fetchall()]
#         return render_template("invoice_create.html", batches=batches)
#     customer = request.form.get("customer_name", "").strip()
#     contact = request.form.get("customer_contact", "").strip()
#     try:
#         batch_id = int(request.form.get("batch_id", "")); qty = int(request.form.get("quantity", ""))
#         if qty <= 0: raise ValueError
#     except ValueError:
#         flash("Select a valid batch and quantity.", "error"); return redirect(url_for("create_invoice"))
#     with closing(get_db()) as conn:
#         batch = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
#         if not batch or batch["quantity"] < qty:
#             flash("The selected batch does not have enough available stock.", "error"); return redirect(url_for("create_invoice"))
#         total = round(float(batch["selling_price"]) * qty, 2)
#         number = "EG-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
#         cur = conn.execute("INSERT INTO invoices(invoice_number, customer_name, customer_contact, subtotal, total, created_by) VALUES (?, ?, ?, ?, ?, ?)", (number, customer, contact, total, total, g.current_user["id"]))
#         invoice_id = cur.lastrowid
#         conn.execute("INSERT INTO invoice_items(invoice_id, batch_id, product_name, batch_number, quantity, unit_price, line_total) VALUES (?, ?, ?, ?, ?, ?, ?)", (invoice_id, batch_id, batch["product_name"], batch["batch_number"], qty, batch["selling_price"], total))
#         conn.execute("UPDATE batches SET quantity = quantity - ? WHERE id = ?", (qty, batch_id))
#         conn.execute("INSERT INTO sales(batch_id, quantity) VALUES (?, ?)", (batch_id, qty))
#         conn.execute("INSERT INTO stock_movements(batch_id, movement_type, quantity_change, note) VALUES (?, 'SALE', ?, ?)", (batch_id, -qty, "Invoice " + number))
#         conn.commit()
#     return redirect(url_for("view_invoice", invoice_id=invoice_id))

# @app.route("/invoices/<int:invoice_id>")
# @require_login
# def view_invoice(invoice_id):
#     with closing(get_db()) as conn:
#         inv = conn.execute("SELECT i.*, u.username AS created_by_name FROM invoices i LEFT JOIN users u ON u.id=i.created_by WHERE i.id=?", (invoice_id,)).fetchone()
#         if not inv: abort(404)
#         items = [dict(r) for r in conn.execute("SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()]
#     return render_template("invoice_receipt.html", invoice=dict(inv), items=items)

# @app.route("/barcode/<int:batch_id>.svg")
# @require_login
# def barcode_svg(batch_id):
#     # A lightweight SVG label containing the existing barcode/batch identifier.
#     with closing(get_db()) as conn:
#         row = conn.execute("SELECT barcode, batch_number, product_name FROM batches WHERE id=?", (batch_id,)).fetchone()
#     if not row: abort(404)
#     value = row["barcode"] or row["batch_number"]
#     safe = __import__("html").escape(str(value))
#     # Deterministic visual bars for a printable inventory label; scan value is printed below.
#     bits = ''.join(f'{ord(ch):08b}' for ch in str(value))[:240]
#     bars = ''.join(f'<rect x="{i*2}" y="0" width="{1 if bit=="1" else 2}" height="54" fill="#111"/>' for i, bit in enumerate(bits) if bit == '1')
#     svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="90" viewBox="0 0 520 90"><rect width="520" height="90" fill="white"/><g transform="translate(10 5)">{bars}</g><text x="10" y="78" font-family="Arial" font-size="14">{safe}</text></svg>'
#     return app.response_class(svg, mimetype="image/svg+xml")

# @app.route("/qr/<int:batch_id>.png")
# @require_login
# def batch_qr_code(batch_id):
#     try:
#         import qrcode
#     except ImportError:
#         return "QR generation requires qrcode[pil]. Install project requirements and retry.", 501
#     with closing(get_db()) as conn:
#         row = conn.execute("SELECT id, product_name, batch_number, barcode FROM batches WHERE id=?", (batch_id,)).fetchone()
#     if not row:
#         abort(404)
#     payload = row["barcode"] or f"EXPIRYGUARD:BATCH:{row['id']}:{row['batch_number']}"
#     image = qrcode.make(str(payload))
#     output = io.BytesIO(); image.save(output, format="PNG")
#     return app.response_class(output.getvalue(), mimetype="image/png")

# @app.route("/audit/export.csv")
# @manager_or_admin_required
# def export_audit_csv():
#     with closing(get_db()) as conn:
#         rows = conn.execute("SELECT m.id, b.product_name, b.batch_number, m.movement_type, m.quantity_change, m.note, m.created_at FROM stock_movements m JOIN batches b ON b.id=m.batch_id ORDER BY m.created_at DESC").fetchall()
#     output=io.StringIO(newline=""); w=csv.writer(output); w.writerow(["ID","Product","Batch","Movement","Quantity Change","Note","Date"]); w.writerows([tuple(r) for r in rows])
#     response=make_response(output.getvalue()); response.headers["Content-Type"]="text/csv; charset=utf-8"; response.headers["Content-Disposition"]="attachment; filename=expiryguard_stock_audit.csv"; return response


# # ============================================================
# # START APPLICATION
# # ============================================================

# init_db()

# if __name__ == "__main__":
#     app.run(debug=True)











# from flask import (
#     Flask, render_template, request, redirect, url_for,
#     flash, jsonify, make_response, session, g, abort
# )
# from functools import wraps
# from werkzeug.security import generate_password_hash, check_password_hash
# import sqlite3
# import math
# import csv
# import io
# from pathlib import Path
# from datetime import date, datetime, timedelta
# from contextlib import closing

# app = Flask(__name__)
# app.secret_key = __import__("os").environ.get("EXPIRYGUARD_SECRET_KEY", "dev-only-change-this-secret-key-before-deployment")
# app.config["SESSION_COOKIE_HTTPONLY"] = True
# app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# app.config["SESSION_COOKIE_SECURE"] = __import__("os").environ.get("EXPIRYGUARD_HTTPS", "0") == "1"
# app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
# app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# BASE_DIR = Path(__file__).resolve().parent
# DB_PATH = BASE_DIR / "expiryguard.db"


# # ============================================================
# # DATABASE
# # ============================================================

# def get_db():
#     conn = sqlite3.connect(DB_PATH, timeout=10)
#     conn.row_factory = sqlite3.Row
#     conn.execute("PRAGMA foreign_keys = ON")
#     return conn


# def column_exists(conn, table, column):
#     return any(
#         row["name"] == column
#         for row in conn.execute(f"PRAGMA table_info({table})")
#     )


# def init_db():
#     with closing(get_db()) as conn:
#         conn.executescript("""
#             CREATE TABLE IF NOT EXISTS batches (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 product_name TEXT NOT NULL,
#                 category TEXT NOT NULL,
#                 batch_number TEXT NOT NULL,
#                 quantity INTEGER NOT NULL DEFAULT 0
#                     CHECK(quantity >= 0),
#                 purchase_price REAL NOT NULL DEFAULT 0
#                     CHECK(purchase_price >= 0),
#                 selling_price REAL NOT NULL DEFAULT 0
#                     CHECK(selling_price >= 0),
#                 expiry_date TEXT NOT NULL,
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 UNIQUE(product_name, batch_number)
#             );

#             CREATE TABLE IF NOT EXISTS sales (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 batch_id INTEGER NOT NULL,
#                 quantity INTEGER NOT NULL CHECK(quantity > 0),
#                 sold_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );

#             CREATE TABLE IF NOT EXISTS stock_movements (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 batch_id INTEGER NOT NULL,
#                 movement_type TEXT NOT NULL,
#                 quantity_change INTEGER NOT NULL,
#                 note TEXT DEFAULT '',
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );

#             CREATE TABLE IF NOT EXISTS users (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 username TEXT NOT NULL COLLATE NOCASE UNIQUE,
#                 email TEXT NOT NULL COLLATE NOCASE UNIQUE,
#                 password_hash TEXT NOT NULL,
#                 role TEXT NOT NULL CHECK(role IN ('Admin', 'Manager', 'Staff')),
#                 status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#             );
#         """)

#         # Add missing columns without deleting existing inventory.
#         additions = {
#             "barcode": "TEXT",
#             "stock_entry_date": "TEXT",
#         }

#         for column, definition in additions.items():
#             if not column_exists(conn, "batches", column):
#                 conn.execute(
#                     f"ALTER TABLE batches ADD COLUMN {column} {definition}"
#                 )

#         # Existing records get a reasonable entry date.
#         conn.execute("""
#             UPDATE batches
#             SET stock_entry_date = COALESCE(
#                 stock_entry_date,
#                 date(created_at),
#                 date('now')
#             )
#             WHERE stock_entry_date IS NULL OR stock_entry_date = ''
#         """)

#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_batches_expiry
#             ON batches(expiry_date)
#         """)
#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_sales_date
#             ON sales(sold_at)
#         """)
#         conn.execute("""
#             CREATE INDEX IF NOT EXISTS idx_movements_date
#             ON stock_movements(created_at)
#         """)

#         conn.executescript("""
#             CREATE TABLE IF NOT EXISTS suppliers (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 name TEXT NOT NULL, contact_person TEXT DEFAULT '',
#                 phone TEXT DEFAULT '', email TEXT DEFAULT '',
#                 address TEXT DEFAULT '', notes TEXT DEFAULT '',
#                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#             );
#             CREATE TABLE IF NOT EXISTS invoices (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 invoice_number TEXT NOT NULL UNIQUE,
#                 customer_name TEXT DEFAULT '', customer_contact TEXT DEFAULT '',
#                 subtotal REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0,
#                 created_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                 FOREIGN KEY(created_by) REFERENCES users(id)
#             );
#             CREATE TABLE IF NOT EXISTS invoice_items (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL,
#                 batch_id INTEGER, product_name TEXT NOT NULL, batch_number TEXT DEFAULT '',
#                 quantity INTEGER NOT NULL, unit_price REAL NOT NULL, line_total REAL NOT NULL,
#                 FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
#                 FOREIGN KEY(batch_id) REFERENCES batches(id)
#             );
#             CREATE TABLE IF NOT EXISTS login_attempts (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT, identity TEXT NOT NULL,
#                 attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, succeeded INTEGER NOT NULL DEFAULT 0
#             );
#             CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);
#             CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(created_at);
#         """)
#         conn.commit()


# # ============================================================
# # AUTHENTICATION
# # ============================================================

# @app.before_request
# def load_current_user():
#     """Load and validate the signed-in user before every protected request."""
#     if request.endpoint in {"login", "static"} or request.endpoint is None:
#         return None
#     if not session.get("user_id"):
#         return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
#     with closing(get_db()) as conn:
#         user = conn.execute(
#             "SELECT id, username, email, role, status FROM users WHERE id = ?",
#             (session["user_id"],)
#         ).fetchone()
#     if not user or user["status"] != "Active":
#         session.clear()
#         return redirect(url_for("login"))
#     g.current_user = dict(user)


# def require_login(view):
#     """Route decorator; global authentication is loaded by load_current_user."""
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         if not getattr(g, "current_user", None):
#             return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
#         return view(*args, **kwargs)
#     return wrapped


# @app.context_processor
# def inject_current_user():
#     return {"current_user": getattr(g, "current_user", None)}


# def admin_required(view):
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         if not getattr(g, "current_user", None) or g.current_user["role"] != "Admin":
#             abort(403)
#         return view(*args, **kwargs)
#     return wrapped


# def manager_or_admin_required(view):
#     """Allow operational inventory management to Admins and Managers only."""
#     @wraps(view)
#     def wrapped(*args, **kwargs):
#         user = getattr(g, "current_user", None)
#         if not user or user["role"] not in {"Admin", "Manager"}:
#             abort(403)
#         return view(*args, **kwargs)
#     return wrapped


# def role_view_allowed(role, module_name):
#     """Staff can view operational screens and sales, but not reports/recommendations/users."""
#     if module_name == "users":
#         return role == "Admin"
#     if module_name in {"reports", "recommendations"}:
#         return role in {"Admin", "Manager"}
#     return module_name in {"dashboard", "inventory", "products", "sales", "alerts"}


# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if session.get("user_id"):
#         return redirect(url_for("dashboard"))
#     error = None
#     if request.method == "POST":
#         identity = request.form.get("identity", "").strip()
#         password = request.form.get("password", "")
#         with closing(get_db()) as conn:
#             recent_failures = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE identity = ? AND succeeded = 0 AND attempted_at >= datetime('now', '-15 minutes')", (identity,)).fetchone()[0]
#             if recent_failures >= 8:
#                 error = "Too many unsuccessful attempts. Please wait 15 minutes before trying again."
#                 return render_template("login.html", error=error), 429
#             user = conn.execute(
#                 "SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1",
#                 (identity, identity)
#             ).fetchone()
#         if user and user["status"] == "Active" and check_password_hash(user["password_hash"], password):
#             with closing(get_db()) as conn:
#                 conn.execute("INSERT INTO login_attempts(identity, succeeded) VALUES (?, 1)", (identity,))
#                 conn.commit()
#             session.clear()
#             session.permanent = True
#             session["user_id"] = user["id"]
#             session["username"] = user["username"]
#             session["role"] = user["role"]
#             destination = request.args.get("next", "")
#             if not destination.startswith("/") or destination.startswith("//"):
#                 destination = url_for("dashboard")
#             return redirect(destination)
#         with closing(get_db()) as conn:
#             conn.execute("INSERT INTO login_attempts(identity, succeeded) VALUES (?, 0)", (identity,))
#             conn.commit()
#         error = "Invalid username/email or password, or the account is inactive."
#     return render_template("login.html", error=error)


# @app.route("/logout", methods=["POST"])
# def logout():
#     session.clear()
#     return redirect(url_for("login"))


# @app.route("/users/create", methods=["POST"])
# @admin_required
# def create_user():
#     username = request.form.get("username", "").strip()
#     email = request.form.get("email", "").strip().lower()
#     password = request.form.get("password", "")
#     role = request.form.get("role", "Staff")
#     status = request.form.get("status", "Active")
#     if (not username or len(username) > 50 or not email or len(email) > 254
#             or "@" not in email or any(ch.isspace() for ch in email)
#             or len(password) < 8
#             or role not in {"Admin", "Manager", "Staff"}
#             or status not in {"Active", "Inactive"}):
#         flash("Enter valid user details. Password must contain at least 8 characters.", "error")
#         return redirect(url_for("dashboard") + "#users")
#     try:
#         with closing(get_db()) as conn:
#             conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
#                          (username, email, generate_password_hash(password), role, status))
#             conn.commit()
#         flash(f"Account created for {username}.", "success")
#     except sqlite3.IntegrityError:
#         flash("Username or email already exists.", "error")
#     return redirect(url_for("dashboard") + "#users")


# @app.route("/users/<int:user_id>/edit", methods=["POST"])
# @admin_required
# def edit_user(user_id):
#     username = request.form.get("username", "").strip()
#     email = request.form.get("email", "").strip().lower()
#     role = request.form.get("role", "Staff")
#     password = request.form.get("password", "")

#     if (not username or len(username) > 50 or not email or len(email) > 254
#             or "@" not in email or any(ch.isspace() for ch in email)
#             or role not in {"Admin", "Manager", "Staff"}
#             or (password and len(password) < 8)):
#         flash("Enter valid user details. A new password must contain at least 8 characters.", "error")
#         return redirect(url_for("dashboard") + "#users")

#     # Prevent an administrator from accidentally removing their own admin access.
#     if user_id == g.current_user["id"] and role != "Admin":
#         flash("You cannot change your own role from Admin.", "error")
#         return redirect(url_for("dashboard") + "#users")

#     try:
#         with closing(get_db()) as conn:
#             target = conn.execute(
#                 "SELECT id, role, status FROM users WHERE id = ?", (user_id,)
#             ).fetchone()
#             if not target:
#                 flash("User not found.", "error")
#                 return redirect(url_for("dashboard") + "#users")

#             if target["role"] == "Admin" and target["status"] == "Active" and role != "Admin":
#                 active_admins = conn.execute(
#                     "SELECT COUNT(*) FROM users WHERE role = 'Admin' AND status = 'Active'"
#                 ).fetchone()[0]
#                 if active_admins <= 1:
#                     flash("The last active Admin cannot be demoted.", "error")
#                     return redirect(url_for("dashboard") + "#users")

#             if password:
#                 conn.execute(
#                     "UPDATE users SET username = ?, email = ?, role = ?, password_hash = ? WHERE id = ?",
#                     (username, email, role, generate_password_hash(password), user_id)
#                 )
#             else:
#                 conn.execute(
#                     "UPDATE users SET username = ?, email = ?, role = ? WHERE id = ?",
#                     (username, email, role, user_id)
#                 )
#             conn.commit()
#         flash("User details updated successfully.", "success")
#     except sqlite3.IntegrityError:
#         flash("That username or email is already in use.", "error")
#     return redirect(url_for("dashboard") + "#users")


# @app.route("/users/<int:user_id>/status", methods=["POST"])
# @admin_required
# def update_user_status(user_id):
#     status = request.form.get("status")
#     if status not in {"Active", "Inactive"}:
#         abort(400)
#     with closing(get_db()) as conn:
#         target = conn.execute(
#             "SELECT id, role, status FROM users WHERE id = ?", (user_id,)
#         ).fetchone()
#         if not target:
#             flash("User not found.", "error")
#         elif user_id == g.current_user["id"] and status == "Inactive":
#             flash("You cannot deactivate your own account.", "error")
#         elif target["role"] == "Admin" and target["status"] == "Active" and status == "Inactive" and conn.execute(
#             "SELECT COUNT(*) FROM users WHERE role = 'Admin' AND status = 'Active'"
#         ).fetchone()[0] <= 1:
#             flash("The last active Admin cannot be deactivated.", "error")
#         else:
#             conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
#             conn.commit()
#             flash("User status updated.", "success")
#     return redirect(url_for("dashboard") + "#users")


# @app.cli.command("create-admin")
# def create_admin_command():
#     """Create the first Admin account interactively; password is never stored in plain text."""
#     import getpass
#     username = input("Admin username: ").strip()
#     email = input("Admin email: ").strip().lower()
#     password = getpass.getpass("Admin password (minimum 8 characters): ")
#     confirm = getpass.getpass("Confirm password: ")
#     if not username or not email or len(password) < 8 or password != confirm:
#         print("Invalid details or passwords do not match.")
#         return
#     with closing(get_db()) as conn:
#         exists = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0]
#         if exists:
#             print("An Admin account already exists. Use the Users page to create accounts.")
#             return
#         try:
#             conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, 'Admin', 'Active')",
#                          (username, email, generate_password_hash(password)))
#             conn.commit()
#             print("Admin account created successfully. You can now log in.")
#         except sqlite3.IntegrityError:
#             print("That username or email is already in use.")


# # ============================================================
# # HELPERS
# # ============================================================

# def get_status(expiry_date):
#     days_left = (date.fromisoformat(str(expiry_date)[:10]) -
#                  date.today()).days

#     if days_left < 0:
#         status = "Expired"
#     elif days_left == 0:
#         status = "Expires Today"
#     elif days_left <= 7:
#         status = "Urgent"
#     elif days_left <= 30:
#         status = "Warning"
#     else:
#         status = "Safe"

#     return days_left, status


# def enrich_batch(batch):
#     item = dict(batch)
#     item["days_left"], item["status"] = get_status(item["expiry_date"])
#     # Availability is independent of expiry status: zero stock must not
#     # overwrite Safe/Warning/Urgent/Expires Today/Expired calculations.
#     item["availability"] = (
#         "Stock Not Available" if int(item["quantity"] or 0) <= 0
#         else "In Stock"
#     )
#     item["stock_value"] = item["quantity"] * item["purchase_price"]
#     return item


# def get_product_sales(conn):
#     rows = conn.execute("""
#         SELECT
#             LOWER(TRIM(b.product_name)) AS product_key,
#             MIN(b.product_name) AS product_name,
#             SUM(b.quantity) AS total_stock,
#             COALESCE((
#                 SELECT SUM(s.quantity)
#                 FROM sales s
#                 JOIN batches bx ON bx.id = s.batch_id
#                 WHERE LOWER(TRIM(bx.product_name)) =
#                       LOWER(TRIM(b.product_name))
#                   AND date(s.sold_at) >= date('now', '-6 days')
#                   AND date(s.sold_at) <= date('now')
#             ), 0) AS sold_7_days
#         FROM batches b
#         GROUP BY LOWER(TRIM(b.product_name))
#     """).fetchall()

#     return {
#         row["product_key"]: {
#             "product_name": row["product_name"],
#             "total_stock": row["total_stock"] or 0,
#             "sold_7_days": row["sold_7_days"] or 0,
#         }
#         for row in rows
#     }


# def generate_recommendations(batches, product_sales):
#     recommendations = []

#     for batch in batches:
#         quantity = max(0, int(batch["quantity"]))
#         days = batch["days_left"]
#         key = batch["product_name"].strip().casefold()
#         sales_info = product_sales.get(key, {})
#         sold = float(sales_info.get("sold_7_days", 0))
#         daily = sold / 7
#         value = round(quantity * batch["purchase_price"], 2)

#         def recommendation_category(title):
#             title_text = str(title).casefold()
#             if "loss" in title_text:
#                 return "Loss"
#             if any(word in title_text for word in ("expiry", "expired", "expires")):
#                 return "Expiry"
#             if any(word in title_text for word in ("sales", "demand")):
#                 return "Sales"
#             return "Stock"

#         def add(level, title, detail, action, stock_value=value):
#             recommendations.append({
#                 "level": level,
#                 "title": title,
#                 "product": batch["product_name"],
#                 "batch": batch["batch_number"],
#                 "batch_id": batch["id"],
#                 "quantity": quantity,
#                 "days_left": days,
#                 "category": recommendation_category(title),
#                 "detail": detail,
#                 "action": action,
#                 "stock_value": stock_value,
#             })

#         if quantity <= 0:
#             add(
#                 "critical", "Stock Not Available",
#                 "This batch currently has no available stock.",
#                 "Review recent sales and stock movements before replenishing.",
#                 0
#             )
#             continue

#         if days < 0:
#             add(
#                 "critical", "Expired Stock",
#                 f"{quantity} units expired {abs(days)} day(s) ago.",
#                 "Remove from sale and follow disposal procedures."
#             )
#             continue

#         if days == 0:
#             add(
#                 "critical", "Expires Today",
#                 f"{quantity} units reach their expiry date today.",
#                 "Review immediately; do not sell once expired."
#             )
#         elif days <= 3:
#             add(
#                 "critical", "Critical Expiry Risk",
#                 f"{quantity} units remain and expire in {days} day(s).",
#                 "Review immediately and prioritize eligible stock."
#             )
#         elif days <= 7:
#             add(
#                 "urgent", "Urgent Expiry Risk",
#                 f"{quantity} units remain and expire in {days} days.",
#                 "Prioritize this batch using FEFO."
#             )
#         elif days <= 30:
#             add(
#                 "warning", "Upcoming Expiry",
#                 f"{quantity} units expire in {days} days.",
#                 "Monitor sales and replenishment."
#             )

#         if days > 0 and daily > 0:
#             at_risk = max(0, min(quantity, math.ceil(quantity - daily * days)))
#             if at_risk:
#                 add(
#                     "warning", "Potential Expiry Loss",
#                     f"Recent sales suggest approximately {at_risk} "
#                     "unit(s) may remain unsold by expiry.",
#                     "Review sales, stock placement and future orders.",
#                     round(at_risk * batch["purchase_price"], 2)
#                 )
#         elif days > 0 and sold == 0:
#             add(
#                 "info", "No Recent Sales",
#                 "No sales were recorded for this product in the last 7 days.",
#                 "Review demand manually."
#             )

#     for info in product_sales.values():
#         stock = max(0, int(info["total_stock"]))
#         daily = float(info["sold_7_days"]) / 7

#         if daily <= 0:
#             continue

#         cover = stock / daily

#         if stock > 0 and cover <= 3:
#             recommendations.append({
#                 "level": "info",
#                 "title": "Low Stock — Review Restocking",
#                 "product": info["product_name"],
#                 "batch": "All batches",
#                 "days_left": 0,
#                 "category": "Stock",
#                 "quantity": stock,
#                 "batch_id": None,
#                 "detail": f"{stock} units remain, about {cover:.1f} "
#                           "days of sales.",
#                 "action": "Review replenishment and expiry dates.",
#                 "stock_value": 0,
#             })
#         elif cover > 30:
#             recommendations.append({
#                 "level": "warning",
#                 "title": "Possible Overstock",
#                 "product": info["product_name"],
#                 "batch": "All batches",
#                 "days_left": 0,
#                 "category": "Stock",
#                 "quantity": stock,
#                 "batch_id": None,
#                 "detail": f"Current stock represents about {cover:.0f} "
#                           "days of sales.",
#                 "action": "Review purchase orders.",
#                 "stock_value": 0,
#             })

#     priority = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
#     recommendations.sort(key=lambda x: priority.get(x["level"], 4))
#     return recommendations


# def build_alerts(batches, recommendations):
#     """Build the dashboard alert feed from existing expiry statuses and recommendations.

#     Expiry dates/statuses are not recalculated here: enrich_batch/get_status remains
#     the single source of truth for Safe, Warning, Urgent, Expires Today and Expired.
#     """
#     alerts = []

#     for batch in batches:
#         quantity = max(0, int(batch.get("quantity", 0) or 0))
#         if quantity <= 0 or batch["days_left"] > 30:
#             continue

#         status = batch["status"]
#         if status == "Expired":
#             title, severity = "Expired stock", "critical"
#             detail = f"{quantity} units are past their expiry date."
#         elif status == "Expires Today":
#             title, severity = "Expires today", "critical"
#             detail = f"{quantity} units reach their expiry date today."
#         elif status == "Urgent":
#             title, severity = "Expiring within 7 days", "urgent"
#             detail = f"{quantity} units expire in {batch['days_left']} day(s)."
#         elif status == "Warning":
#             title, severity = "Expiring within 30 days", "warning"
#             detail = f"{quantity} units expire in {batch['days_left']} days."
#         else:
#             continue

#         alerts.append({
#             "title": title, "severity": severity,
#             "product": batch["product_name"], "batch": batch["batch_number"],
#             "detail": detail, "target": "inventory",
#         })

#     # Reuse existing recommendation output for stock and demand signals.
#     # Do not introduce new thresholds or a second stock/expiry calculation.
#     for item in recommendations:
#         title = item["title"]
#         if title in {"Low Stock — Review Restocking", "Possible Overstock"}:
#             alerts.append({
#                 "title": title, "severity": item["level"],
#                 "product": item["product"], "batch": item["batch"],
#                 "detail": item["detail"], "target": "recommendations",
#             })
#         elif title == "No Recent Sales":
#             alerts.append({
#                 "title": "Slow-moving signal — no recent sales",
#                 "severity": "info", "product": item["product"],
#                 "batch": item["batch"], "detail": item["detail"],
#                 "target": "recommendations",
#             })
#         elif title == "Potential Expiry Loss":
#             alerts.append({
#                 "title": title, "severity": item["level"],
#                 "product": item["product"], "batch": item["batch"],
#                 "detail": item["detail"], "target": "recommendations",
#             })

#     severity_order = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
#     alerts.sort(key=lambda item: severity_order.get(item["severity"], 4))
#     return alerts


# def dashboard_data():
#     with closing(get_db()) as conn:
#         raw_batches = conn.execute("""
#             SELECT * FROM batches
#             ORDER BY expiry_date ASC, product_name ASC
#         """).fetchall()

#         product_sales = get_product_sales(conn)

#         categories = [
#             row["category"]
#             for row in conn.execute("""
#                 SELECT DISTINCT category FROM batches
#                 ORDER BY category
#             """).fetchall()
#         ]

#         product_names = [
#             row["product_name"]
#             for row in conn.execute("""
#                 SELECT MIN(product_name) AS product_name
#                 FROM batches
#                 GROUP BY LOWER(TRIM(product_name))
#                 ORDER BY product_name
#             """).fetchall()
#         ]

#         movements = conn.execute("""
#             SELECT sm.*, b.product_name, b.batch_number
#             FROM stock_movements sm
#             JOIN batches b ON b.id = sm.batch_id
#             ORDER BY sm.id DESC
#             LIMIT 50
#         """).fetchall()

#     batches = [enrich_batch(row) for row in raw_batches]
#     recommendations = generate_recommendations(batches, product_sales)
#     alerts = build_alerts(batches, recommendations)

#     summary = {
#         "total_batches": len(batches),
#         "total_units": sum(b["quantity"] for b in batches),
#         "safe": sum(b["status"] == "Safe" for b in batches),
#         "warning": sum(b["status"] == "Warning" for b in batches),
#         "urgent": sum(
#             b["status"] in ("Urgent", "Expires Today") for b in batches
#         ),
#         "expired": sum(b["status"] == "Expired" for b in batches),
#         "potential_loss": round(sum(
#             b["stock_value"] for b in batches
#             if b["status"] in ("Urgent", "Expires Today", "Expired")
#         ), 2),
#         "average_daily_sales": round(
#             sum(x["sold_7_days"] for x in product_sales.values()) / 7, 2
#         ),
#     }

#     return {
#         "batches": batches,
#         "summary": summary,
#         "recommendations": recommendations,
#         "recommendation_categories": sorted({
#             item.get("category", "Stock") for item in recommendations
#         }, key=lambda value: ["Stock", "Expiry", "Risk", "Loss", "Sales"].index(value)
#         if value in ["Stock", "Expiry", "Risk", "Loss", "Sales"] else value),
#         "alerts": alerts,
#         "alert_count": len(alerts),
#         "categories": categories,
#         "product_names": product_names,
#         "movements": [dict(m) for m in movements],
#         "today": date.today().isoformat(),
#     }


# # ============================================================
# # DASHBOARD AND MODULE ROUTES
# # ============================================================

# @app.route("/")
# def dashboard():
#     data = dashboard_data()
#     if g.current_user["role"] == "Admin":
#         with closing(get_db()) as conn:
#             data["users"] = [dict(row) for row in conn.execute(
#                 "SELECT id, username, email, role, status, created_at FROM users ORDER BY id"
#             ).fetchall()]
#     else:
#         data["users"] = []
#     if g.current_user["role"] == "Staff":
#         data["recommendations"] = []
#         # Preserve existing Staff restrictions: recommendation-derived alerts
#         # are visible only to Admin and Manager roles.
#         data["alerts"] = [item for item in data["alerts"]
#                           if item["target"] != "recommendations"]
#         data["alert_count"] = len(data["alerts"])
#     return render_template("dashboard.html", **data)


# @app.route("/module/<module_name>")
# def module_view(module_name):
#     allowed = {
#         "dashboard", "inventory", "sales", "recommendations",
#         "alerts", "reports", "products", "users"
#     }
#     if module_name not in allowed or not role_view_allowed(g.current_user["role"], module_name):
#         abort(403)
#     return redirect(url_for("dashboard") + "#" + module_name)


# # ============================================================
# # ADD BATCH
# # ============================================================

# @app.route("/add", methods=["POST"])
# @manager_or_admin_required
# def add_batch():
#     product_name = request.form.get("product_name", "").strip()
#     category = request.form.get("category", "").strip()
#     batch_number = request.form.get("batch_number", "").strip()
#     barcode = request.form.get("barcode", "").strip() or None
#     expiry = request.form.get("expiry_date", "").strip()

#     try:
#         quantity = int(request.form.get("quantity", ""))
#         purchase = float(request.form.get("purchase_price", ""))
#         selling = float(request.form.get("selling_price", ""))

#         if not all((product_name, category, batch_number, expiry)):
#             raise ValueError("Fill in all required fields.")

#         date.fromisoformat(expiry)

#         if expiry < date.today().isoformat():
#             raise ValueError("Expiry date cannot be in the past.")
#         if quantity <= 0:
#             raise ValueError("Quantity must be greater than zero.")
#         if not all(map(math.isfinite, [purchase, selling])):
#             raise ValueError("Enter valid prices.")
#         if purchase < 0 or selling < 0:
#             raise ValueError("Prices cannot be negative.")

#     except (ValueError, OverflowError):
#         flash("Enter valid batch details, quantity, dates and prices.", "error")
#         return redirect(url_for("dashboard"))

#     try:
#         with closing(get_db()) as conn:
#             existing_product = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 ORDER BY id LIMIT 1
#             """, (product_name,)).fetchone()

#             if existing_product:
#                 product_name = existing_product["product_name"]
#                 stock = conn.execute("""
#                     SELECT COALESCE(SUM(quantity), 0) AS total
#                     FROM batches WHERE LOWER(TRIM(product_name)) =
#                     LOWER(TRIM(?))
#                 """, (product_name,)).fetchone()["total"]

#                 sales = conn.execute("""
#                     SELECT COALESCE(SUM(s.quantity), 0) AS sold,
#                            COUNT(s.id) AS records
#                     FROM sales s JOIN batches b ON b.id = s.batch_id
#                     WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
#                     AND date(s.sold_at) >= date('now', '-6 days')
#                     AND date(s.sold_at) <= date('now')
#                 """, (product_name,)).fetchone()

#                 if sales["records"] > 0:
#                     required = sales["sold"]
#                     if stock >= required:
#                         flash(
#                             f"Enough stock available for {product_name}. "
#                             f"Current stock: {stock}; seven-day sales: "
#                             f"{required}. Addition blocked by the "
#                             "seven-day stock rule.",
#                             "warning"
#                         )
#                         return redirect(url_for("dashboard"))
#                     flash(
#                         f"Low stock alert for {product_name}. "
#                         f"Current stock: {stock}; seven-day sales: "
#                         f"{required}.",
#                         "warning"
#                     )
#                 else:
#                     flash(
#                         "No sales recorded in the last seven days; "
#                         "demand cannot be estimated reliably.",
#                         "warning"
#                     )

#             existing_batch = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 AND LOWER(TRIM(batch_number)) = LOWER(TRIM(?))
#                 LIMIT 1
#             """, (product_name, batch_number)).fetchone()

#             if existing_batch:
#                 if existing_batch["expiry_date"] != expiry:
#                     flash(
#                         "This batch number already exists with a "
#                         "different expiry date.",
#                         "error"
#                     )
#                     return redirect(url_for("dashboard"))

#                 conn.execute("""
#                     UPDATE batches SET quantity = quantity + ?
#                     WHERE id = ?
#                 """, (quantity, existing_batch["id"]))
#                 batch_id = existing_batch["id"]
#                 movement_type = "PURCHASE"
#             else:
#                 cursor = conn.execute("""
#                     INSERT INTO batches (
#                         product_name, category, batch_number, barcode,
#                         quantity, purchase_price, selling_price,
#                         stock_entry_date, expiry_date
#                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                 """, (
#                     product_name, category, batch_number, barcode,
#                     quantity, purchase, selling,
#                     date.today().isoformat(), expiry
#                 ))
#                 batch_id = cursor.lastrowid
#                 movement_type = "PURCHASE"

#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, ?, ?, ?)
#             """, (batch_id, movement_type, quantity, "Stock added"))
#             conn.commit()

#         flash(f"Stock saved for {product_name}, batch {batch_number}.",
#               "success")

#     except sqlite3.IntegrityError:
#         flash(
#             "Could not save the batch. Check duplicate batch numbers "
#             "and barcode values.",
#             "error"
#         )
#     except sqlite3.Error:
#         app.logger.exception("Could not add batch")
#         flash("Database error while adding stock.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # PRODUCT INSIGHTS AND BARCODE LOOKUP
# # ============================================================

# @app.route("/product-insight")
# def product_insight():
#     name = request.args.get("name", "").strip()
#     barcode = request.args.get("barcode", "").strip()

#     if not name and not barcode:
#         return jsonify({"found": False, "message": "Enter a product name or barcode."})

#     with closing(get_db()) as conn:
#         if barcode:
#             rows = conn.execute("""
#                 SELECT * FROM batches WHERE barcode = ?
#                 ORDER BY expiry_date, id
#             """, (barcode,)).fetchall()
#         else:
#             rows = conn.execute("""
#                 SELECT * FROM batches
#                 WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
#                 ORDER BY expiry_date, id
#             """, (name,)).fetchall()

#         if not rows:
#             return jsonify({"found": False})

#         product_name = rows[0]["product_name"]
#         sold = conn.execute("""
#             SELECT COALESCE(SUM(s.quantity), 0) AS sold
#             FROM sales s JOIN batches b ON b.id = s.batch_id
#             WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
#             AND date(s.sold_at) >= date('now', '-6 days')
#             AND date(s.sold_at) <= date('now')
#         """, (product_name,)).fetchone()["sold"] or 0

#     total_stock = sum(r["quantity"] for r in rows)
#     average = sold / 7
#     cover = round(total_stock / average, 1) if average else None

#     if total_stock == 0:
#         advice = "No stock remains. Review demand before replenishing."
#     elif average == 0:
#         advice = "No recent sales recorded. Review demand and expiry dates."
#     elif cover <= 3:
#         advice = "Low stock cover. Review whether replenishment is needed."
#     elif cover > 30:
#         advice = "Stock may cover over 30 days of sales. Review expiry dates."
#     else:
#         advice = "Stock appears sufficient at the recent sales rate."

#     return jsonify({
#         "found": True,
#         "product_name": product_name,
#         "category": rows[0]["category"],
#         "barcode": rows[0]["barcode"],
#         "purchase_price": rows[0]["purchase_price"],
#         "selling_price": rows[0]["selling_price"],
#         "total_stock": total_stock,
#         "availability": "Stock Not Available" if total_stock <= 0 else "In Stock",
#         "total_sold": sold,
#         "total_sold_7_days": sold,
#         "average_daily_sales": round(average, 2) if sold else None,
#         "stock_cover_days": cover,
#         "batches": [{
#             "batch_number": r["batch_number"],
#             "quantity": r["quantity"],
#             "expiry_date": r["expiry_date"],
#             "status": get_status(r["expiry_date"])[1],
#             "availability": "Stock Not Available" if r["quantity"] <= 0 else "In Stock"
#         } for r in rows],
#         "advice": advice
#     })


# @app.route("/barcode-lookup")
# def barcode_lookup():
#     code = request.args.get("code", "").strip()
#     if not code:
#         flash("Enter or scan a barcode.", "error")
#         return redirect(url_for("dashboard"))

#     with closing(get_db()) as conn:
#         matches = conn.execute("""
#             SELECT id FROM batches WHERE barcode = ? ORDER BY expiry_date
#         """, (code,)).fetchall()

#     if not matches:
#         flash("No batch found for that barcode.", "error")
#         return redirect(url_for("dashboard"))

#     return redirect(url_for("batch_sales", batch_id=matches[0]["id"]))


# # Keep a route name compatible with templates that use barcode_lookup.
# # ============================================================
# # UPDATE STOCK / RECORD SALES
# # ============================================================

# @app.route("/stock/<int:batch_id>", methods=["POST"])
# @manager_or_admin_required
# def update_stock(batch_id):
#     try:
#         quantity = int(request.form.get("quantity", ""))
#         if quantity < 0:
#             raise ValueError

#         note = request.form.get("note", "").strip()

#         with closing(get_db()) as conn:
#             batch = conn.execute(
#                 "SELECT quantity FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()
#             if not batch:
#                 flash("Batch not found.", "error")
#                 return redirect(url_for("dashboard"))

#             change = quantity - batch["quantity"]
#             conn.execute(
#                 "UPDATE batches SET quantity = ? WHERE id = ?",
#                 (quantity, batch_id)
#             )
#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, 'ADJUSTMENT', ?, ?)
#             """, (batch_id, change, note))
#             conn.commit()

#         flash("Stock quantity updated.", "success")
#     except ValueError:
#         flash("Enter a valid non-negative quantity.", "error")
#     except sqlite3.Error:
#         app.logger.exception("Stock update failed")
#         flash("Database error while updating stock.", "error")

#     return redirect(url_for("dashboard"))


# @app.route("/sell/<int:batch_id>", methods=["POST"])
# def record_sale(batch_id):
#     try:
#         quantity = int(request.form.get("quantity_sold", ""))
#         if quantity <= 0:
#             raise ValueError("Sale quantity must be greater than zero.")

#         with closing(get_db()) as conn:
#             conn.execute("BEGIN IMMEDIATE")
#             batch = conn.execute(
#                 "SELECT * FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()

#             if batch is None:
#                 raise ValueError("Batch not found.")
#             if date.fromisoformat(batch["expiry_date"]) <= date.today():
#                 raise ValueError(
#                     "Sales are blocked for batches that expire today "
#                     "or have expired."
#                 )
#             if quantity > batch["quantity"]:
#                 raise ValueError("Not enough stock available.")

#             conn.execute("""
#                 UPDATE batches SET quantity = quantity - ? WHERE id = ?
#             """, (quantity, batch_id))
#             conn.execute("""
#                 INSERT INTO sales (batch_id, quantity) VALUES (?, ?)
#             """, (batch_id, quantity))
#             conn.commit()

#         flash("Sale recorded and stock updated.", "success")
#     except ValueError as exc:
#         flash(str(exc), "error")
#     except sqlite3.Error:
#         app.logger.exception("Sale recording failed")
#         flash("Database error while recording the sale.", "error")

#     return redirect(url_for("dashboard"))


# @app.route("/sales/batch/<int:batch_id>")
# def batch_sales(batch_id):
#     with closing(get_db()) as conn:
#         batch = conn.execute(
#             "SELECT * FROM batches WHERE id = ?", (batch_id,)
#         ).fetchone()
#         if not batch:
#             flash("Batch not found.", "error")
#             return redirect(url_for("dashboard"))

#         sales = conn.execute("""
#             SELECT * FROM sales WHERE batch_id = ?
#             ORDER BY sold_at DESC
#         """, (batch_id,)).fetchall()

#     html = """
#     <!doctype html><html lang="en"><head>
#     <meta charset="utf-8"><meta name="viewport" content="width=device-width">
#     <title>Batch Sales History | ExpiryGuard</title>
#     <style>
#     body{font-family:Arial;background:#f3f7f3;color:#20352a;margin:0;padding:24px}
#     main{max-width:900px;margin:auto;background:white;padding:24px;border-radius:12px}
#     a,button{background:#176b45;color:white;padding:10px 14px;border-radius:7px;text-decoration:none}
#     table{width:100%;border-collapse:collapse;margin-top:20px}
#     td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}
#     </style></head><body><main>
#     <h1>🌿 ExpiryGuard</h1><h2>Sales History</h2>
#     <p>Product: {{ batch['product_name'] }} · Batch: {{ batch['batch_number'] }}</p>
#     <p>Remaining stock: {{ batch['quantity'] }}</p>
#     <a href="{{ url_for('dashboard') }}">Back to Dashboard</a>
#     <table><thead><tr><th>Sale ID</th><th>Quantity</th><th>Sold at</th></tr></thead>
#     <tbody>{% for s in sales %}
#     <tr><td>{{ s['id'] }}</td><td>{{ s['quantity'] }}</td><td>{{ s['sold_at'] }}</td></tr>
#     {% else %}<tr><td colspan="3">No sales recorded for this batch.</td></tr>
#     {% endfor %}</tbody></table></main></body></html>
#     """
#     return render_template_string_compat(html, batch=batch, sales=sales)


# def render_template_string_compat(template, **context):
#     from flask import render_template_string
#     return render_template_string(template, **context)


# # ============================================================
# # STOCK MOVEMENTS
# # ============================================================

# @app.route("/stock-movement/<int:batch_id>", methods=["POST"])
# @manager_or_admin_required
# def add_stock_movement(batch_id):
#     movement_type = request.form.get("movement_type", "").strip().upper()
#     note = request.form.get("note", "").strip()
#     allowed = {
#         "PURCHASE", "RETURN_IN", "DAMAGE",
#         "EXPIRED", "RETURN_OUT", "OTHER"
#     }

#     try:
#         quantity = int(request.form.get("quantity", ""))
#         if quantity <= 0:
#             raise ValueError("Quantity must be greater than zero.")
#         if movement_type not in allowed:
#             raise ValueError("Invalid stock movement type.")

#         with closing(get_db()) as conn:
#             conn.execute("BEGIN IMMEDIATE")
#             batch = conn.execute(
#                 "SELECT * FROM batches WHERE id = ?", (batch_id,)
#             ).fetchone()

#             if not batch:
#                 raise ValueError("Batch not found.")

#             if movement_type in ("PURCHASE", "RETURN_IN"):
#                 change = quantity
#             else:
#                 change = -quantity

#             new_stock = batch["quantity"] + change
#             if new_stock < 0:
#                 raise ValueError("Movement exceeds available stock.")

#             conn.execute(
#                 "UPDATE batches SET quantity = ? WHERE id = ?",
#                 (new_stock, batch_id)
#             )
#             conn.execute("""
#                 INSERT INTO stock_movements (
#                     batch_id, movement_type, quantity_change, note
#                 ) VALUES (?, ?, ?, ?)
#             """, (batch_id, movement_type, change, note))
#             conn.commit()

#         flash("Stock movement recorded.", "success")
#     except ValueError as exc:
#         flash(str(exc), "error")
#     except sqlite3.Error:
#         app.logger.exception("Stock movement failed")
#         flash("Database error while recording stock movement.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # CSV IMPORT / TEMPLATE
# # ============================================================

# CSV_HEADERS = [
#     "product_name", "category", "batch_number", "barcode",
#     "quantity", "purchase_price", "selling_price", "expiry_date"
# ]


# @app.route("/download-template")
# @manager_or_admin_required
# def download_template():
#     output = io.StringIO()
#     writer = csv.writer(output)
#     writer.writerow(CSV_HEADERS)
#     writer.writerow([
#         "Rice", "Food", "RICE-001", "1234567890123",
#         "50", "40.00", "50.00", date.today().isoformat()
#     ])

#     response = make_response("\ufeff" + output.getvalue())
#     response.headers["Content-Type"] = "text/csv; charset=utf-8"
#     response.headers["Content-Disposition"] = (
#         "attachment; filename=expiryguard_inventory_template.csv"
#     )
#     return response


# @app.route("/import-csv", methods=["POST"])
# @manager_or_admin_required
# def import_csv():
#     uploaded = request.files.get("file")

#     if not uploaded or not uploaded.filename:
#         flash("Choose a CSV file to import.", "error")
#         return redirect(url_for("dashboard"))

#     try:
#         content = uploaded.stream.read().decode("utf-8-sig")
#         reader = csv.DictReader(io.StringIO(content))

#         if not reader.fieldnames:
#             raise ValueError("CSV file is empty.")

#         headers = {h.strip().lower() for h in reader.fieldnames if h}
#         required = set(CSV_HEADERS) - {"barcode"}
#         if not required.issubset(headers):
#             raise ValueError(
#                 "CSV headers are missing. Download the template "
#                 "and use its column names."
#             )

#         imported = 0
#         skipped = 0
#         errors = []

#         with closing(get_db()) as conn:
#             for line_no, row in enumerate(reader, start=2):
#                 row = {
#                     (k or "").strip().lower(): (v or "").strip()
#                     for k, v in row.items()
#                 }

#                 try:
#                     name = row.get("product_name", "")
#                     category = row.get("category", "")
#                     batch_no = row.get("batch_number", "")
#                     barcode = row.get("barcode") or None
#                     qty = int(row.get("quantity", ""))
#                     purchase = float(row.get("purchase_price", ""))
#                     selling = float(row.get("selling_price", ""))
#                     expiry = row.get("expiry_date", "")

#                     if not all([name, category, batch_no, expiry]):
#                         raise ValueError("Required field missing.")
#                     date.fromisoformat(expiry)
#                     if expiry < date.today().isoformat():
#                         raise ValueError("Expiry date is in the past.")
#                     if qty <= 0 or purchase < 0 or selling < 0:
#                         raise ValueError("Invalid quantity or price.")
#                     if not math.isfinite(purchase + selling):
#                         raise ValueError("Invalid price.")

#                     duplicate = conn.execute("""
#                         SELECT id FROM batches
#                         WHERE LOWER(TRIM(product_name)) =
#                               LOWER(TRIM(?))
#                           AND LOWER(TRIM(batch_number)) =
#                               LOWER(TRIM(?))
#                     """, (name, batch_no)).fetchone()

#                     if duplicate:
#                         skipped += 1
#                         continue

#                     cursor = conn.execute("""
#                         INSERT INTO batches (
#                             product_name, category, batch_number, barcode,
#                             quantity, purchase_price, selling_price,
#                             stock_entry_date, expiry_date
#                         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                     """, (
#                         name, category, batch_no, barcode, qty,
#                         purchase, selling, date.today().isoformat(), expiry
#                     ))

#                     conn.execute("""
#                         INSERT INTO stock_movements (
#                             batch_id, movement_type, quantity_change, note
#                         ) VALUES (?, 'PURCHASE', ?, ?)
#                     """, (cursor.lastrowid, qty, "CSV import"))
#                     imported += 1

#                 except (ValueError, OverflowError) as exc:
#                     errors.append(f"Row {line_no}: {exc}")

#             conn.commit()

#         flash(
#             f"CSV import complete. Imported: {imported}; "
#             f"duplicates skipped: {skipped}; invalid rows: {len(errors)}.",
#             "success" if not errors else "warning"
#         )

#         for error in errors[:10]:
#             flash(error, "error")

#     except (UnicodeDecodeError, csv.Error, ValueError) as exc:
#         flash(f"CSV import failed: {exc}", "error")
#     except sqlite3.Error:
#         app.logger.exception("CSV import failed")
#         flash("Database error while importing CSV.", "error")

#     return redirect(url_for("dashboard"))


# # ============================================================
# # ADDITIONAL EXPIRYGUARD FEATURES (additive; existing routes retained)
# # ============================================================

# @app.route("/suppliers", methods=["GET", "POST"])
# @manager_or_admin_required
# def suppliers():
#     with closing(get_db()) as conn:
#         if request.method == "POST":
#             name = request.form.get("name", "").strip()
#             if not name:
#                 flash("Supplier name is required.", "error")
#             else:
#                 conn.execute("INSERT INTO suppliers(name, contact_person, phone, email, address, notes) VALUES (?, ?, ?, ?, ?, ?)", (name, request.form.get("contact_person", "").strip(), request.form.get("phone", "").strip(), request.form.get("email", "").strip(), request.form.get("address", "").strip(), request.form.get("notes", "").strip()))
#                 conn.commit()
#                 flash("Supplier saved successfully.", "success")
#                 return redirect(url_for("suppliers"))
#         rows = [dict(r) for r in conn.execute("SELECT * FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()]
#     return render_template("suppliers.html", suppliers=rows)

# @app.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
# @admin_required
# def delete_supplier(supplier_id):
#     with closing(get_db()) as conn:
#         conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
#         conn.commit()
#     flash("Supplier deleted if it existed.", "success")
#     return redirect(url_for("suppliers"))

# @app.route("/export/inventory.csv")
# @manager_or_admin_required
# def export_inventory_csv():
#     with closing(get_db()) as conn:
#         rows = conn.execute("SELECT product_name, category, batch_number, barcode, quantity, purchase_price, selling_price, stock_entry_date, expiry_date FROM batches ORDER BY product_name, expiry_date").fetchall()
#     output = io.StringIO(newline="")
#     writer = csv.writer(output)
#     writer.writerow(["product_name", "category", "batch_number", "barcode", "quantity", "purchase_price", "selling_price", "stock_entry_date", "expiry_date"])
#     writer.writerows([tuple(row) for row in rows])
#     response = make_response(output.getvalue())
#     response.headers["Content-Type"] = "text/csv; charset=utf-8"
#     response.headers["Content-Disposition"] = "attachment; filename=expiryguard_inventory.csv"
#     return response

# @app.route("/export/inventory.xlsx")
# @manager_or_admin_required
# def export_inventory_xlsx():
#     try:
#         from openpyxl import Workbook
#         from openpyxl.utils import get_column_letter
#     except ImportError:
#         flash("Excel export requires openpyxl. Install it with: pip install openpyxl", "error")
#         return redirect(url_for("dashboard"))
#     with closing(get_db()) as conn:
#         rows = conn.execute("SELECT product_name, category, batch_number, barcode, quantity, purchase_price, selling_price, stock_entry_date, expiry_date FROM batches ORDER BY product_name, expiry_date").fetchall()
#     wb = Workbook(); ws = wb.active; ws.title = "Inventory"
#     ws.append(["Product", "Category", "Batch", "Barcode", "Quantity", "Purchase Price", "Selling Price", "Stock Entry Date", "Expiry Date"])
#     for row in rows: ws.append(list(row))
#     for col in ws.columns:
#         ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(max(len(str(c.value or "")) for c in col) + 2, 12), 32)
#     buf = io.BytesIO(); wb.save(buf); buf.seek(0)
#     response = make_response(buf.getvalue()); response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; response.headers["Content-Disposition"] = "attachment; filename=expiryguard_inventory.xlsx"
#     return response

# @app.route("/invoices/create", methods=["GET", "POST"])
# @require_login
# def create_invoice():
#     if request.method == "GET":
#         with closing(get_db()) as conn:
#             batches = [dict(r) for r in conn.execute("SELECT id, product_name, batch_number, quantity, selling_price FROM batches WHERE quantity > 0 ORDER BY product_name").fetchall()]
#         return render_template("invoice_create.html", batches=batches)
#     customer = request.form.get("customer_name", "").strip()
#     contact = request.form.get("customer_contact", "").strip()
#     try:
#         batch_id = int(request.form.get("batch_id", "")); qty = int(request.form.get("quantity", ""))
#         if qty <= 0: raise ValueError
#     except ValueError:
#         flash("Select a valid batch and quantity.", "error"); return redirect(url_for("create_invoice"))
#     with closing(get_db()) as conn:
#         batch = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
#         if not batch or batch["quantity"] < qty:
#             flash("The selected batch does not have enough available stock.", "error"); return redirect(url_for("create_invoice"))
#         total = round(float(batch["selling_price"]) * qty, 2)
#         number = "EG-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
#         cur = conn.execute("INSERT INTO invoices(invoice_number, customer_name, customer_contact, subtotal, total, created_by) VALUES (?, ?, ?, ?, ?, ?)", (number, customer, contact, total, total, g.current_user["id"]))
#         invoice_id = cur.lastrowid
#         conn.execute("INSERT INTO invoice_items(invoice_id, batch_id, product_name, batch_number, quantity, unit_price, line_total) VALUES (?, ?, ?, ?, ?, ?, ?)", (invoice_id, batch_id, batch["product_name"], batch["batch_number"], qty, batch["selling_price"], total))
#         conn.execute("UPDATE batches SET quantity = quantity - ? WHERE id = ?", (qty, batch_id))
#         conn.execute("INSERT INTO sales(batch_id, quantity) VALUES (?, ?)", (batch_id, qty))
#         conn.execute("INSERT INTO stock_movements(batch_id, movement_type, quantity_change, note) VALUES (?, 'SALE', ?, ?)", (batch_id, -qty, "Invoice " + number))
#         conn.commit()
#     return redirect(url_for("view_invoice", invoice_id=invoice_id))

# @app.route("/invoices/<int:invoice_id>")
# @require_login
# def view_invoice(invoice_id):
#     with closing(get_db()) as conn:
#         inv = conn.execute("SELECT i.*, u.username AS created_by_name FROM invoices i LEFT JOIN users u ON u.id=i.created_by WHERE i.id=?", (invoice_id,)).fetchone()
#         if not inv: abort(404)
#         items = [dict(r) for r in conn.execute("SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()]
#     return render_template("invoice_receipt.html", invoice=dict(inv), items=items)

# @app.route("/barcode/<int:batch_id>.svg")
# @require_login
# def barcode_svg(batch_id):
#     # A lightweight SVG label containing the existing barcode/batch identifier.
#     with closing(get_db()) as conn:
#         row = conn.execute("SELECT barcode, batch_number, product_name FROM batches WHERE id=?", (batch_id,)).fetchone()
#     if not row: abort(404)
#     value = row["barcode"] or row["batch_number"]
#     safe = __import__("html").escape(str(value))
#     # Deterministic visual bars for a printable inventory label; scan value is printed below.
#     bits = ''.join(f'{ord(ch):08b}' for ch in str(value))[:240]
#     bars = ''.join(f'<rect x="{i*2}" y="0" width="{1 if bit=="1" else 2}" height="54" fill="#111"/>' for i, bit in enumerate(bits) if bit == '1')
#     svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="90" viewBox="0 0 520 90"><rect width="520" height="90" fill="white"/><g transform="translate(10 5)">{bars}</g><text x="10" y="78" font-family="Arial" font-size="14">{safe}</text></svg>'
#     return app.response_class(svg, mimetype="image/svg+xml")

# @app.route("/qr/<int:batch_id>.png")
# @require_login
# def batch_qr_code(batch_id):
#     try:
#         import qrcode
#     except ImportError:
#         return "QR generation requires qrcode[pil]. Install project requirements and retry.", 501
#     with closing(get_db()) as conn:
#         row = conn.execute("SELECT id, product_name, batch_number, barcode FROM batches WHERE id=?", (batch_id,)).fetchone()
#     if not row:
#         abort(404)
#     payload = row["barcode"] or f"EXPIRYGUARD:BATCH:{row['id']}:{row['batch_number']}"
#     image = qrcode.make(str(payload))
#     output = io.BytesIO(); image.save(output, format="PNG")
#     return app.response_class(output.getvalue(), mimetype="image/png")

# @app.route("/audit/export.csv")
# @manager_or_admin_required
# def export_audit_csv():
#     with closing(get_db()) as conn:
#         rows = conn.execute("SELECT m.id, b.product_name, b.batch_number, m.movement_type, m.quantity_change, m.note, m.created_at FROM stock_movements m JOIN batches b ON b.id=m.batch_id ORDER BY m.created_at DESC").fetchall()
#     output=io.StringIO(newline=""); w=csv.writer(output); w.writerow(["ID","Product","Batch","Movement","Quantity Change","Note","Date"]); w.writerows([tuple(r) for r in rows])
#     response=make_response(output.getvalue()); response.headers["Content-Type"]="text/csv; charset=utf-8"; response.headers["Content-Disposition"]="attachment; filename=expiryguard_stock_audit.csv"; return response


# # ============================================================
# # START APPLICATION
# # ============================================================

# init_db()

# if __name__ == "__main__":
#     app.run(debug=True)








from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, make_response, session, g, abort
)
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import math
import csv
import io
from pathlib import Path
from datetime import date, datetime, timedelta
from contextlib import closing

app = Flask(__name__)
app.secret_key = __import__("os").environ.get("EXPIRYGUARD_SECRET_KEY", "dev-only-change-this-secret-key-before-deployment")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = __import__("os").environ.get("EXPIRYGUARD_HTTPS", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "expiryguard.db"


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(conn, table, column):
    return any(
        row["name"] == column
        for row in conn.execute(f"PRAGMA table_info({table})")
    )


def init_db():
    with closing(get_db()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                batch_number TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0
                    CHECK(quantity >= 0),
                purchase_price REAL NOT NULL DEFAULT 0
                    CHECK(purchase_price >= 0),
                selling_price REAL NOT NULL DEFAULT 0
                    CHECK(selling_price >= 0),
                expiry_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_name, batch_number)
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                sold_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                selling_price_snapshot REAL,
                purchase_price_snapshot REAL,
                FOREIGN KEY(batch_id) REFERENCES batches(id)
            );

            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                movement_type TEXT NOT NULL,
                quantity_change INTEGER NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(batch_id) REFERENCES batches(id)
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Admin', 'Manager', 'Staff')),
                status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add missing columns without deleting existing inventory.
        additions = {
            "barcode": "TEXT",
            "stock_entry_date": "TEXT",
        }

        for column, definition in additions.items():
            if not column_exists(conn, "batches", column):
                conn.execute(
                    f"ALTER TABLE batches ADD COLUMN {column} {definition}"
                )

        # Add transaction price snapshots without deleting or rebuilding existing data.
        if not column_exists(conn, "sales", "selling_price_snapshot"):
            conn.execute("ALTER TABLE sales ADD COLUMN selling_price_snapshot REAL")
        if not column_exists(conn, "sales", "purchase_price_snapshot"):
            conn.execute("ALTER TABLE sales ADD COLUMN purchase_price_snapshot REAL")
        # Legacy transactions did not retain prices; backfill using current batch prices.
        conn.execute("""
            UPDATE sales
            SET selling_price_snapshot = COALESCE(selling_price_snapshot,
                (SELECT selling_price FROM batches WHERE batches.id = sales.batch_id)),
                purchase_price_snapshot = COALESCE(purchase_price_snapshot,
                (SELECT purchase_price FROM batches WHERE batches.id = sales.batch_id))
            WHERE selling_price_snapshot IS NULL OR purchase_price_snapshot IS NULL
        """)

        # Existing records get a reasonable entry date.
        conn.execute("""
            UPDATE batches
            SET stock_entry_date = COALESCE(
                stock_entry_date,
                date(created_at),
                date('now')
            )
            WHERE stock_entry_date IS NULL OR stock_entry_date = ''
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_batches_expiry
            ON batches(expiry_date)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sales_date
            ON sales(sold_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_movements_date
            ON stock_movements(created_at)
        """)

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, contact_person TEXT DEFAULT '',
                phone TEXT DEFAULT '', email TEXT DEFAULT '',
                address TEXT DEFAULT '', notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                customer_name TEXT DEFAULT '', customer_contact TEXT DEFAULT '',
                subtotal REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0,
                created_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL,
                batch_id INTEGER, product_name TEXT NOT NULL, batch_number TEXT DEFAULT '',
                quantity INTEGER NOT NULL, unit_price REAL NOT NULL, line_total REAL NOT NULL,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
                FOREIGN KEY(batch_id) REFERENCES batches(id)
            );
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, identity TEXT NOT NULL,
                attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, succeeded INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);
            CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(created_at);
        """)
        conn.commit()


# ============================================================
# AUTHENTICATION
# ============================================================

@app.before_request
def load_current_user():
    """Load and validate the signed-in user before every protected request."""
    if request.endpoint in {"login", "static"} or request.endpoint is None:
        return None
    if not session.get("user_id"):
        return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
    with closing(get_db()) as conn:
        user = conn.execute(
            "SELECT id, username, email, role, status FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()
    if not user or user["status"] != "Active":
        session.clear()
        return redirect(url_for("login"))
    g.current_user = dict(user)


def require_login(view):
    """Route decorator; global authentication is loaded by load_current_user."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not getattr(g, "current_user", None):
            return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_current_user():
    return {"current_user": getattr(g, "current_user", None)}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not getattr(g, "current_user", None) or g.current_user["role"] != "Admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def manager_or_admin_required(view):
    """Allow operational inventory management to Admins and Managers only."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if not user or user["role"] not in {"Admin", "Manager"}:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def role_view_allowed(role, module_name):
    """Staff can view operational screens and sales, but not reports/recommendations/users."""
    if module_name == "users":
        return role == "Admin"
    if module_name in {"reports", "recommendations"}:
        return role in {"Admin", "Manager"}
    return module_name in {"dashboard", "inventory", "products", "sales", "alerts"}


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        with closing(get_db()) as conn:
            recent_failures = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE identity = ? AND succeeded = 0 AND attempted_at >= datetime('now', '-15 minutes')", (identity,)).fetchone()[0]
            if recent_failures >= 8:
                error = "Too many unsuccessful attempts. Please wait 15 minutes before trying again."
                return render_template("login.html", error=error), 429
            user = conn.execute(
                "SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1",
                (identity, identity)
            ).fetchone()
        if user and user["status"] == "Active" and check_password_hash(user["password_hash"], password):
            with closing(get_db()) as conn:
                conn.execute("INSERT INTO login_attempts(identity, succeeded) VALUES (?, 1)", (identity,))
                conn.commit()
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            destination = request.args.get("next", "")
            if not destination.startswith("/") or destination.startswith("//"):
                destination = url_for("dashboard")
            return redirect(destination)
        with closing(get_db()) as conn:
            conn.execute("INSERT INTO login_attempts(identity, succeeded) VALUES (?, 0)", (identity,))
            conn.commit()
        error = "Invalid username/email or password, or the account is inactive."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "Staff")
    status = request.form.get("status", "Active")
    if (not username or len(username) > 50 or not email or len(email) > 254
            or "@" not in email or any(ch.isspace() for ch in email)
            or len(password) < 8
            or role not in {"Admin", "Manager", "Staff"}
            or status not in {"Active", "Inactive"}):
        flash("Enter valid user details. Password must contain at least 8 characters.", "error")
        return redirect(url_for("dashboard") + "#users")
    try:
        with closing(get_db()) as conn:
            conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
                         (username, email, generate_password_hash(password), role, status))
            conn.commit()
        flash(f"Account created for {username}.", "success")
    except sqlite3.IntegrityError:
        flash("Username or email already exists.", "error")
    return redirect(url_for("dashboard") + "#users")


@app.route("/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def edit_user(user_id):
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "Staff")
    password = request.form.get("password", "")

    if (not username or len(username) > 50 or not email or len(email) > 254
            or "@" not in email or any(ch.isspace() for ch in email)
            or role not in {"Admin", "Manager", "Staff"}
            or (password and len(password) < 8)):
        flash("Enter valid user details. A new password must contain at least 8 characters.", "error")
        return redirect(url_for("dashboard") + "#users")

    # Prevent an administrator from accidentally removing their own admin access.
    if user_id == g.current_user["id"] and role != "Admin":
        flash("You cannot change your own role from Admin.", "error")
        return redirect(url_for("dashboard") + "#users")

    try:
        with closing(get_db()) as conn:
            target = conn.execute(
                "SELECT id, role, status FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not target:
                flash("User not found.", "error")
                return redirect(url_for("dashboard") + "#users")

            if target["role"] == "Admin" and target["status"] == "Active" and role != "Admin":
                active_admins = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'Admin' AND status = 'Active'"
                ).fetchone()[0]
                if active_admins <= 1:
                    flash("The last active Admin cannot be demoted.", "error")
                    return redirect(url_for("dashboard") + "#users")

            if password:
                conn.execute(
                    "UPDATE users SET username = ?, email = ?, role = ?, password_hash = ? WHERE id = ?",
                    (username, email, role, generate_password_hash(password), user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET username = ?, email = ?, role = ? WHERE id = ?",
                    (username, email, role, user_id)
                )
            conn.commit()
        flash("User details updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("That username or email is already in use.", "error")
    return redirect(url_for("dashboard") + "#users")


@app.route("/users/<int:user_id>/status", methods=["POST"])
@admin_required
def update_user_status(user_id):
    status = request.form.get("status")
    if status not in {"Active", "Inactive"}:
        abort(400)
    with closing(get_db()) as conn:
        target = conn.execute(
            "SELECT id, role, status FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not target:
            flash("User not found.", "error")
        elif user_id == g.current_user["id"] and status == "Inactive":
            flash("You cannot deactivate your own account.", "error")
        elif target["role"] == "Admin" and target["status"] == "Active" and status == "Inactive" and conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'Admin' AND status = 'Active'"
        ).fetchone()[0] <= 1:
            flash("The last active Admin cannot be deactivated.", "error")
        else:
            conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            conn.commit()
            flash("User status updated.", "success")
    return redirect(url_for("dashboard") + "#users")


@app.cli.command("create-admin")
def create_admin_command():
    """Create the first Admin account interactively; password is never stored in plain text."""
    import getpass
    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password (minimum 8 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if not username or not email or len(password) < 8 or password != confirm:
        print("Invalid details or passwords do not match.")
        return
    with closing(get_db()) as conn:
        exists = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0]
        if exists:
            print("An Admin account already exists. Use the Users page to create accounts.")
            return
        try:
            conn.execute("INSERT INTO users (username, email, password_hash, role, status) VALUES (?, ?, ?, 'Admin', 'Active')",
                         (username, email, generate_password_hash(password)))
            conn.commit()
            print("Admin account created successfully. You can now log in.")
        except sqlite3.IntegrityError:
            print("That username or email is already in use.")


# ============================================================
# HELPERS
# ============================================================

def get_status(expiry_date):
    days_left = (date.fromisoformat(str(expiry_date)[:10]) -
                 date.today()).days

    if days_left < 0:
        status = "Expired"
    elif days_left == 0:
        status = "Expires Today"
    elif days_left <= 7:
        status = "Urgent"
    elif days_left <= 30:
        status = "Warning"
    else:
        status = "Safe"

    return days_left, status


def enrich_batch(batch):
    item = dict(batch)
    item["days_left"], item["status"] = get_status(item["expiry_date"])
    # Availability is independent of expiry status: zero stock must not
    # overwrite Safe/Warning/Urgent/Expires Today/Expired calculations.
    item["availability"] = (
        "Stock Not Available" if int(item["quantity"] or 0) <= 0
        else "In Stock"
    )
    item["stock_value"] = item["quantity"] * item["purchase_price"]
    return item


def get_product_sales(conn):
    rows = conn.execute("""
        SELECT
            LOWER(TRIM(b.product_name)) AS product_key,
            MIN(b.product_name) AS product_name,
            SUM(b.quantity) AS total_stock,
            COALESCE((
                SELECT SUM(s.quantity)
                FROM sales s
                JOIN batches bx ON bx.id = s.batch_id
                WHERE LOWER(TRIM(bx.product_name)) =
                      LOWER(TRIM(b.product_name))
                  AND date(s.sold_at) >= date('now', '-6 days')
                  AND date(s.sold_at) <= date('now')
            ), 0) AS sold_7_days,
            COALESCE((
                SELECT SUM(s.quantity) FROM sales s
                JOIN batches bx ON bx.id = s.batch_id
                WHERE LOWER(TRIM(bx.product_name)) = LOWER(TRIM(b.product_name))
                  AND date(s.sold_at) >= date('now', '-29 days')
                  AND date(s.sold_at) <= date('now')
            ), 0) AS sold_30_days
        FROM batches b
        GROUP BY LOWER(TRIM(b.product_name))
    """).fetchall()

    return {
        row["product_key"]: {
            "product_name": row["product_name"],
            "total_stock": row["total_stock"] or 0,
            "sold_7_days": row["sold_7_days"] or 0,
            "sold_30_days": row["sold_30_days"] or 0,
        }
        for row in rows
    }


def generate_recommendations(batches, product_sales):
    recommendations = []

    for batch in batches:
        quantity = max(0, int(batch["quantity"]))
        days = batch["days_left"]
        key = batch["product_name"].strip().casefold()
        sales_info = product_sales.get(key, {})
        sold = float(sales_info.get("sold_7_days", 0))
        daily = sold / 7
        value = round(quantity * batch["purchase_price"], 2)

        def recommendation_category(title):
            title_text = str(title).casefold()
            if "loss" in title_text:
                return "Loss"
            if any(word in title_text for word in ("expiry", "expired", "expires")):
                return "Expiry"
            if any(word in title_text for word in ("sales", "demand")):
                return "Sales"
            return "Stock"

        def add(level, title, detail, action, stock_value=value):
            recommendations.append({
                "level": level,
                "title": title,
                "product": batch["product_name"],
                "batch": batch["batch_number"],
                "batch_id": batch["id"],
                "quantity": quantity,
                "days_left": days,
                "category": recommendation_category(title),
                "detail": detail,
                "action": action,
                "stock_value": stock_value,
            })

        if quantity <= 0:
            add(
                "critical", "Stock Not Available",
                "This batch currently has no available stock.",
                "Review recent sales and stock movements before replenishing.",
                0
            )
            continue

        if days < 0:
            add(
                "critical", "Expired Stock",
                f"{quantity} units expired {abs(days)} day(s) ago.",
                "Remove from sale and follow disposal procedures."
            )
            continue

        if days == 0:
            add(
                "critical", "Expires Today",
                f"{quantity} units reach their expiry date today.",
                "Review immediately; do not sell once expired."
            )
        elif days <= 3:
            add(
                "critical", "Critical Expiry Risk",
                f"{quantity} units remain and expire in {days} day(s).",
                "Review immediately and prioritize eligible stock."
            )
        elif days <= 7:
            add(
                "urgent", "Urgent Expiry Risk",
                f"{quantity} units remain and expire in {days} days.",
                "Prioritize this batch using FEFO."
            )
        elif days <= 30:
            add(
                "warning", "Upcoming Expiry",
                f"{quantity} units expire in {days} days.",
                "Monitor sales and replenishment."
            )

        if days > 0 and daily > 0:
            at_risk = max(0, min(quantity, math.ceil(quantity - daily * days)))
            if at_risk:
                add(
                    "warning", "Potential Expiry Loss",
                    f"Recent sales suggest approximately {at_risk} "
                    "unit(s) may remain unsold by expiry.",
                    "Review sales, stock placement and future orders.",
                    round(at_risk * batch["purchase_price"], 2)
                )
        elif days > 0 and sold == 0:
            add(
                "info", "No Recent Sales",
                "No sales were recorded for this product in the last 7 days.",
                "Review demand manually."
            )

    for info in product_sales.values():
        stock = max(0, int(info["total_stock"]))
        recent_daily = float(info["sold_7_days"]) / 7
        monthly_daily = float(info.get("sold_30_days", 0)) / 30
        daily = recent_daily * 0.6 + monthly_daily * 0.4 if monthly_daily else recent_daily

        if daily <= 0:
            continue

        cover = stock / daily

        if stock > 0 and cover <= 7:
            recommendations.append({
                "level": "info",
                "title": "Low Stock — Review Restocking",
                "product": info["product_name"],
                "batch": "All batches",
                "days_left": 0,
                "category": "Stock",
                "quantity": stock,
                "batch_id": None,
                "detail": f"{stock} units remain. Estimated demand is {daily:.2f} units/day; "
                          f"stock may last about {cover:.1f} days.",
                "action": "Plan replenishment before the predicted stock-out date.",
                "stock_value": 0,
            })
        elif cover > 30:
            recommendations.append({
                "level": "warning",
                "title": "Possible Overstock",
                "product": info["product_name"],
                "batch": "All batches",
                "days_left": 0,
                "category": "Stock",
                "quantity": stock,
                "batch_id": None,
                "detail": f"Current stock represents about {cover:.0f} "
                          "days of sales.",
                "action": "Review purchase orders.",
                "stock_value": 0,
            })

    priority = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
    recommendations.sort(key=lambda x: priority.get(x["level"], 4))
    return recommendations


def build_alerts(batches, recommendations):
    """Build the dashboard alert feed from existing expiry statuses and recommendations.

    Expiry dates/statuses are not recalculated here: enrich_batch/get_status remains
    the single source of truth for Safe, Warning, Urgent, Expires Today and Expired.
    """
    alerts = []

    for batch in batches:
        quantity = max(0, int(batch.get("quantity", 0) or 0))
        if quantity <= 0 or batch["days_left"] > 30:
            continue

        status = batch["status"]
        if status == "Expired":
            title, severity = "Expired stock", "critical"
            detail = f"{quantity} units are past their expiry date."
        elif status == "Expires Today":
            title, severity = "Expires today", "critical"
            detail = f"{quantity} units reach their expiry date today."
        elif status == "Urgent":
            title, severity = "Expiring within 7 days", "urgent"
            detail = f"{quantity} units expire in {batch['days_left']} day(s)."
        elif status == "Warning":
            title, severity = "Expiring within 30 days", "warning"
            detail = f"{quantity} units expire in {batch['days_left']} days."
        else:
            continue

        alerts.append({
            "title": title, "severity": severity,
            "product": batch["product_name"], "batch": batch["batch_number"],
            "detail": detail, "target": "inventory",
        })

    # Reuse existing recommendation output for stock and demand signals.
    # Do not introduce new thresholds or a second stock/expiry calculation.
    for item in recommendations:
        title = item["title"]
        if title in {"Low Stock — Review Restocking", "Possible Overstock"}:
            alerts.append({
                "title": title, "severity": item["level"],
                "product": item["product"], "batch": item["batch"],
                "detail": item["detail"], "target": "recommendations",
            })
        elif title == "No Recent Sales":
            alerts.append({
                "title": "Slow-moving signal — no recent sales",
                "severity": "info", "product": item["product"],
                "batch": item["batch"], "detail": item["detail"],
                "target": "recommendations",
            })
        elif title == "Potential Expiry Loss":
            alerts.append({
                "title": title, "severity": item["level"],
                "product": item["product"], "batch": item["batch"],
                "detail": item["detail"], "target": "recommendations",
            })

    severity_order = {"critical": 0, "urgent": 1, "warning": 2, "info": 3}
    alerts.sort(key=lambda item: severity_order.get(item["severity"], 4))
    return alerts


def build_sales_forecast(conn):
    rows = conn.execute("""
        SELECT LOWER(TRIM(b.product_name)) AS product_key, MIN(b.product_name) AS product_name,
               COALESCE(SUM(CASE WHEN date(s.sold_at) >= date('now','-6 days') THEN s.quantity ELSE 0 END),0) AS sold_7,
               COALESCE(SUM(CASE WHEN date(s.sold_at) >= date('now','-29 days') THEN s.quantity ELSE 0 END),0) AS sold_30,
               COALESCE((SELECT SUM(bx.quantity) FROM batches bx
                         WHERE LOWER(TRIM(bx.product_name)) = LOWER(TRIM(b.product_name))),0) AS stock
        FROM batches b LEFT JOIN sales s ON s.batch_id=b.id
        GROUP BY LOWER(TRIM(b.product_name)) ORDER BY product_name
    """).fetchall()
    result=[]
    for row in rows:
        recent=float(row["sold_7"] or 0)/7
        monthly=float(row["sold_30"] or 0)/30
        daily=round(recent*0.6+monthly*0.4,2) if monthly else round(recent,2)
        stock=int(row["stock"] or 0)
        result.append({"product_name":row["product_name"],"stock":stock,"sold_7":int(row["sold_7"] or 0),
                       "sold_30":int(row["sold_30"] or 0),"daily_demand":daily,"forecast_30":round(daily*30,1),
                       "days_cover":round(stock/daily,1) if daily>0 else None,"stockout_risk":bool(daily>0 and stock/daily<=7)})
    return result


def build_profit_analytics(conn):
    row=conn.execute("""SELECT COALESCE(SUM(quantity*COALESCE(selling_price_snapshot,0)),0) revenue,
                       COALESCE(SUM(quantity*COALESCE(purchase_price_snapshot,0)),0) cost,
                       COUNT(*) transactions, COALESCE(SUM(quantity),0) units_sold FROM sales""").fetchone()
    expired=conn.execute("SELECT COALESCE(SUM(quantity*purchase_price),0) FROM batches WHERE expiry_date < ? AND quantity>0",
                         (date.today().isoformat(),)).fetchone()[0]
    revenue=float(row["revenue"] or 0); cost=float(row["cost"] or 0); expired=float(expired or 0)
    return {"revenue":round(revenue,2),"cost_of_goods":round(cost,2),"gross_profit":round(revenue-cost,2),
            "expired_stock_cost":round(expired,2),"estimated_net_after_expiry":round(revenue-cost-expired,2),
            "transactions":int(row["transactions"] or 0),"units_sold":int(row["units_sold"] or 0)}


def dashboard_data():
    with closing(get_db()) as conn:
        raw_batches = conn.execute("""
            SELECT * FROM batches
            ORDER BY expiry_date ASC, product_name ASC
        """).fetchall()

        product_sales = get_product_sales(conn)

        categories = [
            row["category"]
            for row in conn.execute("""
                SELECT DISTINCT category FROM batches
                ORDER BY category
            """).fetchall()
        ]

        product_names = [
            row["product_name"]
            for row in conn.execute("""
                SELECT MIN(product_name) AS product_name
                FROM batches
                GROUP BY LOWER(TRIM(product_name))
                ORDER BY product_name
            """).fetchall()
        ]

        sales_forecast = build_sales_forecast(conn)
        profit_analytics = build_profit_analytics(conn)

        movements = conn.execute("""
            SELECT sm.*, b.product_name, b.batch_number
            FROM stock_movements sm
            JOIN batches b ON b.id = sm.batch_id
            ORDER BY sm.id DESC
            LIMIT 50
        """).fetchall()

    batches = [enrich_batch(row) for row in raw_batches]
    product_stock = {}
    for item in batches:
        key = item["product_name"].strip().casefold()
        product_stock[key] = product_stock.get(key, 0) + int(item["quantity"] or 0)
    for item in batches:
        item["fefo_available"] = sum(int(b["quantity"] or 0) for b in batches
                                      if b["product_name"].strip().casefold() == item["product_name"].strip().casefold()
                                      and b["days_left"] > 0)
    recommendations = generate_recommendations(batches, product_sales)
    alerts = build_alerts(batches, recommendations)

    summary = {
        "total_batches": len(batches),
        "total_units": sum(b["quantity"] for b in batches),
        "safe": sum(b["status"] == "Safe" for b in batches),
        "warning": sum(b["status"] == "Warning" for b in batches),
        "urgent": sum(
            b["status"] in ("Urgent", "Expires Today") for b in batches
        ),
        "expired": sum(b["status"] == "Expired" for b in batches),
        "potential_loss": round(sum(
            b["stock_value"] for b in batches
            if b["status"] in ("Urgent", "Expires Today", "Expired")
        ), 2),
        "average_daily_sales": round(
            sum(x["sold_7_days"] for x in product_sales.values()) / 7, 2
        ),
    }

    return {
        "batches": batches,
        "summary": summary,
        "recommendations": recommendations,
        "recommendation_categories": sorted({
            item.get("category", "Stock") for item in recommendations
        }, key=lambda value: ["Stock", "Expiry", "Risk", "Loss", "Sales"].index(value)
        if value in ["Stock", "Expiry", "Risk", "Loss", "Sales"] else value),
        "alerts": alerts,
        "alert_count": len(alerts),
        "categories": categories,
        "product_names": product_names,
        "movements": [dict(m) for m in movements],
        "today": date.today().isoformat(),
        "sales_forecast": sales_forecast,
        "profit_analytics": profit_analytics,
    }


# ============================================================
# DASHBOARD AND MODULE ROUTES
# ============================================================

@app.route("/")
def dashboard():
    data = dashboard_data()
    if g.current_user["role"] == "Admin":
        with closing(get_db()) as conn:
            data["users"] = [dict(row) for row in conn.execute(
                "SELECT id, username, email, role, status, created_at FROM users ORDER BY id"
            ).fetchall()]
    else:
        data["users"] = []
    if g.current_user["role"] == "Staff":
        data["recommendations"] = []
        # Preserve existing Staff restrictions: recommendation-derived alerts
        # are visible only to Admin and Manager roles.
        data["alerts"] = [item for item in data["alerts"]
                          if item["target"] != "recommendations"]
        data["alert_count"] = len(data["alerts"])
    return render_template("dashboard.html", **data)


@app.route("/module/<module_name>")
def module_view(module_name):
    allowed = {
        "dashboard", "inventory", "sales", "recommendations",
        "alerts", "reports", "products", "users"
    }
    if module_name not in allowed or not role_view_allowed(g.current_user["role"], module_name):
        abort(403)
    return redirect(url_for("dashboard") + "#" + module_name)


# ============================================================
# ADD BATCH
# ============================================================

@app.route("/add", methods=["POST"])
@manager_or_admin_required
def add_batch():
    product_name = request.form.get("product_name", "").strip()
    category = request.form.get("category", "").strip()
    batch_number = request.form.get("batch_number", "").strip()
    barcode = request.form.get("barcode", "").strip() or None
    expiry = request.form.get("expiry_date", "").strip()

    try:
        quantity = int(request.form.get("quantity", ""))
        purchase = float(request.form.get("purchase_price", ""))
        selling = float(request.form.get("selling_price", ""))

        if not all((product_name, category, batch_number, expiry)):
            raise ValueError("Fill in all required fields.")

        date.fromisoformat(expiry)

        if expiry < date.today().isoformat():
            raise ValueError("Expiry date cannot be in the past.")
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if not all(map(math.isfinite, [purchase, selling])):
            raise ValueError("Enter valid prices.")
        if purchase < 0 or selling < 0:
            raise ValueError("Prices cannot be negative.")

    except (ValueError, OverflowError):
        flash("Enter valid batch details, quantity, dates and prices.", "error")
        return redirect(url_for("dashboard"))

    try:
        with closing(get_db()) as conn:
            existing_product = conn.execute("""
                SELECT * FROM batches
                WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
                ORDER BY id LIMIT 1
            """, (product_name,)).fetchone()

            if existing_product:
                product_name = existing_product["product_name"]
                stock = conn.execute("""
                    SELECT COALESCE(SUM(quantity), 0) AS total
                    FROM batches WHERE LOWER(TRIM(product_name)) =
                    LOWER(TRIM(?))
                """, (product_name,)).fetchone()["total"]

                sales = conn.execute("""
                    SELECT COALESCE(SUM(s.quantity), 0) AS sold,
                           COUNT(s.id) AS records
                    FROM sales s JOIN batches b ON b.id = s.batch_id
                    WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
                    AND date(s.sold_at) >= date('now', '-6 days')
                    AND date(s.sold_at) <= date('now')
                """, (product_name,)).fetchone()

                if sales["records"] > 0:
                    required = sales["sold"]
                    if stock >= required:
                        flash(
                            f"Enough stock available for {product_name}. "
                            f"Current stock: {stock}; seven-day sales: "
                            f"{required}. Addition blocked by the "
                            "seven-day stock rule.",
                            "warning"
                        )
                        return redirect(url_for("dashboard"))
                    flash(
                        f"Low stock alert for {product_name}. "
                        f"Current stock: {stock}; seven-day sales: "
                        f"{required}.",
                        "warning"
                    )
                else:
                    flash(
                        "No sales recorded in the last seven days; "
                        "demand cannot be estimated reliably.",
                        "warning"
                    )

            existing_batch = conn.execute("""
                SELECT * FROM batches
                WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
                AND LOWER(TRIM(batch_number)) = LOWER(TRIM(?))
                LIMIT 1
            """, (product_name, batch_number)).fetchone()

            if existing_batch:
                if existing_batch["expiry_date"] != expiry:
                    flash(
                        "This batch number already exists with a "
                        "different expiry date.",
                        "error"
                    )
                    return redirect(url_for("dashboard"))

                conn.execute("""
                    UPDATE batches SET quantity = quantity + ?
                    WHERE id = ?
                """, (quantity, existing_batch["id"]))
                batch_id = existing_batch["id"]
                movement_type = "PURCHASE"
            else:
                cursor = conn.execute("""
                    INSERT INTO batches (
                        product_name, category, batch_number, barcode,
                        quantity, purchase_price, selling_price,
                        stock_entry_date, expiry_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_name, category, batch_number, barcode,
                    quantity, purchase, selling,
                    date.today().isoformat(), expiry
                ))
                batch_id = cursor.lastrowid
                movement_type = "PURCHASE"

            conn.execute("""
                INSERT INTO stock_movements (
                    batch_id, movement_type, quantity_change, note
                ) VALUES (?, ?, ?, ?)
            """, (batch_id, movement_type, quantity, "Stock added"))
            conn.commit()

        flash(f"Stock saved for {product_name}, batch {batch_number}.",
              "success")

    except sqlite3.IntegrityError:
        flash(
            "Could not save the batch. Check duplicate batch numbers "
            "and barcode values.",
            "error"
        )
    except sqlite3.Error:
        app.logger.exception("Could not add batch")
        flash("Database error while adding stock.", "error")

    return redirect(url_for("dashboard"))


# ============================================================
# PRODUCT INSIGHTS AND BARCODE LOOKUP
# ============================================================

@app.route("/product-insight")
def product_insight():
    name = request.args.get("name", "").strip()
    barcode = request.args.get("barcode", "").strip()

    if not name and not barcode:
        return jsonify({"found": False, "message": "Enter a product name or barcode."})

    with closing(get_db()) as conn:
        if barcode:
            rows = conn.execute("""
                SELECT * FROM batches WHERE barcode = ?
                ORDER BY expiry_date, id
            """, (barcode,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM batches
                WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
                ORDER BY expiry_date, id
            """, (name,)).fetchall()

        if not rows:
            return jsonify({"found": False})

        product_name = rows[0]["product_name"]
        sold = conn.execute("""
            SELECT COALESCE(SUM(s.quantity), 0) AS sold
            FROM sales s JOIN batches b ON b.id = s.batch_id
            WHERE LOWER(TRIM(b.product_name)) = LOWER(TRIM(?))
            AND date(s.sold_at) >= date('now', '-6 days')
            AND date(s.sold_at) <= date('now')
        """, (product_name,)).fetchone()["sold"] or 0

    total_stock = sum(r["quantity"] for r in rows)
    average = sold / 7
    cover = round(total_stock / average, 1) if average else None

    if total_stock == 0:
        advice = "No stock remains. Review demand before replenishing."
    elif average == 0:
        advice = "No recent sales recorded. Review demand and expiry dates."
    elif cover <= 3:
        advice = "Low stock cover. Review whether replenishment is needed."
    elif cover > 30:
        advice = "Stock may cover over 30 days of sales. Review expiry dates."
    else:
        advice = "Stock appears sufficient at the recent sales rate."

    return jsonify({
        "found": True,
        "product_name": product_name,
        "category": rows[0]["category"],
        "barcode": rows[0]["barcode"],
        "purchase_price": rows[0]["purchase_price"],
        "selling_price": rows[0]["selling_price"],
        "total_stock": total_stock,
        "availability": "Stock Not Available" if total_stock <= 0 else "In Stock",
        "total_sold": sold,
        "total_sold_7_days": sold,
        "average_daily_sales": round(average, 2) if sold else None,
        "stock_cover_days": cover,
        "batches": [{
            "batch_number": r["batch_number"],
            "quantity": r["quantity"],
            "expiry_date": r["expiry_date"],
            "status": get_status(r["expiry_date"])[1],
            "availability": "Stock Not Available" if r["quantity"] <= 0 else "In Stock"
        } for r in rows],
        "advice": advice
    })


@app.route("/barcode-lookup")
def barcode_lookup():
    code = request.args.get("code", "").strip()
    if not code:
        flash("Enter or scan a barcode.", "error")
        return redirect(url_for("dashboard"))

    with closing(get_db()) as conn:
        matches = conn.execute("""
            SELECT id FROM batches WHERE barcode = ? ORDER BY expiry_date
        """, (code,)).fetchall()

    if not matches:
        flash("No batch found for that barcode.", "error")
        return redirect(url_for("dashboard"))

    return redirect(url_for("batch_sales", batch_id=matches[0]["id"]))


# Keep a route name compatible with templates that use barcode_lookup.
# ============================================================
# UPDATE STOCK / RECORD SALES
# ============================================================

@app.route("/stock/<int:batch_id>", methods=["POST"])
@manager_or_admin_required
def update_stock(batch_id):
    try:
        quantity = int(request.form.get("quantity", ""))
        if quantity < 0:
            raise ValueError

        note = request.form.get("note", "").strip()

        with closing(get_db()) as conn:
            batch = conn.execute(
                "SELECT quantity FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if not batch:
                flash("Batch not found.", "error")
                return redirect(url_for("dashboard"))

            change = quantity - batch["quantity"]
            conn.execute(
                "UPDATE batches SET quantity = ? WHERE id = ?",
                (quantity, batch_id)
            )
            conn.execute("""
                INSERT INTO stock_movements (
                    batch_id, movement_type, quantity_change, note
                ) VALUES (?, 'ADJUSTMENT', ?, ?)
            """, (batch_id, change, note))
            conn.commit()

        flash("Stock quantity updated.", "success")
    except ValueError:
        flash("Enter a valid non-negative quantity.", "error")
    except sqlite3.Error:
        app.logger.exception("Stock update failed")
        flash("Database error while updating stock.", "error")

    return redirect(url_for("dashboard"))


@app.route("/sell/<int:batch_id>", methods=["POST"])
def record_sale(batch_id):
    """Allocate product sales to eligible batches using FEFO order."""
    try:
        quantity = int(request.form.get("quantity_sold", ""))
        if quantity <= 0:
            raise ValueError("Sale quantity must be greater than zero.")
        with closing(get_db()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            selected = conn.execute("SELECT id, product_name FROM batches WHERE id = ?", (batch_id,)).fetchone()
            if selected is None:
                raise ValueError("Batch not found.")
            eligible = conn.execute("""
                SELECT * FROM batches
                WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(?))
                  AND quantity > 0 AND expiry_date > ?
                ORDER BY expiry_date ASC, stock_entry_date ASC, id ASC
            """, (selected["product_name"], date.today().isoformat())).fetchall()
            available = sum(int(row["quantity"]) for row in eligible)
            if quantity > available:
                raise ValueError(f"Insufficient eligible stock. Available quantity: {available}.")
            remaining, allocations = quantity, []
            for batch in eligible:
                if remaining <= 0:
                    break
                allocated = min(remaining, int(batch["quantity"]))
                if not allocated:
                    continue
                conn.execute("UPDATE batches SET quantity = quantity - ? WHERE id = ?", (allocated, batch["id"]))
                conn.execute("""INSERT INTO sales(batch_id, quantity, selling_price_snapshot, purchase_price_snapshot)
                               VALUES (?, ?, ?, ?)""", (batch["id"], allocated, batch["selling_price"], batch["purchase_price"]))
                conn.execute("""INSERT INTO stock_movements(batch_id, movement_type, quantity_change, note)
                               VALUES (?, 'SALE', ?, ?)""", (batch["id"], -allocated, "FEFO sale allocation"))
                allocations.append(f"{batch['batch_number']}: {allocated}")
                remaining -= allocated
            conn.commit()
        flash("Sale recorded using FEFO: " + ", ".join(allocations), "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except sqlite3.Error:
        app.logger.exception("FEFO sale recording failed")
        flash("Database error while recording the sale.", "error")
    return redirect(url_for("dashboard"))


@app.route("/sales/batch/<int:batch_id>")
def batch_sales(batch_id):
    with closing(get_db()) as conn:
        batch = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            flash("Batch not found.", "error")
            return redirect(url_for("dashboard"))

        sales = conn.execute("""
            SELECT * FROM sales WHERE batch_id = ?
            ORDER BY sold_at DESC
        """, (batch_id,)).fetchall()

    html = """
    <!doctype html><html lang="en"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>Batch Sales History | ExpiryGuard</title>
    <style>
    body{font-family:Arial;background:#f3f7f3;color:#20352a;margin:0;padding:24px}
    main{max-width:900px;margin:auto;background:white;padding:24px;border-radius:12px}
    a,button{background:#176b45;color:white;padding:10px 14px;border-radius:7px;text-decoration:none}
    table{width:100%;border-collapse:collapse;margin-top:20px}
    td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}
    </style></head><body><main>
    <h1>🌿 ExpiryGuard</h1><h2>Sales History</h2>
    <p>Product: {{ batch['product_name'] }} · Batch: {{ batch['batch_number'] }}</p>
    <p>Remaining stock: {{ batch['quantity'] }}</p>
    <a href="{{ url_for('dashboard') }}">Back to Dashboard</a>
    <table><thead><tr><th>Sale ID</th><th>Quantity</th><th>Sold at</th></tr></thead>
    <tbody>{% for s in sales %}
    <tr><td>{{ s['id'] }}</td><td>{{ s['quantity'] }}</td><td>{{ s['sold_at'] }}</td></tr>
    {% else %}<tr><td colspan="3">No sales recorded for this batch.</td></tr>
    {% endfor %}</tbody></table></main></body></html>
    """
    return render_template_string_compat(html, batch=batch, sales=sales)


def render_template_string_compat(template, **context):
    from flask import render_template_string
    return render_template_string(template, **context)


# ============================================================
# STOCK MOVEMENTS
# ============================================================

@app.route("/stock-movement/<int:batch_id>", methods=["POST"])
@manager_or_admin_required
def add_stock_movement(batch_id):
    movement_type = request.form.get("movement_type", "").strip().upper()
    note = request.form.get("note", "").strip()
    allowed = {
        "PURCHASE", "RETURN_IN", "DAMAGE",
        "EXPIRED", "RETURN_OUT", "OTHER"
    }

    try:
        quantity = int(request.form.get("quantity", ""))
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if movement_type not in allowed:
            raise ValueError("Invalid stock movement type.")

        with closing(get_db()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            batch = conn.execute(
                "SELECT * FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()

            if not batch:
                raise ValueError("Batch not found.")

            if movement_type in ("PURCHASE", "RETURN_IN"):
                change = quantity
            else:
                change = -quantity

            new_stock = batch["quantity"] + change
            if new_stock < 0:
                raise ValueError("Movement exceeds available stock.")

            conn.execute(
                "UPDATE batches SET quantity = ? WHERE id = ?",
                (new_stock, batch_id)
            )
            conn.execute("""
                INSERT INTO stock_movements (
                    batch_id, movement_type, quantity_change, note
                ) VALUES (?, ?, ?, ?)
            """, (batch_id, movement_type, change, note))
            conn.commit()

        flash("Stock movement recorded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except sqlite3.Error:
        app.logger.exception("Stock movement failed")
        flash("Database error while recording stock movement.", "error")

    return redirect(url_for("dashboard"))


# ============================================================
# CSV IMPORT / TEMPLATE
# ============================================================

CSV_HEADERS = [
    "product_name", "category", "batch_number", "barcode",
    "quantity", "purchase_price", "selling_price", "expiry_date"
]


@app.route("/download-template")
@manager_or_admin_required
def download_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)
    writer.writerow([
        "Rice", "Food", "RICE-001", "1234567890123",
        "50", "40.00", "50.00", date.today().isoformat()
    ])

    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        "attachment; filename=expiryguard_inventory_template.csv"
    )
    return response


@app.route("/import-csv", methods=["POST"])
@manager_or_admin_required
def import_csv():
    uploaded = request.files.get("file")

    if not uploaded or not uploaded.filename:
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("dashboard"))

    try:
        content = uploaded.stream.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))

        if not reader.fieldnames:
            raise ValueError("CSV file is empty.")

        headers = {h.strip().lower() for h in reader.fieldnames if h}
        required = set(CSV_HEADERS) - {"barcode"}
        if not required.issubset(headers):
            raise ValueError(
                "CSV headers are missing. Download the template "
                "and use its column names."
            )

        imported = 0
        skipped = 0
        errors = []

        with closing(get_db()) as conn:
            for line_no, row in enumerate(reader, start=2):
                row = {
                    (k or "").strip().lower(): (v or "").strip()
                    for k, v in row.items()
                }

                try:
                    name = row.get("product_name", "")
                    category = row.get("category", "")
                    batch_no = row.get("batch_number", "")
                    barcode = row.get("barcode") or None
                    qty = int(row.get("quantity", ""))
                    purchase = float(row.get("purchase_price", ""))
                    selling = float(row.get("selling_price", ""))
                    expiry = row.get("expiry_date", "")

                    if not all([name, category, batch_no, expiry]):
                        raise ValueError("Required field missing.")
                    date.fromisoformat(expiry)
                    if expiry < date.today().isoformat():
                        raise ValueError("Expiry date is in the past.")
                    if qty <= 0 or purchase < 0 or selling < 0:
                        raise ValueError("Invalid quantity or price.")
                    if not math.isfinite(purchase + selling):
                        raise ValueError("Invalid price.")

                    duplicate = conn.execute("""
                        SELECT id FROM batches
                        WHERE LOWER(TRIM(product_name)) =
                              LOWER(TRIM(?))
                          AND LOWER(TRIM(batch_number)) =
                              LOWER(TRIM(?))
                    """, (name, batch_no)).fetchone()

                    if duplicate:
                        skipped += 1
                        continue

                    cursor = conn.execute("""
                        INSERT INTO batches (
                            product_name, category, batch_number, barcode,
                            quantity, purchase_price, selling_price,
                            stock_entry_date, expiry_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        name, category, batch_no, barcode, qty,
                        purchase, selling, date.today().isoformat(), expiry
                    ))

                    conn.execute("""
                        INSERT INTO stock_movements (
                            batch_id, movement_type, quantity_change, note
                        ) VALUES (?, 'PURCHASE', ?, ?)
                    """, (cursor.lastrowid, qty, "CSV import"))
                    imported += 1

                except (ValueError, OverflowError) as exc:
                    errors.append(f"Row {line_no}: {exc}")

            conn.commit()

        flash(
            f"CSV import complete. Imported: {imported}; "
            f"duplicates skipped: {skipped}; invalid rows: {len(errors)}.",
            "success" if not errors else "warning"
        )

        for error in errors[:10]:
            flash(error, "error")

    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        flash(f"CSV import failed: {exc}", "error")
    except sqlite3.Error:
        app.logger.exception("CSV import failed")
        flash("Database error while importing CSV.", "error")

    return redirect(url_for("dashboard"))


# ============================================================
# ADDITIONAL EXPIRYGUARD FEATURES (additive; existing routes retained)
# ============================================================

@app.route("/suppliers", methods=["GET", "POST"])
@manager_or_admin_required
def suppliers():
    with closing(get_db()) as conn:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Supplier name is required.", "error")
            else:
                conn.execute("INSERT INTO suppliers(name, contact_person, phone, email, address, notes) VALUES (?, ?, ?, ?, ?, ?)", (name, request.form.get("contact_person", "").strip(), request.form.get("phone", "").strip(), request.form.get("email", "").strip(), request.form.get("address", "").strip(), request.form.get("notes", "").strip()))
                conn.commit()
                flash("Supplier saved successfully.", "success")
                return redirect(url_for("suppliers"))
        rows = [dict(r) for r in conn.execute("SELECT * FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()]
    return render_template("suppliers.html", suppliers=rows)

@app.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@admin_required
def delete_supplier(supplier_id):
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        conn.commit()
    flash("Supplier deleted if it existed.", "success")
    return redirect(url_for("suppliers"))

@app.route("/export/inventory.csv")
@manager_or_admin_required
def export_inventory_csv():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT product_name, category, batch_number, barcode, quantity, purchase_price, selling_price, stock_entry_date, expiry_date FROM batches ORDER BY product_name, expiry_date").fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["product_name", "category", "batch_number", "barcode", "quantity", "purchase_price", "selling_price", "stock_entry_date", "expiry_date"])
    writer.writerows([tuple(row) for row in rows])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=expiryguard_inventory.csv"
    return response

@app.route("/export/inventory.xlsx")
@manager_or_admin_required
def export_inventory_xlsx():
    try:
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter
    except ImportError:
        flash("Excel export requires openpyxl. Install it with: pip install openpyxl", "error")
        return redirect(url_for("dashboard"))
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT product_name, category, batch_number, barcode, quantity, purchase_price, selling_price, stock_entry_date, expiry_date FROM batches ORDER BY product_name, expiry_date").fetchall()
    wb = Workbook(); ws = wb.active; ws.title = "Inventory"
    ws.append(["Product", "Category", "Batch", "Barcode", "Quantity", "Purchase Price", "Selling Price", "Stock Entry Date", "Expiry Date"])
    for row in rows: ws.append(list(row))
    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(max(len(str(c.value or "")) for c in col) + 2, 12), 32)
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    response = make_response(buf.getvalue()); response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; response.headers["Content-Disposition"] = "attachment; filename=expiryguard_inventory.xlsx"
    return response

@app.route("/invoices/create", methods=["GET", "POST"])
@require_login
def create_invoice():
    if request.method == "GET":
        with closing(get_db()) as conn:
            batches = [dict(r) for r in conn.execute("""
                SELECT id, product_name, batch_number, quantity, selling_price, expiry_date
                FROM batches WHERE quantity > 0 AND expiry_date > ?
                ORDER BY product_name, expiry_date, id
            """, (date.today().isoformat(),)).fetchall()]
        return render_template("invoice_create.html", batches=batches)
    customer = request.form.get("customer_name", "").strip()
    contact = request.form.get("customer_contact", "").strip()
    try:
        batch_id = int(request.form.get("batch_id", "")); qty = int(request.form.get("quantity", ""))
        if qty <= 0: raise ValueError
    except ValueError:
        flash("Select a valid batch and quantity.", "error"); return redirect(url_for("create_invoice"))
    with closing(get_db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        selected = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not selected:
            flash("The selected batch was not found.", "error"); return redirect(url_for("create_invoice"))
        eligible = conn.execute("""SELECT * FROM batches WHERE LOWER(TRIM(product_name))=LOWER(TRIM(?))
            AND quantity>0 AND expiry_date>? ORDER BY expiry_date ASC, stock_entry_date ASC, id ASC""",
            (selected["product_name"], date.today().isoformat())).fetchall()
        available = sum(int(row["quantity"]) for row in eligible)
        if qty > available:
            flash(f"Insufficient eligible stock. Available quantity: {available}.", "error")
            return redirect(url_for("create_invoice"))
        allocations=[]; remaining=qty; total=0.0
        for batch in eligible:
            if remaining<=0: break
            allocated=min(remaining,int(batch["quantity"]))
            if not allocated: continue
            line_total=round(float(batch["selling_price"])*allocated,2); total+=line_total
            allocations.append((batch,allocated,line_total))
            remaining-=allocated
        number = "EG-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        cur=conn.execute("INSERT INTO invoices(invoice_number,customer_name,customer_contact,subtotal,total,created_by) VALUES (?,?,?,?,?,?)",
                         (number,customer,contact,total,total,g.current_user["id"]))
        invoice_id=cur.lastrowid
        for batch,allocated,line_total in allocations:
            conn.execute("INSERT INTO invoice_items(invoice_id,batch_id,product_name,batch_number,quantity,unit_price,line_total) VALUES (?,?,?,?,?,?,?)",
                         (invoice_id,batch["id"],batch["product_name"],batch["batch_number"],allocated,batch["selling_price"],line_total))
            conn.execute("UPDATE batches SET quantity=quantity-? WHERE id=?",(allocated,batch["id"]))
            conn.execute("INSERT INTO sales(batch_id,quantity,selling_price_snapshot,purchase_price_snapshot) VALUES (?,?,?,?)",
                         (batch["id"],allocated,batch["selling_price"],batch["purchase_price"]))
            conn.execute("INSERT INTO stock_movements(batch_id,movement_type,quantity_change,note) VALUES (?,'SALE',?,?)",
                         (batch["id"],-allocated,"FEFO invoice " + number))
        conn.commit()
    return redirect(url_for("view_invoice", invoice_id=invoice_id))


@app.route("/invoices/<int:invoice_id>")
@require_login
def view_invoice(invoice_id):
    with closing(get_db()) as conn:
        inv = conn.execute("SELECT i.*, u.username AS created_by_name FROM invoices i LEFT JOIN users u ON u.id=i.created_by WHERE i.id=?", (invoice_id,)).fetchone()
        if not inv: abort(404)
        items = [dict(r) for r in conn.execute("SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()]
    return render_template("invoice_receipt.html", invoice=dict(inv), items=items)

@app.route("/barcode/<int:batch_id>.svg")
@require_login
def barcode_svg(batch_id):
    # A lightweight SVG label containing the existing barcode/batch identifier.
    with closing(get_db()) as conn:
        row = conn.execute("SELECT barcode, batch_number, product_name FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not row: abort(404)
    value = row["barcode"] or row["batch_number"]
    safe = __import__("html").escape(str(value))
    # Deterministic visual bars for a printable inventory label; scan value is printed below.
    bits = ''.join(f'{ord(ch):08b}' for ch in str(value))[:240]
    bars = ''.join(f'<rect x="{i*2}" y="0" width="{1 if bit=="1" else 2}" height="54" fill="#111"/>' for i, bit in enumerate(bits) if bit == '1')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="90" viewBox="0 0 520 90"><rect width="520" height="90" fill="white"/><g transform="translate(10 5)">{bars}</g><text x="10" y="78" font-family="Arial" font-size="14">{safe}</text></svg>'
    return app.response_class(svg, mimetype="image/svg+xml")

@app.route("/audit/export.csv")
@manager_or_admin_required
def export_audit_csv():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT m.id, b.product_name, b.batch_number, m.movement_type, m.quantity_change, m.note, m.created_at FROM stock_movements m JOIN batches b ON b.id=m.batch_id ORDER BY m.created_at DESC").fetchall()
    output=io.StringIO(newline=""); w=csv.writer(output); w.writerow(["ID","Product","Batch","Movement","Quantity Change","Note","Date"]); w.writerows([tuple(r) for r in rows])
    response=make_response(output.getvalue()); response.headers["Content-Type"]="text/csv; charset=utf-8"; response.headers["Content-Disposition"]="attachment; filename=expiryguard_stock_audit.csv"; return response


# ============================================================
# START APPLICATION
# ============================================================

init_db()

if __name__ == "__main__":
    app.run(debug=True)

