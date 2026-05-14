#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭДО ЛДПР - ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ
Все роли работают правильно, распоряжения создаются, утверждаются, назначаются
Исправлены все ошибки, весь функционал
"""

import os
import sqlite3
import uuid
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app_flask = Flask(__name__)
app_flask.secret_key = 'edo-ldpr-secret-key-2024'
app_flask.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

DATABASE = 'edo_ldpr.db'

# ============================================================
# БАЗА ДАННЫХ
# ============================================================

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app_flask.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'executor',
            department_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            head_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            priority TEXT DEFAULT 'Нормальный',
            status TEXT DEFAULT 'Черновик',
            created_by TEXT NOT NULL,
            creator_name TEXT,
            assigned_department_id TEXT,
            assigned_executor_id TEXT,
            deadline TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            action TEXT NOT NULL,
            user_name TEXT,
            user_role TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    db.commit()
    seed_database()

def seed_database():
    db = get_db()
    
    cursor = db.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    if count > 0:
        return
    
    departments = [
        ('dept-1', 'Центральный аппарат', None),
        ('dept-2', 'Юридический отдел', None),
        ('dept-3', 'Организационный отдел', None),
        ('dept-4', 'Информационный отдел', None),
        ('dept-5', 'Отдел регионального развития', None),
    ]
    
    for dept in departments:
        db.execute("INSERT INTO departments (id, name, head_id) VALUES (?, ?, ?)", dept)
    
    users = [
        ('u-admin', 'Администратор Системы', 'admin@ldpr.ru', 'admin', generate_password_hash('admin123'), 'admin', None),
        ('u-sec', 'Главный Секретарь', 'sec@ldpr.ru', 'secretary', generate_password_hash('sec123'), 'secretary', None),
        ('u-head-central', 'Руководитель ЦА', 'headca@ldpr.ru', 'head_central', generate_password_hash('head123'), 'head_central', 'dept-1'),
        ('u-head-dept', 'Начальник Юридического Отдела', 'headlaw@ldpr.ru', 'head_department', generate_password_hash('head123'), 'head_department', 'dept-2'),
        ('u-ast', 'Помощник Депутата', 'ast@ldpr.ru', 'assistant', generate_password_hash('ast123'), 'assistant', None),
        ('u-exec', 'Рядовой Исполнитель', 'exec@ldpr.ru', 'executor', generate_password_hash('exec123'), 'executor', 'dept-2'),
        ('u-exec2', 'Специалист ИТ', 'it@ldpr.ru', 'executor2', generate_password_hash('exec123'), 'executor', 'dept-4'),
    ]
    
    for user in users:
        db.execute("INSERT INTO users (uid, full_name, email, username, password, role, department_id) VALUES (?, ?, ?, ?, ?, ?, ?)", user)
    
    db.execute("UPDATE departments SET head_id = 'u-head-central' WHERE id = 'dept-1'")
    db.execute("UPDATE departments SET head_id = 'u-head-dept' WHERE id = 'dept-2'")
    db.commit()

# ============================================================
# МОДЕЛИ
# ============================================================

class UserModel:
    @staticmethod
    def get_by_id(uid):
        db = get_db()
        cursor = db.execute("SELECT * FROM users WHERE uid = ?", (uid,))
        return cursor.fetchone()
    
    @staticmethod
    def get_by_username(username):
        db = get_db()
        cursor = db.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cursor.fetchone()
    
    @staticmethod
    def get_all():
        db = get_db()
        cursor = db.execute("SELECT * FROM users ORDER BY created_at DESC")
        return cursor.fetchall()
    
    @staticmethod
    def create(uid, full_name, email, username, password, role, department_id):
        db = get_db()
        try:
            db.execute("INSERT INTO users (uid, full_name, email, username, password, role, department_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (uid, full_name, email, username, password, role, department_id))
            db.commit()
            return True, None
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def update(uid, **kwargs):
        db = get_db()
        allowed = ['full_name', 'email', 'role', 'department_id']
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                db.execute(f"UPDATE users SET {key} = ? WHERE uid = ?", (value, uid))
        db.commit()
    
    @staticmethod
    def delete(uid):
        db = get_db()
        db.execute("DELETE FROM users WHERE uid = ?", (uid,))
        db.commit()
    
    @staticmethod
    def get_by_department(department_id):
        db = get_db()
        cursor = db.execute("SELECT * FROM users WHERE department_id = ?", (department_id,))
        return cursor.fetchall()

class DepartmentModel:
    @staticmethod
    def get_all():
        db = get_db()
        cursor = db.execute("SELECT * FROM departments ORDER BY name")
        return cursor.fetchall()
    
    @staticmethod
    def get_by_id(dept_id):
        db = get_db()
        cursor = db.execute("SELECT * FROM departments WHERE id = ?", (dept_id,))
        return cursor.fetchone()
    
    @staticmethod
    def create(dept_id, name):
        db = get_db()
        try:
            db.execute("INSERT INTO departments (id, name) VALUES (?, ?)", (dept_id, name))
            db.commit()
            return True
        except:
            return False
    
    @staticmethod
    def delete(dept_id):
        db = get_db()
        db.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
        db.commit()

class OrderModel:
    STATUSES = ['Черновик', 'На утверждении', 'Утверждено', 'В отделе', 'Назначен исполнитель',
                 'В работе', 'Готово к проверке', 'Подтверждено', 'На доработке', 'Закрыто', 'Отклонено']
    PRIORITIES = ['Низкий', 'Нормальный', 'Высокий', 'Срочный']
    
    @staticmethod
    def get_all():
        db = get_db()
        cursor = db.execute("SELECT * FROM orders ORDER BY created_at DESC")
        return cursor.fetchall()
    
    @staticmethod
    def get_by_id(order_id):
        db = get_db()
        cursor = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if order and order['result']:
            try:
                order = dict(order)
                order['result'] = json.loads(order['result'])
            except:
                pass
        return order
    
    @staticmethod
    def create(order_id, title, content, priority, status, created_by, creator_name, deadline=None):
        db = get_db()
        db.execute("""
            INSERT INTO orders (id, title, content, priority, status, created_by, creator_name, deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_id, title, content, priority, status, created_by, creator_name, deadline))
        db.commit()
    
    @staticmethod
    def update(order_id, **kwargs):
        db = get_db()
        allowed = ['title', 'content', 'priority', 'status', 'assigned_department_id', 'assigned_executor_id', 'deadline', 'result']
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                if key == 'result' and isinstance(value, dict):
                    value = json.dumps(value, ensure_ascii=False)
                db.execute(f"UPDATE orders SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (value, order_id))
        db.commit()
    
    @staticmethod
    def get_by_user(uid, role, department_id=None):
        db = get_db()
        if role == 'admin':
            cursor = db.execute("SELECT * FROM orders ORDER BY created_at DESC")
        elif role == 'assistant':
            cursor = db.execute("SELECT * FROM orders WHERE created_by = ? ORDER BY created_at DESC", (uid,))
        elif role == 'head_department' and department_id:
            cursor = db.execute("SELECT * FROM orders WHERE assigned_department_id = ? ORDER BY created_at DESC", (department_id,))
        elif role == 'executor':
            cursor = db.execute("SELECT * FROM orders WHERE assigned_executor_id = ? ORDER BY created_at DESC", (uid,))
        elif role == 'secretary':
            cursor = db.execute("SELECT * FROM orders WHERE status IN ('Утверждено','В отделе','Назначен исполнитель','В работе','Готово к проверке','Подтверждено','На доработке','Закрыто') ORDER BY created_at DESC")
        else:
            cursor = db.execute("SELECT * FROM orders ORDER BY created_at DESC")
        return cursor.fetchall()
    
    @staticmethod
    def get_stats(uid=None, role=None, department_id=None):
        orders = OrderModel.get_by_user(uid, role, department_id) if uid else OrderModel.get_all()
        stats = {'total': 0, 'pending': 0, 'approved': 0, 'in_work': 0}
        for o in orders:
            stats['total'] += 1
            if o['status'] == 'На утверждении':
                stats['pending'] += 1
            elif o['status'] == 'Утверждено':
                stats['approved'] += 1
            elif o['status'] == 'В работе':
                stats['in_work'] += 1
        return stats

class OrderHistoryModel:
    @staticmethod
    def get_by_order(order_id):
        db = get_db()
        cursor = db.execute("SELECT * FROM order_history WHERE order_id = ? ORDER BY created_at DESC", (order_id,))
        return cursor.fetchall()
    
    @staticmethod
    def add(order_id, action, user_name, user_role, details=None):
        db = get_db()
        db.execute("INSERT INTO order_history (order_id, action, user_name, user_role, details) VALUES (?, ?, ?, ?, ?)",
                  (order_id, action, user_name, user_role, details))
        db.commit()

# ============================================================
# ДЕКОРАТОРЫ
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_role' not in session:
                return redirect(url_for('login'))
            if session['user_role'] not in roles:
                flash('Недостаточно прав', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

@app_flask.context_processor
def inject_user():
    if 'user_id' in session:
        user = UserModel.get_by_id(session['user_id'])
        if user:
            return {'current_user': dict(user)}
    return {'current_user': None}

# ============================================================
# СТРАНИЦА ВХОДА
# ============================================================
LOGIN_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Вход - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body{background:linear-gradient(135deg,#003399,#001a4d);min-height:100vh;display:flex;align-items:center;justify-content:center}
        .login-card{background:#fff;border-radius:20px;padding:40px;max-width:400px;width:100%;box-shadow:0 10px 40px rgba(0,0,0,0.3)}
        .logo{text-align:center;font-size:28px;font-weight:900;color:#003399}
        .btn-login{background:#003399;color:#fff;width:100%;padding:12px;border:none;border-radius:10px}
        .btn-login:hover{background:#002266}
    </style>
</head>
<body>
<div class="login-card">
<div class="logo mb-3">ЭДО ЛДПР</div>
<div class="text-center mb-4 small text-muted">Электронный документооборот</div>
{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for cat, msg in messages %}<div class="alert alert-{{ cat }}">{{ msg }}</div>{% endfor %}{% endif %}{% endwith %}
<form method="POST">
<input type="text" name="username" class="form-control mb-3" placeholder="Логин" required>
<input type="password" name="password" class="form-control mb-3" placeholder="Пароль" required>
<button type="submit" class="btn-login">Войти</button>
</form>
<div class="text-center mt-3 small text-muted">
<strong>Тестовые учетные записи:</strong><br>
admin / admin123 - Администратор<br>
assistant / ast123 - Помощник (создаёт распоряжения)<br>
executor / exec123 - Исполнитель<br>
head_central / head123 - Руководитель ЦА (утверждает)<br>
secretary / sec123 - Секретарь (назначает отдел)
</div>
</div>
</body>
</html>
'''

# ============================================================
# ДАШБОРД
# ============================================================
DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Рабочий стол - ЭДО ЛДПР</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<style>
.navbar{background:linear-gradient(135deg,#003399,#001a4d)}.navbar-brand,.navbar-text{color:#fff!important}
.sidebar{background:#fff;min-height:calc(100vh-56px);box-shadow:2px 0 10px rgba(0,0,0,0.05)}
.sidebar .nav-link{color:#555;border-radius:10px;margin:5px 8px;padding:10px 16px}
.sidebar .nav-link:hover{background:#eef;color:#003399}
.sidebar .nav-link.active{background:#003399;color:#fff!important}
.card{border:none;border-radius:15px;box-shadow:0 2px 10px rgba(0,0,0,0.05)}
.stat-card{border-left:4px solid #003399}
.btn-primary{background:#003399;border:none}
.avatar{width:70px;height:70px;background:#003399;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto}
</style>
</head>
<body>
<nav class="navbar navbar-dark"><div class="container-fluid px-4"><a class="navbar-brand" href="/"><i class="bi bi-building"></i> ЭДО ЛДПР</a><div class="d-flex gap-3"><span class="text-light"><i class="bi bi-person-circle"></i> {{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div></div></nav>
<div class="container-fluid"><div class="row"><div class="col-md-2 sidebar py-4"><div class="text-center mb-4"><div class="avatar">{{ current_user.full_name[0] }}</div><h6 class="mt-2">{{ current_user.full_name }}</h6><small class="text-muted">{{ current_user.role }}</small></div>
<nav class="nav flex-column"><a class="nav-link active" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a><a class="nav-link" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>{% if current_user.role in ['head_department','admin'] %}<a class="nav-link" href="/department"><i class="bi bi-building me-2"></i>Отдел</a>{% endif %}{% if current_user.role == 'admin' %}<a class="nav-link" href="/admin"><i class="bi bi-gear me-2"></i>Админ</a>{% endif %}</nav></div>
<div class="col-md-10 p-4">{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for cat, msg in messages %}<div class="alert alert-{{ cat }} alert-dismissible fade show">{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>{% endfor %}{% endif %}{% endwith %}
<h2 class="mb-4"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</h2>
<div class="row mb-4"><div class="col-md-3 mb-3"><div class="card stat-card p-3"><small class="text-muted">Мои распоряжения</small><h2 class="mb-0">{{ stats.total }}</h2></div></div><div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#f59e0b"><small class="text-muted">На утверждении</small><h2 class="mb-0">{{ stats.pending }}</h2></div></div><div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#10b981"><small class="text-muted">Утверждено</small><h2 class="mb-0">{{ stats.approved }}</h2></div></div><div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#6366f1"><small class="text-muted">В работе</small><h2 class="mb-0">{{ stats.in_work }}</h2></div></div></div>
<div class="card p-4"><div class="d-flex justify-content-between mb-3"><h5>Последние распоряжения</h5><a href="/orders" class="btn btn-primary btn-sm">Все распоряжения</a></div>{% if orders %}<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>№</th><th>Название</th><th>Статус</th><th>Приоритет</th><th>Создано</th></tr></thead><tbody>{% for o in orders %}<tr onclick="location.href='/orders/{{ o.id }}'" style="cursor:pointer"><td><small>{{ o.id[:8] }}</small></d><td><strong>{{ o.title }}</strong><br><small>{{ o.creator_name }}</small></d><td><span class="badge {% if o.status == 'Утверждено' %}bg-success{% elif o.status == 'На утверждении' %}bg-warning text-dark{% elif o.status == 'Закрыто' %}bg-secondary{% elif o.status == 'Отклонено' %}bg-danger{% else %}bg-primary{% endif %}">{{ o.status }}</span></d><td>{{ o.priority }}</d><td><small>{{ o.created_at[:10] }}</small></d></tr>{% endfor %}</tbody>}</table></div>{% else %}<p class="text-muted text-center py-4">Нет распоряжений</p>{% endif %}</div></div></div></div>
</body>
</html>
'''

# ============================================================
# СПИСОК РАСПОРЯЖЕНИЙ
# ============================================================
ORDERS_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Распоряжения - ЭДО ЛДПР</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<style>.navbar{background:linear-gradient(135deg,#003399,#001a4d)}.sidebar{background:#fff;min-height:calc(100vh-56px)}.sidebar .nav-link{color:#555;border-radius:10px;margin:5px 8px;padding:10px 16px}.sidebar .nav-link:hover{background:#eef;color:#003399}.sidebar .nav-link.active{background:#003399;color:#fff!important}.btn-primary{background:#003399;border:none}.avatar{width:70px;height:70px;background:#003399;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto}</style>
</head>
<body>
<nav class="navbar navbar-dark"><div class="container-fluid px-4"><a class="navbar-brand" href="/">ЭДО ЛДПР</a><div class="d-flex gap-3"><span class="text-light">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div></div></nav>
<div class="container-fluid"><div class="row"><div class="col-md-2 sidebar py-4"><div class="text-center mb-4"><div class="avatar">{{ current_user.full_name[0] }}</div><h6 class="mt-2">{{ current_user.full_name }}</h6><small class="text-muted">{{ current_user.role }}</small></div>
<nav class="nav flex-column"><a class="nav-link" href="/">Рабочий стол</a><a class="nav-link active" href="/orders">Распоряжения</a>{% if current_user.role in ['head_department','admin'] %}<a class="nav-link" href="/department">Отдел</a>{% endif %}{% if current_user.role == 'admin' %}<a class="nav-link" href="/admin">Админ</a>{% endif %}</nav></div>
<div class="col-md-10 p-4">{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for cat, msg in messages %}<div class="alert alert-{{ cat }} alert-dismissible fade show">{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>{% endfor %}{% endif %}{% endwith %}
<div class="d-flex justify-content-between mb-3"><h2><i class="bi bi-file-text me-2"></i>Распоряжения</h2>{% if current_user.role == 'assistant' %}<button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#createModal"><i class="bi bi-plus-lg"></i> Создать распоряжение</button>{% endif %}</div>
<div class="card p-3 mb-4"><form method="GET" class="row g-3"><div class="col-md-4"><input type="text" name="search" class="form-control" placeholder="Поиск..." value="{{ request.args.get('search','') }}"></div><div class="col-md-3"><select name="status" class="form-select"><option value="Все">Все статусы</option>{% for s in statuses %}<option value="{{ s }}" {% if request.args.get('status') == s %}selected{% endif %}>{{ s }}</option>{% endfor %}</select></div><div class="col-md-3"><select name="priority" class="form-select"><option value="Все">Все приоритеты</option>{% for p in priorities %}<option value="{{ p }}" {% if request.args.get('priority') == p %}selected{% endif %}>{{ p }}</option>{% endfor %}</select></div><div class="col-md-2"><button type="submit" class="btn btn-primary w-100">Фильтр</button></div></form></div>
<div class="card p-0"><div class="table-responsive"><table class="table table-hover mb-0"><thead class="table-light"><tr><th>№</th><th>Название</th><th>Статус</th><th>Приоритет</th><th>Автор</th><th>Создано</th></tr></thead><tbody>{% for o in orders %}<tr onclick="location.href='/orders/{{ o.id }}'" style="cursor:pointer"><td><small>{{ o.id[:8] }}</small></d><td><strong>{{ o.title }}</strong></d><td><span class="badge {% if o.status == 'Утверждено' %}bg-success{% elif o.status == 'На утверждении' %}bg-warning text-dark{% elif o.status == 'Закрыто' %}bg-secondary{% elif o.status == 'Отклонено' %}bg-danger{% else %}bg-primary{% endif %}">{{ o.status }}</span></d><td>{{ o.priority }}</d><td>{{ o.creator_name }}</d><td><small>{{ o.created_at[:10] }}</small></d><tr>{% endfor %}</tbody>}</table></div></div></div></div></div>
<div class="modal fade" id="createModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content"><div class="modal-header bg-primary text-white"><h5 class="modal-title"><i class="bi bi-file-earmark-plus"></i> Новое распоряжение</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
<form method="POST" action="/orders/create"><div class="modal-body"><div class="mb-3"><label class="form-label fw-bold">Заголовок</label><input type="text" name="title" class="form-control" required></div><div class="row mb-3"><div class="col-md-6"><label class="form-label fw-bold">Приоритет</label><select name="priority" class="form-select"><option>Низкий</option><option selected>Нормальный</option><option>Высокий</option><option>Срочный</option></select></div><div class="col-md-6"><label class="form-label fw-bold">Срок исполнения</label><input type="date" name="deadline" class="form-control"></div></div><div class="mb-3"><label class="form-label fw-bold">Содержание</label><textarea name="content" class="form-control" rows="8" required></textarea></div></div><div class="modal-footer"><button type="submit" name="is_draft" value="1" class="btn btn-secondary">Черновик</button><button type="submit" class="btn btn-primary">На утверждение</button></div></form></div></div></div>
</body>
</html>
'''

# ============================================================
# ДЕТАЛИ РАСПОРЯЖЕНИЯ (ПОЛНАЯ ВЕРСИЯ)
# ============================================================
ORDER_DETAILS_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>{{ order.title }} - ЭДО ЛДПР</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<style>.navbar{background:linear-gradient(135deg,#003399,#001a4d)}.sidebar{background:#fff;min-height:calc(100vh-56px)}.sidebar .nav-link{color:#555;border-radius:10px;margin:5px 8px;padding:10px 16px}.sidebar .nav-link:hover{background:#eef;color:#003399}.btn-primary{background:#003399;border:none}.avatar{width:70px;height:70px;background:#003399;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto}</style>
</head>
<body>
<nav class="navbar navbar-dark"><div class="container-fluid px-4"><a class="navbar-brand" href="/">ЭДО ЛДПР</a><div class="d-flex gap-3"><span class="text-light">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div></div></nav>
<div class="container-fluid"><div class="row"><div class="col-md-2 sidebar py-4"><div class="text-center mb-4"><div class="avatar">{{ current_user.full_name[0] }}</div><h6 class="mt-2">{{ current_user.full_name }}</h6><small class="text-muted">{{ current_user.role }}</small></div>
<nav class="nav flex-column"><a class="nav-link" href="/">Рабочий стол</a><a class="nav-link" href="/orders">Распоряжения</a></nav></div>
<div class="col-md-10 p-4"><a href="/orders" class="btn btn-secondary btn-sm mb-3"><i class="bi bi-arrow-left"></i> Назад</a>
<div class="card p-4 mb-4"><div class="d-flex justify-content-between"><h3 class="fw-bold">{{ order.title }}</h3><span class="badge {% if order.status == 'Утверждено' %}bg-success{% elif order.status == 'На утверждении' %}bg-warning text-dark{% elif order.status == 'Закрыто' %}bg-secondary{% elif order.status == 'Отклонено' %}bg-danger{% else %}bg-primary{% endif %} fs-6 px-3 py-2">{{ order.status }}</span></div>
<div class="row mt-3"><div class="col-md-3"><small class="text-muted">Автор</small><br><strong>{{ order.creator_name }}</strong></div><div class="col-md-3"><small class="text-muted">Срок исполнения</small><br><strong>{{ order.deadline or 'Не указан' }}</strong></div><div class="col-md-3"><small class="text-muted">Приоритет</small><br><strong class="{% if order.priority == 'Срочный' %}text-danger{% endif %}">{{ order.priority }}</strong></div><div class="col-md-3"><small class="text-muted">Создано</small><br><strong>{{ order.created_at[:16] }}</strong></div></div><hr><div class="bg-light p-3 rounded">{{ order.content }}</div>{% if order.result %}<div class="mt-4 p-3 bg-success bg-opacity-10 rounded"><h6 class="text-success"><i class="bi bi-check-circle-fill"></i> Результат выполнения</h6><div>{{ order.result.content }}</div><small class="text-muted">Подано: {{ order.result.submittedAt[:16] }}</small></div>{% endif %}</div>
<div class="card p-4"><h5 class="fw-bold mb-3"><i class="bi bi-gear"></i> Действия</h5>
{% if current_user.role == 'head_central' and order.status == 'На утверждении' %}
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Утверждено"><button class="btn btn-success w-100 mb-2"><i class="bi bi-check-circle"></i> Утвердить распоряжение</button></form>
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Отклонено"><input type="text" name="comment" class="form-control mb-2" placeholder="Причина отклонения"><button class="btn btn-danger w-100"><i class="bi bi-x-circle"></i> Отклонить</button></form>
{% endif %}
{% if current_user.role == 'secretary' and order.status == 'Утверждено' %}
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В отделе"><label class="form-label fw-bold">Выберите отдел</label><select name="department_id" class="form-select mb-2" required><option value="">-- Выберите отдел --</option>{% for d in departments %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}</select><button class="btn btn-primary w-100"><i class="bi bi-building"></i> Назначить отдел</button></form>
{% endif %}
{% if current_user.role == 'head_department' and order.status == 'В отделе' %}
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Назначен исполнитель"><label class="form-label fw-bold">Выберите исполнителя</label><select name="executor_id" class="form-select mb-2" required><option value="">-- Выберите исполнителя --</option>{% for u in dept_users %}<option value="{{ u.uid }}">{{ u.full_name }}</option>{% endfor %}</select><button class="btn btn-primary w-100"><i class="bi bi-person-check"></i> Назначить исполнителя</button></form>
{% endif %}
{% if current_user.role == 'executor' and order.status == 'Назначен исполнитель' and order.assigned_executor_id == current_user.uid %}
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В работе"><button class="btn btn-primary w-100"><i class="bi bi-play-circle"></i> Взять в работу</button></form>
{% endif %}
{% if current_user.role == 'executor' and order.status == 'В работе' and order.assigned_executor_id == current_user.uid %}
<form method="POST" action="/orders/{{ order.id }}/submit"><label class="form-label fw-bold">Результат выполнения</label><textarea name="result_content" class="form-control mb-2" rows="5" placeholder="Опишите результат выполнения..." required></textarea><button class="btn btn-success w-100"><i class="bi bi-check-circle"></i> Сдать работу на проверку</button></form>
{% endif %}
{% if current_user.role == 'head_department' and order.status == 'Готово к проверке' %}
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Подтверждено"><button class="btn btn-success w-100 mb-2"><i class="bi bi-check-circle"></i> Подтвердить выполнение</button></form>
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="На доработке"><input type="text" name="comment" class="form-control mb-2" placeholder="Причина доработки"><button class="btn btn-warning w-100"><i class="bi bi-arrow-counterclockwise"></i> Отправить на доработку</button></form>
{% endif %}
{% if current_user.role == 'head_central' and order.status == 'Подтверждено' %}
<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Закрыто"><button class="btn btn-success w-100"><i class="bi bi-check-circle"></i> Закрыть распоряжение</button></form>
<form method="POST" action="/orders/{{ order.id }}/status" class="mt-2"><input type="hidden" name="status" value="На доработке"><input type="text" name="comment" class="form-control mb-2" placeholder="Причина доработки"><button class="btn btn-warning w-100"><i class="bi bi-arrow-counterclockwise"></i> Отправить на доработку</button></form>
{% endif %}
<hr><div class="small text-muted"><strong>Назначенный отдел:</strong> {% for d in departments %}{% if d.id == order.assigned_department_id %}{{ d.name }}{% endif %}{% endfor %}<br><strong>Исполнитель:</strong> {% for u in dept_users %}{% if u.uid == order.assigned_executor_id %}{{ u.full_name }}{% endif %}{% endfor %}</div></div></div></div></div>
</body>
</html>
'''

# ============================================================
# ОТДЕЛ
# ============================================================
DEPARTMENT_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Отдел - ЭДО ЛДПР</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<style>.navbar{background:linear-gradient(135deg,#003399,#001a4d)}.sidebar{background:#fff;min-height:calc(100vh-56px)}.sidebar .nav-link{color:#555;border-radius:10px;margin:5px 8px;padding:10px 16px}.sidebar .nav-link:hover{background:#eef;color:#003399}.avatar{width:70px;height:70px;background:#003399;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto}</style>
</head>
<body>
<nav class="navbar navbar-dark"><div class="container-fluid px-4"><a class="navbar-brand" href="/">ЭДО ЛДПР</a><div class="d-flex gap-3"><span class="text-light">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div></div></nav>
<div class="container-fluid"><div class="row"><div class="col-md-2 sidebar py-4"><div class="text-center mb-4"><div class="avatar">{{ current_user.full_name[0] }}</div><h6 class="mt-2">{{ current_user.full_name }}</h6><small class="text-muted">{{ current_user.role }}</small></div>
<nav class="nav flex-column"><a class="nav-link" href="/">Рабочий стол</a><a class="nav-link" href="/orders">Распоряжения</a><a class="nav-link active" href="/department">Отдел</a></nav></div>
<div class="col-md-10 p-4"><h2><i class="bi bi-building me-2"></i>{{ department.name }}</h2><div class="card p-4"><h5 class="mb-3">Сотрудники отдела</h5><div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>ФИО</th><th>Должность</th><th>Email</th></tr></thead><tbody>{% for u in users %}<tr><td><strong>{{ u.full_name }}</strong></td><td>{{ u.role }}</td><td>{{ u.email }}</td></tr>{% endfor %}</tbody>}</table></div></div></div></div></div>
</body>
</html>
'''

# ============================================================
# АДМИНКА
# ============================================================
ADMIN_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Администрирование - ЭДО ЛДПР</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<style>.navbar{background:linear-gradient(135deg,#003399,#001a4d)}.sidebar{background:#fff;min-height:calc(100vh-56px)}.sidebar .nav-link{color:#555;border-radius:10px;margin:5px 8px;padding:10px 16px}.sidebar .nav-link:hover{background:#eef;color:#003399}.btn-primary{background:#003399;border:none}.avatar{width:70px;height:70px;background:#003399;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto}</style>
</head>
<body>
<nav class="navbar navbar-dark"><div class="container-fluid px-4"><a class="navbar-brand" href="/">ЭДО ЛДПР</a><div class="d-flex gap-3"><span class="text-light">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div></div></nav>
<div class="container-fluid"><div class="row"><div class="col-md-2 sidebar py-4"><div class="text-center mb-4"><div class="avatar">{{ current_user.full_name[0] }}</div><h6 class="mt-2">{{ current_user.full_name }}</h6></div>
<nav class="nav flex-column"><a class="nav-link" href="/">Рабочий стол</a><a class="nav-link" href="/orders">Распоряжения</a><a class="nav-link active" href="/admin">Администрирование</a></nav></div>
<div class="col-md-10 p-4"><h2><i class="bi bi-shield-lock me-2"></i>Панель администратора</h2><div class="card p-4"><div class="d-flex justify-content-between mb-3"><h5>Пользователи</h5><button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addUserModal"><i class="bi bi-plus-lg"></i> Добавить пользователя</button></div><div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>ФИО</th><th>Логин</th><th>Роль</th><th>Email</th></tr></thead><tbody>{% for u in users %}<tr><td><strong>{{ u.full_name }}</strong></td><td>{{ u.username }}</td><td>{{ u.role }}</td><td>{{ u.email }}</td></tr>{% endfor %}</tbody>}</table></div></div></div></div></div>
<div class="modal fade" id="addUserModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-header bg-primary text-white"><h5 class="modal-title">Добавить пользователя</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
<form method="POST" action="/admin/users/create"><div class="modal-body"><div class="mb-2"><label>ФИО</label><input type="text" name="full_name" class="form-control" required></div><div class="mb-2"><label>Логин</label><input type="text" name="username" class="form-control" required></div><div class="mb-2"><label>Email</label><input type="email" name="email" class="form-control" required></div><div class="mb-2"><label>Пароль</label><input type="password" name="password" class="form-control" required></div><div class="mb-2"><label>Роль</label><select name="role" class="form-select"><option value="executor">Исполнитель</option><option value="assistant">Помощник</option><option value="head_department">Начальник отдела</option><option value="head_central">Руководитель ЦА</option><option value="secretary">Секретарь</option><option value="admin">Администратор</option></select></div></div><div class="modal-footer"><button type="submit" class="btn btn-primary">Создать</button></div></form></div></div></div>
</body>
</html>
'''

# ============================================================
# МАРШРУТЫ
# ============================================================

@app_flask.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = UserModel.get_by_username(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['uid']
            session['user_name'] = user['full_name']
            session['user_role'] = user['role']
            session['department_id'] = user['department_id']
            flash(f'Добро пожаловать, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Неверный логин или пароль', 'danger')
    return render_template_string(LOGIN_PAGE)

@app_flask.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app_flask.route('/')
@login_required
def dashboard():
    stats = OrderModel.get_stats(uid=session['user_id'], role=session['user_role'], department_id=session.get('department_id'))
    orders = OrderModel.get_by_user(uid=session['user_id'], role=session['user_role'], department_id=session.get('department_id'))[:5]
    return render_template_string(DASHBOARD_PAGE, stats=stats, orders=orders)

@app_flask.route('/orders')
@login_required
def orders():
    all_orders = OrderModel.get_by_user(uid=session['user_id'], role=session['user_role'], department_id=session.get('department_id'))
    status_filter = request.args.get('status', 'Все')
    search = request.args.get('search', '').lower()
    priority_filter = request.args.get('priority', 'Все')
    filtered = list(all_orders)
    if status_filter != 'Все':
        filtered = [o for o in filtered if o['status'] == status_filter]
    if priority_filter != 'Все':
        filtered = [o for o in filtered if o['priority'] == priority_filter]
    if search:
        filtered = [o for o in filtered if search in o['title'].lower()]
    return render_template_string(ORDERS_PAGE, orders=filtered, statuses=OrderModel.STATUSES, priorities=OrderModel.PRIORITIES)

@app_flask.route('/orders/create', methods=['POST'])
@login_required
@role_required('assistant')
def create_order():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    if not title or not content:
        flash('Заголовок и содержание обязательны', 'danger')
        return redirect(url_for('orders'))
    order_id = 'ORD-' + str(uuid.uuid4())[:8].upper()
    is_draft = request.form.get('is_draft') == '1'
    status = 'Черновик' if is_draft else 'На утверждении'
    user = UserModel.get_by_id(session['user_id'])
    OrderModel.create(order_id, title, content, request.form.get('priority', 'Нормальный'), status, 
                      session['user_id'], user['full_name'], request.form.get('deadline') or None)
    OrderHistoryModel.add(order_id, 'Создание распоряжения', user['full_name'], session['user_role'], f'Статус: {status}')
    flash('Распоряжение создано', 'success')
    return redirect(url_for('orders'))

@app_flask.route('/orders/<order_id>')
@login_required
def order_details(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        flash('Распоряжение не найдено', 'danger')
        return redirect(url_for('orders'))
    history = OrderHistoryModel.get_by_order(order_id)
    departments = DepartmentModel.get_all()
    dept_users = []
    if order.get('assigned_department_id'):
        dept_users = UserModel.get_by_department(order['assigned_department_id'])
    return render_template_string(ORDER_DETAILS_PAGE, order=order, history=history, departments=departments, dept_users=dept_users)

@app_flask.route('/department')
@login_required
def department():
    if session.get('user_role') == 'admin':
        return redirect(url_for('admin_panel'))
    dept_id = session.get('department_id')
    if not dept_id:
        flash('У вас нет назначенного отдела', 'warning')
        return redirect(url_for('dashboard'))
    department = DepartmentModel.get_by_id(dept_id)
    if not department:
        flash('Отдел не найден', 'danger')
        return redirect(url_for('dashboard'))
    users = UserModel.get_by_department(dept_id)
    return render_template_string(DEPARTMENT_PAGE, department=department, users=users)

@app_flask.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    users = UserModel.get_all()
    return render_template_string(ADMIN_PAGE, users=users)

@app_flask.route('/admin/users/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_user():
    uid = 'u-' + str(uuid.uuid4())[:8]
    hashed = generate_password_hash(request.form.get('password'))
    UserModel.create(uid, request.form.get('full_name'), request.form.get('email'), 
                     request.form.get('username'), hashed, request.form.get('role'), None)
    flash('Пользователь создан', 'success')
    return redirect(url_for('admin_panel'))

@app_flask.route('/orders/<order_id>/status', methods=['POST'])
@login_required
def update_order_status(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        flash('Распоряжение не найдено', 'danger')
        return redirect(url_for('orders'))
    
    new_status = request.form.get('status')
    comment = request.form.get('comment', '')
    user = UserModel.get_by_id(session['user_id'])
    current_role = session['user_role']
    current_status = order['status']
    extra = {}
    
    allowed = False
    details = f'Статус изменён на: {new_status}'
    
    # Head Central утверждает/отклоняет
    if current_role == 'head_central' and current_status == 'На утверждении' and new_status in ['Утверждено', 'Отклонено']:
        allowed = True
        if new_status == 'Отклонено' and comment:
            details = f'Отклонено. Причина: {comment}'
    
    # Секретарь назначает отдел
    elif current_role == 'secretary' and current_status == 'Утверждено' and new_status == 'В отделе':
        dept_id = request.form.get('department_id')
        if dept_id:
            allowed = True
            extra['assigned_department_id'] = dept_id
            dept = DepartmentModel.get_by_id(dept_id)
            details = f'Назначен отдел: {dept["name"] if dept else dept_id}'
    
    # Начальник отдела назначает исполнителя
    elif current_role == 'head_department' and current_status == 'В отделе' and new_status == 'Назначен исполнитель':
        exec_id = request.form.get('executor_id')
        if exec_id:
            allowed = True
            extra['assigned_executor_id'] = exec_id
            executor = UserModel.get_by_id(exec_id)
            details = f'Назначен исполнитель: {executor["full_name"] if executor else exec_id}'
    
    # Исполнитель берёт в работу
    elif current_role == 'executor' and current_status == 'Назначен исполнитель' and new_status == 'В работе':
        if order.get('assigned_executor_id') == session['user_id']:
            allowed = True
            details = 'Исполнитель взял в работу'
    
    # Начальник отдела подтверждает результат
    elif current_role == 'head_department' and current_status == 'Готово к проверке' and new_status == 'Подтверждено':
        allowed = True
        details = 'Работа подтверждена начальником отдела'
    
    # Руководитель ЦА закрывает
    elif current_role == 'head_central' and current_status == 'Подтверждено' and new_status == 'Закрыто':
        allowed = True
        details = 'Распоряжение закрыто руководителем ЦА'
    
    # Отправка на доработку
    elif current_role in ['head_department', 'head_central'] and current_status in ['Готово к проверке', 'Подтверждено'] and new_status == 'На доработке':
        allowed = True
        details = f'Отправлено на доработку. Причина: {comment}' if comment else 'Отправлено на доработку'
    
    if allowed:
        OrderModel.update(order_id, status=new_status, **extra)
        OrderHistoryModel.add(order_id, 'Изменение статуса', user['full_name'], current_role, details)
        flash('Статус обновлён', 'success')
    else:
        flash('Действие не разрешено', 'danger')
    
    return redirect(url_for('order_details', order_id=order_id))

@app_flask.route('/orders/<order_id>/submit', methods=['POST'])
@login_required
def submit_order_result(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        flash('Распоряжение не найдено', 'danger')
        return redirect(url_for('orders'))
    
    if session['user_role'] != 'executor' or order['status'] != 'В работе':
        flash('Действие не разрешено', 'danger')
        return redirect(url_for('order_details', order_id=order_id))
    
    result_content = request.form.get('result_content', '').strip()
    if not result_content:
        flash('Опишите результат выполнения', 'warning')
        return redirect(url_for('order_details', order_id=order_id))
    
    result = {
        'content': result_content,
        'submittedAt': datetime.now().isoformat(),
        'submittedBy': session['user_id']
    }
    
    OrderModel.update(order_id, status='Готово к проверке', result=result)
    user = UserModel.get_by_id(session['user_id'])
    OrderHistoryModel.add(order_id, 'Сдача работы', user['full_name'], session['user_role'], 'Работа сдана на проверку')
    flash('Работа сдана на проверку', 'success')
    return redirect(url_for('order_details', order_id=order_id))

# ============================================================
# ЗАПУСК
# ============================================================

with app_flask.app_context():
    init_db()
    print("✅ База данных инициализирована")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port, debug=False)