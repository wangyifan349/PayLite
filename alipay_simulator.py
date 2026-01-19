# alipay_simulator.py
# --------------------------------------------------------------------
# This is a self-contained Flask+sqlite3 demo for a minimal "Alipay-like"
# payment system. Features:
#  - User registration, login, logout
#  - Balance inquiry, peer-to-peer transfer
#  - Full transaction history (each entry with balance snapshot)
#  - API export of all records with token-protected authentication
#  - Pure Python, HTML templates embedded, one-file for direct execution
#  - English code style and comments, all variable names in English
#  - Safe SQL practices; no list comprehensions or expression nesting
#  - User's initial balance is 0
# Dependencies: flask
#
# Usage: python alipay_simulator.py
# --------------------------------------------------------------------
import os
import sqlite3
import secrets
from flask import Flask, session, request, redirect, url_for, render_template_string, flash, g, jsonify
app = Flask(__name__)
app.secret_key = 'your_secret_key_please_change'
DATABASE = 'alipay_sim.db'
# ======================= Database & Utility Functions ====================== #
def get_db():
    """Get a database connection returning Row objects (dict-style access)."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db
@app.teardown_appcontext
def close_connection(exception):
    """Close database connection after each request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
def initialize_db():
    """Initialize tables: users, transactions; user initial balance is 0."""
    with app.app_context():
        db = get_db()
        # Users table
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,         -- User ID
                username TEXT UNIQUE NOT NULL,                -- Username (unique)
                password TEXT NOT NULL,                       -- Plain password (for demo only)
                balance REAL DEFAULT 0,                       -- Current balance，default 0
                api_token TEXT                                -- User's API token
            )
        ''')
        # Transactions table
        db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,         -- Transaction record ID
                from_user INTEGER,                            -- Sender user ID
                to_user INTEGER,                              -- Receiver user ID
                amount REAL,                                  -- Transfer amount
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- Timestamp
                FOREIGN KEY(from_user) REFERENCES users(id),  -- Foreign key
                FOREIGN KEY(to_user) REFERENCES users(id)
            )
        ''')                                                # Commit transaction
        db.commit()
def get_user_by_id(user_id):
    """Fetch user using user_id."""
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
def get_user_by_token(token):
    """Fetch user using their API token."""
    db = get_db()
    return db.execute("SELECT * FROM users WHERE api_token=?", (token,)).fetchone()
def generate_token():
    """Generate a random token string."""
    return secrets.token_hex(24)
def set_user_token(user_id):
    """Generate a new API token and assign to the user."""
    token = generate_token()
    db = get_db()
    db.execute("UPDATE users SET api_token=? WHERE id=?", (token, user_id))       # Update user token
    db.commit()
    return token
def get_transactions_with_balance(user_id):
    """
    Return all transactions of a user including balance after each.
    Each item: dict with post_balance field.
    """
    db = get_db()
    # Query all user's transactions (ascending by time)
    sql = '''
        SELECT t.id, t.time, t.amount, t.from_user, t.to_user,
               u1.username AS from_username,
               u2.username AS to_username
        FROM transactions t
        LEFT JOIN users u1 ON t.from_user = u1.id
        LEFT JOIN users u2 ON t.to_user = u2.id
        WHERE t.from_user=? OR t.to_user=?
        ORDER BY t.time ASC, t.id ASC
    '''
    cur = db.execute(sql, (user_id, user_id))
    records = []
    balance = 0.0                              # Initial balance is 0
    for row in cur:
        row_dict = dict(row)
        if row["from_user"] == user_id:
            balance -= row["amount"]           # If sent, reduce balance
        elif row["to_user"] == user_id:
            balance += row["amount"]           # If received, increase balance
        row_dict["post_balance"] = round(balance, 2)
        records.append(row_dict)
    return records
def get_last_balance(records):
    """Get the final balance from user's records, or 0."""
    if records:
        return records[-1]["post_balance"]
    return 0.0
