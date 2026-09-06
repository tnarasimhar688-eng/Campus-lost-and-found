from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "campus-lost-found-2026"

DATABASE = "campus_lost_found.db"


# ================= DATABASE =================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            student_id TEXT UNIQUE NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            location TEXT NOT NULL,
            item_date TEXT NOT NULL,
            item_type TEXT NOT NULL,
            status TEXT DEFAULT 'Available',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            claimant_id INTEGER NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(item_id) REFERENCES items(id),
            FOREIGN KEY(claimant_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# ================= LOGIN REQUIRED =================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


# ================= HOME =================

@app.route("/")
def home():

    conn = get_db()

    lost_count = conn.execute(
        "SELECT COUNT(*) FROM items WHERE item_type='Lost'"
    ).fetchone()[0]

    found_count = conn.execute(
        "SELECT COUNT(*) FROM items WHERE item_type='Found'"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        lost_count=lost_count,
        found_count=found_count
    )


# ================= REGISTER =================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        student_id = request.form["student_id"].strip()
        phone = request.form["phone"].strip()
        password = request.form["password"]

        if not name or not student_id or not phone or not password:
            flash("Please fill all fields.", "error")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (name, student_id, phone, password)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                student_id,
                phone,
                hashed_password
            ))

            conn.commit()
            conn.close()

            flash("Account created successfully! 🎉", "success")

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            conn.close()

            flash(
                "Student ID or phone number already exists.",
                "error"
            )

            return redirect(url_for("register"))

    return render_template("register.html")


# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        student_id = request.form["student_id"].strip()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE student_id = ?
        """, (student_id,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        flash("Invalid Student ID or password.", "error")

    return render_template("login.html")


# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully.", "success")

    return redirect(url_for("home"))


# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    my_items = conn.execute("""
        SELECT *
        FROM items
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    my_claims = conn.execute("""
        SELECT claims.*, items.title
        FROM claims
        JOIN items ON claims.item_id = items.id
        WHERE claims.claimant_id = ?
        ORDER BY claims.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        my_items=my_items,
        my_claims=my_claims
    )


# ================= REPORT ITEM =================

@app.route("/report", methods=["GET", "POST"])
@login_required
def report():

    if request.method == "POST":

        title = request.form["title"].strip()
        category = request.form["category"]
        description = request.form["description"].strip()
        location = request.form["location"].strip()
        item_date = request.form["item_date"]
        item_type = request.form["item_type"]

        if not title or not category or not location or not item_date:
            flash("Please fill all required fields.", "error")
            return redirect(url_for("report"))

        conn = get_db()

        conn.execute("""
            INSERT INTO items
            (
                user_id,
                title,
                category,
                description,
                location,
                item_date,
                item_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            title,
            category,
            description,
            location,
            item_date,
            item_type
        ))

        conn.commit()
        conn.close()

        flash(
            f"{item_type} item reported successfully! 📢",
            "success"
        )

        return redirect(url_for("dashboard"))

    return render_template("report.html")


# ================= SEARCH ITEMS =================

@app.route("/items")
def items():

    search = request.args.get("search", "").strip()
    item_type = request.args.get("type", "")

    conn = get_db()

    query = """
        SELECT items.*, users.name
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE 1=1
    """

    values = []

    if search:

        query += """
            AND (
                items.title LIKE ?
                OR items.category LIKE ?
                OR items.location LIKE ?
            )
        """

        search_value = "%" + search + "%"

        values.extend([
            search_value,
            search_value,
            search_value
        ])

    if item_type in ["Lost", "Found"]:

        query += " AND items.item_type = ?"

        values.append(item_type)

    query += " ORDER BY items.id DESC"

    all_items = conn.execute(
        query,
        values
    ).fetchall()

    conn.close()

    return render_template(
        "items.html",
        items=all_items,
        search=search,
        selected_type=item_type
    )


# ================= CLAIM ITEM =================

@app.route("/claim/<int:item_id>", methods=["POST"])
@login_required
def claim(item_id):

    message = request.form["message"].strip()

    conn = get_db()

    item = conn.execute("""
        SELECT *
        FROM items
        WHERE id = ?
    """, (item_id,)).fetchone()

    if not item:

        conn.close()

        flash("Item not found.", "error")

        return redirect(url_for("items"))

    if item["user_id"] == session["user_id"]:

        conn.close()

        flash(
            "You cannot claim your own reported item.",
            "error"
        )

        return redirect(url_for("items"))

    conn.execute("""
        INSERT INTO claims
        (
            item_id,
            claimant_id,
            message
        )
        VALUES (?, ?, ?)
    """, (
        item_id,
        session["user_id"],
        message
    ))

    conn.commit()
    conn.close()

    flash(
        "Claim request sent successfully! 🤝",
        "success"
    )

    return redirect(url_for("items"))


# ================= CLAIMS =================

@app.route("/claims")
@login_required
def claims():

    conn = get_db()

    received = conn.execute("""
        SELECT
            claims.id,
            claims.message,
            claims.status,
            items.title,
            users.name,
            users.student_id,
            users.phone
        FROM claims
        JOIN items ON claims.item_id = items.id
        JOIN users ON claims.claimant_id = users.id
        WHERE items.user_id = ?
        ORDER BY claims.id DESC
    """, (session["user_id"],)).fetchall()

    sent = conn.execute("""
        SELECT
            claims.id,
            claims.message,
            claims.status,
            items.title,
            users.name
        FROM claims
        JOIN items ON claims.item_id = items.id
        JOIN users ON items.user_id = users.id
        WHERE claims.claimant_id = ?
        ORDER BY claims.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "claims.html",
        received=received,
        sent=sent
    )


# ================= UPDATE CLAIM =================

@app.route("/claim/<int:claim_id>/<action>")
@login_required
def update_claim(claim_id, action):

    if action not in ["Approved", "Rejected"]:
        flash("Invalid action.", "error")
        return redirect(url_for("claims"))

    conn = get_db()

    claim = conn.execute("""
        SELECT claims.*, items.user_id
        FROM claims
        JOIN items ON claims.item_id = items.id
        WHERE claims.id = ?
    """, (claim_id,)).fetchone()

    if not claim:

        conn.close()

        flash("Claim not found.", "error")

        return redirect(url_for("claims"))

    if claim["user_id"] != session["user_id"]:

        conn.close()

        flash("You are not allowed to update this claim.", "error")

        return redirect(url_for("claims"))

    conn.execute("""
        UPDATE claims
        SET status = ?
        WHERE id = ?
    """, (
        action,
        claim_id
    ))

    if action == "Approved":

        conn.execute("""
            UPDATE items
            SET status = 'Claimed'
            WHERE id = ?
        """, (claim["item_id"],))

    conn.commit()
    conn.close()

    flash(
        f"Claim {action.lower()} successfully.",
        "success"
    )

    return redirect(url_for("claims"))


# ================= START =================

if __name__ == "__main__":

    init_db()

    print("\n===================================")
    print("📦 CAMPUS LOST & FOUND")
    print("===================================")
    print("🌐 http://127.0.0.1:5000")
    print("===================================\n")

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
