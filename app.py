import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
import datetime
import secrets

app = Flask(__name__)
app.secret_key = 'your_secret_key_please_change'
DATABASE = 'alipay.db'

# --------------------- 数据库工具和初始化 ------------------------ #

def get_db():
    """获取数据库连接, 设置行为返回字典型数据"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """请求完成后关闭数据库连接"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库, 创建用户和转账表"""
    with app.app_context():
        db = get_db()
        # 用户表, 初始余额0
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance REAL DEFAULT 0,
            api_token TEXT
        )''')
        # 转账流水表
        db.execute('''CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            amount REAL,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(from_user) REFERENCES users(id),
            FOREIGN KEY(to_user) REFERENCES users(id)
        )''')
        db.commit()

# --------------------- 工具函数 ------------------------ #

def get_user_by_id(user_id):
    """根据用户ID获取用户, 返回Row对象"""
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cur.fetchone()
    return user

def get_user_by_token(token):
    """根据api_token查找用户"""
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE api_token=?", (token,))
    user = cur.fetchone()
    return user

def generate_token():
    """生成随机安全token"""
    return secrets.token_hex(24)

def update_user_token(user_id):
    """为用户生成新token并写入库"""
    token = generate_token()
    db = get_db()
    db.execute("UPDATE users SET api_token=? WHERE id=?", (token, user_id))
    db.commit()
    return token

def get_transfers_with_balance(user_id):
    """
    查询某用户的所有转账记录（收与支），并为每笔记录补充发生后的余额。
    - 保证SQL无表达式嵌套 (逐条拼余额)
    - 返回列表：[{"记录基础字段", "post_balance": 余额}]
    """
    db = get_db()
    # 查询时间顺序下所有相关记录
    cur = db.execute(
        '''SELECT t.id, t.time, t.amount, t.from_user, t.to_user,
                  u1.username AS from_username,
                  u2.username AS to_username
           FROM transfers t
           LEFT JOIN users u1 ON t.from_user = u1.id
           LEFT JOIN users u2 ON t.to_user = u2.id
           WHERE t.from_user=? OR t.to_user=?
           ORDER BY t.time ASC, t.id ASC''',
        (user_id, user_id)
    )
    records = []
    # 起始余额
    balance = 0
    # 查询注册后的初始余额
    user = get_user_by_id(user_id)
    if user is not None:
        balance = 0  # 注册默认0
    # 依次计算每一行的余额变化
    for row in cur:
        row_dict = dict(row)
        if row["from_user"] == user_id:
            balance -= row["amount"]
        elif row["to_user"] == user_id:
            balance += row["amount"]
        row_dict["post_balance"] = round(balance, 2)
        records.append(row_dict)
    return records

def get_last_balance_from_records(records):
    """获取最后一条记录余额"""
    if len(records) == 0:
        return 0.0
    else:
        return records[-1]["post_balance"]

# --------------------- 认证相关 ------------------------ #

def login_required(f):
    """登录保护的装饰器"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# --------------------- 路由实现 ------------------------ #

@app.route('/')
@login_required
def index():
    """首页：显示用户信息"""
    user = get_user_by_id(session["user_id"])
    return render_template('index.html', user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('用户名和密码不能为空')
            return render_template('register.html')
        db = get_db()
        # 用户名唯一性校验
        cur = db.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            flash('用户名已存在')
            return render_template('register.html')
        # 插入新用户
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        db.commit()
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        cur = db.execute("SELECT id FROM users WHERE username=? AND password=?", (username, password))
        user = cur.fetchone()
        if user:
            session["user_id"] = user["id"]
            # 登录自动生成api token
            token = update_user_token(user["id"])
            session["api_token"] = token
            return redirect(url_for('index'))
        else:
            flash("用户名或密码错误")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """退出登录"""
    session.pop("user_id", None)
    session.pop("api_token", None)
    flash("已退出登录")
    return redirect(url_for("login"))

@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    """转账页面"""
    user = get_user_by_id(session["user_id"])
    if request.method == "POST":
        to_user_id = request.form['to_user_id']
        amount = request.form['amount']
        # 校验输入（ID和金额都是数值即可）
        try:
            to_user_id = int(to_user_id)
            amount = float(amount)
        except Exception:
            flash('请输入正确的用户ID和金额')
            return render_template('transfer.html', user=user)
        if amount <= 0:
            flash('金额必须大于0')
            return render_template('transfer.html', user=user)
        if to_user_id == user["id"]:
            flash('不能给自己转账')
            return render_template('transfer.html', user=user)
        db = get_db()
        # 目标用户是否存在
        cur = db.execute("SELECT * FROM users WHERE id=?", (to_user_id,))
        to_user = cur.fetchone()
        if not to_user:
            flash('目标用户不存在')
            return render_template('transfer.html', user=user)
        # 查询自己余额
        if user["balance"] < amount:
            flash("余额不足")
            return render_template('transfer.html', user=user)
        # 安全事务处理
        try:
            # 扣自己，加对方
            db.execute("UPDATE users SET balance = balance - ? WHERE id=?",
                        (amount, user["id"]))
            db.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                        (amount, to_user_id))
            db.execute(
                "INSERT INTO transfers (from_user, to_user, amount) VALUES (?,?,?)",
                (user["id"], to_user_id, amount)
            )
            db.commit()
            flash('转账成功！')
            return redirect(url_for('record'))
        except Exception as e:
            db.rollback()
            flash('转账失败，请重试')
    return render_template('transfer.html', user=user)

@app.route('/record')
@login_required
def record():
    """前端查看转账历史（记录+变动余额）"""
    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    # 查询全记录（含余额快照）
    records = get_transfers_with_balance(user_id)
    last_balance = get_last_balance_from_records(records)
    return render_template('record.html', user=user, records=records, last_balance=last_balance)

# ------------------- JSON API: 导出全部历史 ------------------- #
@app.route('/api/records', methods=['GET'])
def api_records():
    """
    用于导出当前用户转账明细（支持token登录），
    GET参数: token=api_token（可见于前端）
    返回完整的收/支历史流水，每条附带转账之后该用户余额
    """
    token = request.args.get('token')
    if not token:
        return jsonify({"error": "请提供token"}), 403
    user = get_user_by_token(token)
    if not user:
        return jsonify({"error": "无效token"}), 403

    # 查询该用户全部转账流水及余额快照
    user_id = user["id"]
    records = get_transfers_with_balance(user_id)
    for r in records:
        # 保证所有数字都是可序列化
        if isinstance(r["amount"], float):
            r["amount"] = float(r["amount"])
        if isinstance(r["post_balance"], float):
            r["post_balance"] = float(r["post_balance"])
    # 输出所有流水
    result = {
        "username": user["username"],
        "user_id": user_id,
        "init_balance": 0.0,
        "current_balance": get_last_balance_from_records(records),
        "records": records
    }
    return jsonify(result)

# ------------------- 主入口 ------------------- #
if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=False)