def require_login(f):
    """Decorator: protect view, require login."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kw)
    return wrapper
# ============================ Views / Routes ============================ #
@app.route("/")
@require_login
def index():
    """Homepage: show user balance and token."""
    user = get_user_by_id(session["user_id"])
    return render_template_string(TEMPLATES['index'], user=user, api_token=session['api_token'])
@app.route("/register", methods=['GET', 'POST'])
def register():
    """User registration view."""
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Username and password required')
            return render_template_string(TEMPLATES['register'])
        db = get_db()
        # Check unique username
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            flash('Username already exists')
            return render_template_string(TEMPLATES['register'])
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))    # Add new user
        db.commit()
        flash('Registration successful, please log in')
        return redirect(url_for('login'))
    return render_template_string(TEMPLATES['register'])
@app.route("/login", methods=['GET', 'POST'])
def login():
    """User login view."""
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if user:
            session["user_id"] = user["id"]
            token = set_user_token(user["id"])        # Issue new API token at login
            session["api_token"] = token
            return redirect(url_for('index'))
        else:
            flash("Username or password incorrect")
    return render_template_string(TEMPLATES['login'])
@app.route("/logout")
@require_login
def logout():
    """Logout and clean session."""
    session.pop("user_id", None)
    session.pop("api_token", None)
    flash("Logged out")
    return redirect(url_for("login"))
@app.route("/transfer", methods=['GET', 'POST'])
@require_login
def transfer():
    """Transfer funds to another user."""
    user = get_user_by_id(session["user_id"])
    if request.method == "POST":
        to_user_id = request.form['to_user_id']
        amount = request.form['amount']
        try:
            to_user_id = int(to_user_id)
            amount = float(amount)
        except Exception:
            flash('Enter valid User ID and Amount')
            return render_template_string(TEMPLATES['transfer'], user=user)
        if amount <= 0:
            flash('Amount must be > 0')
            return render_template_string(TEMPLATES['transfer'], user=user)
        if to_user_id == user["id"]:
            flash('Cannot transfer to yourself')
            return render_template_string(TEMPLATES['transfer'], user=user)
        db = get_db()
        if not db.execute("SELECT id FROM users WHERE id=?", (to_user_id,)).fetchone():
            flash('Target user not found')
            return render_template_string(TEMPLATES['transfer'], user=user)
        if user["balance"] < amount:
            flash("Insufficient balance")
            return render_template_string(TEMPLATES['transfer'], user=user)
        try:
            db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, user["id"]))      # Deduct balance
            db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, to_user_id))      # Add to target
            db.execute("INSERT INTO transactions (from_user, to_user, amount) VALUES (?, ?, ?)",
                        (user["id"], to_user_id, amount))        # Insert transaction record
            db.commit()
            flash('Transfer succeeded!')
            return redirect(url_for('record'))
        except Exception:
            db.rollback()
            flash('Transfer failed, please retry')
    return render_template_string(TEMPLATES['transfer'], user=user)
@app.route("/record")
@require_login
def record():
    """Show user's transaction records with balance per transaction."""
    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    records = get_transactions_with_balance(user_id)
    last_balance = get_last_balance(records)
    return render_template_string(TEMPLATES['record'], user=user, records=records, last_balance=last_balance, api_token=session['api_token'])
@app.route("/api/records")
def api_records():
    """
    API: Export all of the user's transaction records (protected with API token).
    Parameters: ?token=API_TOKEN
    Returns: JSON (all user self records with balance snapshots)
    """
    token = request.args.get('token')
    if not token:
        return jsonify({"error": "Token required"}), 403
    user = get_user_by_token(token)
    if not user:
        return jsonify({"error": "Invalid token"}), 403
    user_id = user["id"]
    records = get_transactions_with_balance(user_id)
    for r in records:
        if isinstance(r["amount"], float): r["amount"] = float(r["amount"])
        if isinstance(r["post_balance"], float): r["post_balance"] = float(r["post_balance"])
    return jsonify({
        "username": user["username"],
        "user_id": user_id,
        "init_balance": 0.0,
        "current_balance": get_last_balance(records),
        "records": records
    })
# ========================== HTML Templates (Embedded) ======================== #
BASE_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{% block title %}Alipay Simulator{% endblock %}</title>
    <!-- Bootstrap 5 CDN -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { background: #fffbe6;}
      .navbar { background: linear-gradient(90deg, #f7b733 0, #fc4a1a 100%); }
      .gold-title { color: #d4af37; letter-spacing:2px;}
      .btn-gold { background: #d4af37; border:none; color:#222;font-weight: bold;}
      .btn-gold:hover { background:#c6a44d; color:#111;}
      .form-label { color:#b37d08;}
      .table-gold th,
      .table-gold td { border-color: #eed991;}
      .table-gold thead th { background: #fff3d1;}
    </style>
    {% block extrahead %}{% endblock %}
  </head>
  <body>
    <nav class="navbar navbar-expand navbar-dark mb-4">
      <div class="container-fluid">
        <a class="navbar-brand gold-title" href="{{ url_for('index') }}">Alipay Simulator</a>
        {% if session.get('user_id') %}
          <div class="d-flex">
            <a href="{{ url_for('index') }}" class="nav-link text-dark">Home</a>
            <a href="{{ url_for('transfer') }}" class="nav-link text-dark">Transfer</a>
            <a href="{{ url_for('record') }}" class="nav-link text-dark">Records</a>
            <a href="{{ url_for('logout') }}" class="nav-link text-dark">Logout</a>
          </div>
        {% endif %}
      </div>
    </nav>
    <div class="container" style="max-width:600px;">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          {% for message in messages %}
            <div class="alert alert-warning" role="alert" style="background:#fff3d1;">
              {{ message }}
            </div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </div>
  </body>
</html>
"""

TEMPLATES = {
'login':
"""
{% extends base_template %}
{% block title %}Login{% endblock %}
{% block content %}
  <h2 class="gold-title mt-4 mb-3">User Login</h2>
  <form method="post">
    <div class="mb-3">
      <label class="form-label">Username:</label>
      <input class="form-control" autocomplete="username" name="username" required>
    </div>
    <div class="mb-3">
      <label class="form-label">Password:</label>
      <input class="form-control" autocomplete="current-password" name="password" type="password" required>
    </div>
    <button class="btn btn-gold w-100" type="submit">Login</button>
  </form>
  <div class="text-center mt-3">
    <a href="{{ url_for('register') }}">No account? Register</a>
  </div>
{% endblock %}
""",
'register':
"""
{% extends base_template %}
{% block title %}Register{% endblock %}
{% block content %}
  <h2 class="gold-title mt-4 mb-3">User Registration</h2>
  <form method="post">
    <div class="mb-3">
      <label class="form-label">Username:</label>
      <input class="form-control" name="username" required autocomplete="off">
    </div>
    <div class="mb-3">
      <label class="form-label">Password:</label>
      <input class="form-control" name="password" type="password" required>
    </div>
    <button class="btn btn-gold w-100" type="submit">Register</button>
  </form>
  <div class="text-center mt-3">
    <a href="{{ url_for('login') }}">Already have an account? Login</a>
  </div>
{% endblock %}
""",
'index':
"""
{% extends base_template %}
{% block title %}Account{% endblock %}
{% block content %}
  <div class="card shadow" style="background:rgba(255,255,255,0.9)">
    <div class="card-header text-center gold-title" style="font-size:1.4em;">
      Welcome, {{ user['username'] }}!
    </div>
    <div class="card-body text-center">
      <div class="mb-2">
        <span class="form-label">User ID:</span>
        <span class="fw-bold">{{ user['id'] }}</span>
      </div>
      <div class="mb-3">
        <span class="form-label">Balance:</span>
        <span class="fs-3 gold-title">{{ user['balance'] }}</span>
      </div>
      <div class="mb-3" style="font-size:0.95em;">
        <span class="form-label">API export token:</span>
        <input type="text" class="form-control text-primary" style="display:inline-block;width:60%;" readonly value="{{ api_token }}">
        <div class="form-text text-secondary text-start">For API data export</div>
      </div>
      <div>
        <a class="btn btn-gold w-100 mb-2" href="{{ url_for('transfer') }}">Make a Transfer</a>
        <a class="btn btn-outline-warning w-100 mb-2" href="{{ url_for('record') }}">Transaction History</a>
        <a class="btn btn-outline-secondary w-100" href="{{ url_for('logout') }}">Logout</a>
      </div>
    </div>
  </div>
{% endblock %}
""",
'transfer':
"""
{% extends base_template %}
{% block title %}Transfer{% endblock %}
{% block content %}
  <h2 class="gold-title text-center mt-4 mb-4">Make a Transfer</h2>
  <div class="mb-4">
    <div class="form-label">Your Balance: <span class="gold-title">{{ user['balance'] }}</span></div>
    <div class="form-label mb-2">Your User ID: <b>{{ user['id'] }}</b></div>
  </div>
  <form method="post">
    <div class="mb-3">
      <label class="form-label">Recipient User ID:</label>
      <input class="form-control" name="to_user_id" required pattern="[0-9]+">
    </div>
    <div class="mb-3">
      <label class="form-label">Amount:</label>
      <input class="form-control" name="amount" type="number" min="0.01" step="0.01" required>
    </div>
    <button class="btn btn-gold w-100" type="submit">Transfer</button>
  </form>
  <div class="text-center mt-3">
    <a href="{{ url_for('index') }}">Back to Home</a>
  </div>
{% endblock %}
""",
'record':
"""
{% extends base_template %}
{% block title %}Transaction Records{% endblock %}
{% block content %}
  <h2 class="gold-title text-center mt-4 mb-4">Transaction History</h2>
  <table class="table table-gold table-bordered table-hover" style="background:rgba(255,250,220,0.97)">
    <thead>
      <tr>
        <th>Time</th>
        <th>Peer</th>
        <th>Type</th>
        <th>Amount</th>
        <th>Balance</th>
      </tr>
    </thead>
    <tbody>
      {% for tx in records %}
      <tr>
        <td>{{ tx['time'] }}</td>
        <td>
          {% if tx['from_user'] == user['id'] %}
            To <span class="fw-bold gold-title">{{ tx['to_username'] }}</span> (ID:{{ tx['to_user'] }})
          {% else %}
            From <span class="fw-bold gold-title">{{ tx['from_username'] }}</span> (ID:{{ tx['from_user'] }})
          {% endif %}
        </td>
        <td>
          {% if tx['from_user'] == user['id'] %}
            <span style="color: #ff9800; font-weight:bold;">Sent</span>
          {% else %}
            <span style="color: #43a047; font-weight:bold;">Received</span>
          {% endif %}
        </td>
        <td>
          {% if tx['from_user'] == user['id'] %}
            <span style="color:red;">-{{ tx['amount'] }}</span>
          {% else %}
            <span style="color:#43a047;">+{{ tx['amount'] }}</span>
          {% endif %}
        </td>
        <td>{{ tx['post_balance'] }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <div class="text-center mt-3">
    <span style="color:#997b33;font-size:1.1em;">
      Current Balance: <b>{{ last_balance }}</b>
    </span>
    <br>
    <button class="btn btn-gold mt-3" id="exportBtn">Export All Records (JSON)</button>
    <div class="mt-2">
      <textarea class="form-control" id="exportTextarea" rows="6" readonly style="display:none;font-size:0.95em;"></textarea>
    </div>
    <div class="text-secondary mt-2" style="font-size:0.93em;">
      <b>API token: {{ api_token }}</b><br>
      Use:<br>
      <code>GET /api/records?token=YOUR_TOKEN</code>
    </div>
    <a class="btn btn-outline-secondary mt-3" href="{{ url_for('index') }}">Back to Home</a>
  </div>
  <script>
  document.getElementById("exportBtn").onclick = function() {
      var token = "{{ api_token }}";
      var url = "/api/records?token=" + token;
      fetch(url)
        .then(resp => resp.json())
        .then(res => {
          if (res && !res.error) {
            var txt = JSON.stringify(res, null, 2);
            document.getElementById("exportTextarea").style.display = '';
            document.getElementById("exportTextarea").value = txt;
          } else {
            alert(res.error || "Export failed");
          }
        });
  };
  </script>
{% endblock %}
"""
}
# Jinja2: all templates extend 'base_template'
for k in TEMPLATES:
    TEMPLATES[k] = TEMPLATES[k].replace('{% extends base_template %}', '{% extends "__base__" %}')
TEMPLATES['__base__'] = BASE_TEMPLATE
# ============================ Main Entry ============================ #
if __name__ == "__main__":
    if not os.path.exists(DATABASE):          # Ensure first-run setup
        initialize_db()
    # Attach in-memory template loader (maps template name => source)
    app.jinja_loader = type('TplLoader', (), {'get_source': lambda self, env, name:
                                              (TEMPLATES[name], name, lambda: True)})
    app.run(debug=False)
