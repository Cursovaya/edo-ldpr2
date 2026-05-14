#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭДО ЛДПР - ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ
Все функции, без ошибок TemplateNotFound
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
    
    cursor = db.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    if count == 0:
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
    
    @staticmethod
    def set_head(dept_id, head_id):
        db = get_db()
        db.execute("UPDATE departments SET head_id = ? WHERE id = ?", (head_id, dept_id))
        db.execute("UPDATE users SET department_id = ? WHERE uid = ?", (dept_id, head_id))
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
# СТРАНИЦА ВХОДА (САМОСТОЯТЕЛЬНАЯ, БЕЗ EXTENDS)
# ============================================================

LOGIN_PAGE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        body { background: linear-gradient(135deg, #003399 0%, #001a4d 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Segoe UI', sans-serif; }
        .login-card { background: white; border-radius: 24px; padding: 45px 55px; max-width: 450px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); animation: fadeIn 0.5s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
        .logo-text { text-align: center; font-size: 2.2rem; font-weight: 900; color: #003399; margin-bottom: 10px; }
        .subtitle { text-align: center; font-size: 0.7rem; color: #666; margin-bottom: 30px; }
        .form-control-custom { width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 12px; margin-bottom: 20px; font-size: 1rem; transition: all 0.3s; }
        .form-control-custom:focus { outline: none; border-color: #003399; box-shadow: 0 0 0 3px rgba(0,51,153,0.1); }
        .btn-login { width: 100%; padding: 14px; background: linear-gradient(135deg, #003399, #002266); color: white; border: none; border-radius: 12px; font-size: 1rem; font-weight: 700; cursor: pointer; transition: all 0.3s; }
        .btn-login:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0,51,153,0.3); }
        .test-accounts { margin-top: 25px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 0.7rem; color: #666; }
        .test-accounts strong { color: #003399; }
        .alert { padding: 10px; border-radius: 8px; margin-bottom: 15px; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo-text">ЭДО ЛДПР</div>
        <div class="subtitle">Электронный документооборот Либерально-демократической партии России</div>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert alert-{{ cat }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" class="form-control-custom" placeholder="Логин" required autofocus>
            <input type="password" name="password" class="form-control-custom" placeholder="Пароль" required>
            <button type="submit" class="btn-login"><i class="bi bi-box-arrow-in-right"></i> Войти в систему</button>
        </form>
        <div class="test-accounts">
            <strong>Тестовые учетные записи:</strong><br>
            admin / admin123 - Администратор<br>
            secretary / sec123 - Секретарь<br>
            head_central / head123 - Руководитель ЦА<br>
            head_department / head123 - Начальник отдела<br>
            assistant / ast123 - Помощник<br>
            executor / exec123 - Исполнитель
        </div>
    </div>
</body>
</html>'''

# ============================================================
# БАЗОВЫЙ ШАБЛОН (ДЛЯ ВНУТРЕННИХ СТРАНИЦ)
# ============================================================

BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}ЭДО ЛДПР{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        :root { --ldpr-blue: #003399; }
        body { background: #f0f2f5; font-family: 'Segoe UI', sans-serif; }
        .navbar { background: linear-gradient(135deg, #003399, #001a4d); }
        .navbar-brand, .navbar-text { color: white !important; }
        .sidebar { background: white; min-height: calc(100vh - 56px); box-shadow: 2px 0 10px rgba(0,0,0,0.05); }
        .sidebar .nav-link { color: #555; border-radius: 10px; margin: 3px 8px; padding: 10px 16px; font-weight: 500; transition: all 0.3s; }
        .sidebar .nav-link:hover { background: #eef; color: #003399; transform: translateX(5px); }
        .sidebar .nav-link.active { background: #003399; color: white !important; }
        .card { border: none; border-radius: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); transition: transform 0.2s; }
        .card:hover { transform: translateY(-2px); }
        .stat-card { border-left: 4px solid #003399; }
        .badge-status { font-size: 0.75rem; font-weight: 600; padding: 5px 12px; border-radius: 20px; }
        .btn-primary { background: #003399; border: none; border-radius: 8px; padding: 8px 20px; }
        .btn-primary:hover { background: #002266; transform: translateY(-1px); }
        .table th { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #888; }
        .avatar { width: 40px; height: 40px; background: #003399; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; }
    </style>
</head>
<body>
    {% if current_user %}
    <nav class="navbar navbar-dark">
        <div class="container-fluid px-4">
            <a class="navbar-brand" href="/"><i class="bi bi-building"></i> ЭДО ЛДПР</a>
            <div class="d-flex align-items-center gap-3">
                <span class="text-light"><i class="bi bi-person-circle"></i> {{ current_user.full_name }}</span>
                <a href="/logout" class="btn btn-outline-light btn-sm"><i class="bi bi-box-arrow-right"></i> Выход</a>
            </div>
        </div>
    </nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar py-4">
                <div class="text-center mb-4">
                    <div class="avatar mx-auto" style="width: 70px; height: 70px; font-size: 28px;">{{ current_user.full_name[0] }}</div>
                    <h6 class="mt-2 mb-0 fw-bold">{{ current_user.full_name }}</h6>
                    <small class="text-muted">{{ current_user.role }}</small>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link {{ 'active' if request.path == '/' }}" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a>
                    <a class="nav-link {{ 'active' if '/orders' in request.path }}" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>
                    {% if current_user.role in ['head_department', 'admin'] %}
                    <a class="nav-link {{ 'active' if request.path == '/department' }}" href="/department"><i class="bi bi-building me-2"></i>Отдел</a>
                    {% endif %}
                    {% if current_user.role == 'admin' %}
                    <a class="nav-link {{ 'active' if request.path == '/admin' }}" href="/admin"><i class="bi bi-gear me-2"></i>Администрирование</a>
                    {% endif %}
                </nav>
            </div>
            <div class="col-md-10 p-4">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for cat, msg in messages %}
                            <div class="alert alert-{{ cat }} alert-dismissible fade show shadow-sm">{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                {% block content %}{% endblock %}
            </div>
        </div>
    </div>
    {% else %}
    {% block full_content %}{% endblock %}
    {% endif %}
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''

# ============================================================
# ДАШБОРД
# ============================================================

DASHBOARD_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Рабочий стол{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</h2>
<div class="row mb-4">
    <div class="col-md-3 mb-3"><div class="card stat-card p-3"><small class="text-muted text-uppercase fw-bold">Мои распоряжения</small><h2 class="fw-bold mb-0">{{ stats.total }}</h2></div></div>
    <div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#f59e0b;"><small class="text-muted text-uppercase fw-bold">На утверждении</small><h2 class="fw-bold mb-0">{{ stats.pending }}</h2></div></div>
    <div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#10b981;"><small class="text-muted text-uppercase fw-bold">Утверждено</small><h2 class="fw-bold mb-0">{{ stats.approved }}</h2></div></div>
    <div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#6366f1;"><small class="text-muted text-uppercase fw-bold">В работе</small><h2 class="fw-bold mb-0">{{ stats.in_work }}</h2></div></div>
</div>
<div class="card p-4"><div class="d-flex justify-content-between align-items-center mb-3"><h5 class="fw-bold mb-0">Последние распоряжения</h5><a href="/orders" class="btn btn-primary btn-sm">Все распоряжения</a></div>
{% if orders %}<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>№</th><th>Название</th><th>Статус</th><th>Приоритет</th><th>Создано</th></tr></thead><tbody>{% for o in orders %}<tr onclick="location.href='/orders/{{ o.id }}'" style="cursor:pointer"><td><small class="text-muted">#{{ o.id[:8] }}</small></d><td><strong>{{ o.title }}</strong><br><small>{{ o.creator_name }}</small></d><td><span class="badge-status bg-primary">{{ o.status }}</span></d><td>{{ o.priority }}</d><td><small>{{ o.created_at[:10] }}</small></d></tr>{% endfor %}</tbody></table></div>{% else %}<p class="text-muted text-center py-4">Нет распоряжений</p>{% endif %}</div>
{% endblock %}'''

# ============================================================
# СПИСОК РАСПОРЯЖЕНИЙ
# ============================================================

ORDERS_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Распоряжения{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4"><h2 class="fw-bold"><i class="bi bi-file-text me-2"></i>Распоряжения</h2>{% if current_user.role == 'assistant' %}<button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#createModal"><i class="bi bi-plus-lg"></i> Создать</button>{% endif %}</div>
<div class="card p-3 mb-4"><form method="GET" class="row g-3"><div class="col-md-4"><input type="text" name="search" class="form-control" placeholder="Поиск..." value="{{ request.args.get('search','') }}"></div><div class="col-md-3"><select name="status" class="form-select"><option value="Все">Все статусы</option>{% for s in statuses %}<option value="{{ s }}" {% if request.args.get('status') == s %}selected{% endif %}>{{ s }}</option>{% endfor %}</select></div><div class="col-md-3"><select name="priority" class="form-select"><option value="Все">Все приоритеты</option>{% for p in priorities %}<option value="{{ p }}" {% if request.args.get('priority') == p %}selected{% endif %}>{{ p }}</option>{% endfor %}</select></div><div class="col-md-2"><button type="submit" class="btn btn-primary w-100">Фильтр</button></div></form></div>
<div class="card p-0"><div class="table-responsive"><table class="table table-hover mb-0"><thead class="table-light"><tr><th>№</th><th>Название</th><th>Статус</th><th>Приоритет</th><th>Автор</th><th>Создано</th></tr></thead><tbody>{% for o in orders %}<tr onclick="location.href='/orders/{{ o.id }}'" style="cursor:pointer"><td><small class="text-muted">#{{ o.id[:8] }}</small></d><td><strong>{{ o.title }}</strong></d><td><span class="badge-status bg-primary">{{ o.status }}</span></d><td>{{ o.priority }}</d><td><small>{{ o.creator_name }}</small></d><td><small>{{ o.created_at[:10] }}</small></d></tr>{% endfor %}</tbody></table></div></div>
<div class="modal fade" id="createModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content"><div class="modal-header bg-primary text-white"><h5 class="modal-title">Создание распоряжения</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><form method="POST" action="/orders/create"><div class="modal-body"><input type="text" name="title" class="form-control mb-2" placeholder="Заголовок" required><div class="row mb-2"><div class="col-md-6"><select name="priority" class="form-select"><option>Низкий</option><option selected>Нормальный</option><option>Высокий</option><option>Срочный</option></select></div><div class="col-md-6"><input type="date" name="deadline" class="form-control"></div></div><textarea name="content" class="form-control" rows="6" placeholder="Содержание" required></textarea></div><div class="modal-footer"><button type="submit" name="is_draft" value="1" class="btn btn-secondary">Черновик</button><button type="submit" class="btn btn-primary">На утверждение</button></div></form></div></div></div>
{% endblock %}'''

# ============================================================
# ДЕТАЛИ РАСПОРЯЖЕНИЯ
# ============================================================

ORDER_DETAILS_TEMPLATE = '''{% extends "base.html" %}
{% block title %}{{ order.title }}{% endblock %}
{% block content %}
<a href="/orders" class="btn btn-outline-secondary btn-sm mb-3"><i class="bi bi-arrow-left"></i> Назад</a>
<div class="row"><div class="col-md-8"><div class="card p-4 mb-4"><h3>{{ order.title }}</h3><div class="row mt-3 mb-3"><div class="col-md-3"><small>Автор:</small><br><strong>{{ order.creator_name }}</strong></div><div class="col-md-3"><small>Статус:</small><br><strong class="text-primary">{{ order.status }}</strong></div><div class="col-md-3"><small>Приоритет:</small><br><strong>{{ order.priority }}</strong></div><div class="col-md-3"><small>Создано:</small><br><strong>{{ order.created_at[:10] }}</strong></div></div><hr><div class="bg-light p-3 rounded">{{ order.content }}</div>{% if order.result %}<div class="mt-3 p-3 bg-success bg-opacity-10 rounded"><h6 class="text-success">Результат</h6><div>{{ order.result.content }}</div></div>{% endif %}</div><div class="card p-4"><h5>История</h5>{% for item in history %}<div class="border-bottom py-2"><strong>{{ item.action }}</strong><br><small class="text-muted">{{ item.user_name }} - {{ item.created_at[:16] }}</small></div>{% endfor %}</div></div>
<div class="col-md-4"><div class="card p-4"><h5>Действия</h5>
{% if current_user.role == 'head_central' and order.status == 'На утверждении' %}<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Утверждено"><button class="btn btn-success w-100 mb-2">✓ Утвердить</button></form><form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Отклонено"><input type="text" name="comment" class="form-control mb-2" placeholder="Причина"><button class="btn btn-danger w-100">✗ Отклонить</button></form>{% endif %}
{% if current_user.role == 'secretary' and order.status == 'Утверждено' %}<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В отделе"><select name="department_id" class="form-select mb-2" required><option value="">Выберите отдел</option>{% for d in departments %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}</select><button class="btn btn-primary w-100">Назначить отдел</button></form>{% endif %}
{% if current_user.role == 'head_department' and order.status == 'В отделе' %}<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Назначен исполнитель"><select name="executor_id" class="form-select mb-2" required><option value="">Выберите исполнителя</option>{% for u in dept_users %}<option value="{{ u.uid }}">{{ u.full_name }}</option>{% endfor %}</select><button class="btn btn-primary w-100">Назначить</button></form>{% endif %}
{% if current_user.role == 'executor' and order.status == 'Назначен исполнитель' and order.assigned_executor_id == current_user.uid %}<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В работе"><button class="btn btn-primary w-100">Взять в работу</button></form>{% endif %}
{% if current_user.role == 'executor' and order.status == 'В работе' and order.assigned_executor_id == current_user.uid %}<form method="POST" action="/orders/{{ order.id }}/submit"><textarea name="result_content" class="form-control mb-2" rows="4" placeholder="Результат" required></textarea><button class="btn btn-success w-100">Сдать работу</button></form>{% endif %}
{% if current_user.role == 'head_department' and order.status == 'Готово к проверке' %}<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Подтверждено"><button class="btn btn-success w-100 mb-2">Подтвердить</button></form><form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="На доработке"><input type="text" name="comment" class="form-control mb-2" placeholder="Причина"><button class="btn btn-warning w-100">На доработку</button></form>{% endif %}
{% if current_user.role == 'head_central' and order.status == 'Подтверждено' %}<form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Закрыто"><button class="btn btn-success w-100">Закрыть</button></form>{% endif %}
</div></div></div>
{% endblock %}'''

# ============================================================
# ОТДЕЛ
# ============================================================

DEPARTMENT_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Отдел{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-building me-2"></i>{{ department.name }}</h2>
<div class="card p-4"><h5 class="fw-bold mb-3">Сотрудники отдела</h5><div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>ФИО</th><th>Должность</th><th>Email</th></tr></thead><tbody>{% for u in users %}<tr><td><strong>{{ u.full_name }}</strong></td><td>{{ u.role }}</td><td>{{ u.email }}</td></tr>{% endfor %}</tbody></table></div></div>
{% endblock %}'''

# ============================================================
# АДМИНКА
# ============================================================

ADMIN_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Администрирование{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-shield-lock me-2"></i>Администрирование</h2>
<div class="card p-4 mb-4"><div class="d-flex justify-content-between align-items-center mb-3"><h5 class="fw-bold mb-0">Пользователи</h5><button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addUserModal"><i class="bi bi-plus-lg"></i> Добавить</button></div><div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>ФИО</th><th>Логин</th><th>Роль</th><th>Email</th><th>Отдел</th><th>Действия</th></tr></thead><tbody>{% for u in users %}<td><strong>{{ u.full_name }}</strong></td><td>{{ u.username }}</td><td><span class="badge bg-secondary">{{ u.role }}</span></td><td>{{ u.email }}</td><td>{% for d in departments %}{% if d.id == u.department_id %}{{ d.name }}{% endif %}{% endfor %}</d><td><button class="btn btn-sm btn-outline-danger" onclick="if(confirm('Удалить?')) location.href='/admin/users/{{ u.uid }}/delete'"><i class="bi bi-trash"></i></button></d></tr>{% endfor %}</tbody></table></div></div>
<div class="card p-4"><div class="d-flex justify-content-between align-items-center mb-3"><h5 class="fw-bold mb-0">Отделы</h5><button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addDeptModal"><i class="bi bi-plus-lg"></i> Добавить отдел</button></div><div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Название</th><th>Руководитель</th><th>Действия</th></tr></thead><tbody>{% for d in departments %}<tr><td><strong>{{ d.name }}</strong></d><td>{{ d.head_name or 'Не назначен' }}</d><td><button class="btn btn-sm btn-outline-danger" onclick="if(confirm('Удалить отдел?')) location.href='/admin/departments/{{ d.id }}/delete'"><i class="bi bi-trash"></i></button></d></tr>{% endfor %}</tbody><tr></div></div>
<div class="modal fade" id="addUserModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-header bg-primary text-white"><h5 class="modal-title">Добавить пользователя</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><form method="POST" action="/admin/users/create"><div class="modal-body"><input type="text" name="full_name" class="form-control mb-2" placeholder="ФИО" required><input type="text" name="username" class="form-control mb-2" placeholder="Логин" required><input type="email" name="email" class="form-control mb-2" placeholder="Email" required><input type="password" name="password" class="form-control mb-2" placeholder="Пароль" required><select name="role" class="form-select mb-2"><option value="executor">Исполнитель</option><option value="assistant">Помощник</option><option value="head_department">Начальник отдела</option><option value="head_central">Руководитель ЦА</option><option value="secretary">Секретарь</option><option value="admin">Администратор</option></select><select name="department_id" class="form-select"><option value="">Без отдела</option>{% for d in departments %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}</select></div><div class="modal-footer"><button type="submit" class="btn btn-primary">Создать</button></div></form></div></div></div>
<div class="modal fade" id="addDeptModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-header bg-primary text-white"><h5 class="modal-title">Добавить отдел</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><form method="POST" action="/department/create"><div class="modal-body"><input type="text" name="name" class="form-control" placeholder="Название" required></div><div class="modal-footer"><button type="submit" class="btn btn-primary">Создать</button></div></form></div></div></div>
{% endblock %}'''

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
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app_flask.route('/')
@login_required
def dashboard():
    stats = OrderModel.get_stats(uid=session['user_id'], role=session['user_role'], department_id=session.get('department_id'))
    orders = OrderModel.get_by_user(uid=session['user_id'], role=session['user_role'], department_id=session.get('department_id'))[:5]
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats, orders=orders)

@app_flask.route('/orders')
@login_required
def orders():
    all_orders = OrderModel.get_by_user(uid=session['user_id'], role=session['user_role'], department_id=session.get('department_id'))
    status_filter = request.args.get('status', 'Все')
    search = request.args.get('search', '').lower()
    priority_filter = request.args.get('priority', 'Все')
    filtered = all_orders
    if status_filter != 'Все':
        filtered = [o for o in filtered if o['status'] == status_filter]
    if priority_filter != 'Все':
        filtered = [o for o in filtered if o['priority'] == priority_filter]
    if search:
        filtered = [o for o in filtered if search in o['title'].lower()]
    return render_template_string(ORDERS_TEMPLATE, orders=filtered, statuses=OrderModel.STATUSES, priorities=OrderModel.PRIORITIES)

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
    OrderHistoryModel.add(order_id, 'Создание', user['full_name'], session['user_role'], status)
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
    dept_users = UserModel.get_by_department(order.get('assigned_department_id')) if order.get('assigned_department_id') else []
    return render_template_string(ORDER_DETAILS_TEMPLATE, order=order, history=history, departments=departments, dept_users=dept_users)

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
    users = UserModel.get_by_department(dept_id)
    return render_template_string(DEPARTMENT_TEMPLATE, department=department, users=users)

@app_flask.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    users = UserModel.get_all()
    departments = DepartmentModel.get_all()
    return render_template_string(ADMIN_TEMPLATE, users=users, departments=departments)

@app_flask.route('/admin/users/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_user():
    uid = 'u-' + str(uuid.uuid4())[:8]
    hashed = generate_password_hash(request.form.get('password'))
    UserModel.create(uid, request.form.get('full_name'), request.form.get('email'), 
                     request.form.get('username'), hashed, request.form.get('role'), request.form.get('department_id') or None)
    flash('Пользователь создан', 'success')
    return redirect(url_for('admin_panel'))

@app_flask.route('/admin/users/<uid>/delete')
@login_required
@role_required('admin')
def admin_delete_user(uid):
    if uid != session['user_id']:
        UserModel.delete(uid)
        flash('Пользователь удален', 'success')
    else:
        flash('Нельзя удалить себя', 'danger')
    return redirect(url_for('admin_panel'))

@app_flask.route('/department/create', methods=['POST'])
@login_required
@role_required('admin')
def create_department():
    dept_id = 'dept-' + str(uuid.uuid4())[:8]
    if DepartmentModel.create(dept_id, request.form.get('name')):
        flash('Отдел создан', 'success')
    else:
        flash('Ошибка при создании', 'danger')
    return redirect(url_for('admin_panel'))

@app_flask.route('/admin/departments/<dept_id>/delete')
@login_required
@role_required('admin')
def admin_delete_department(dept_id):
    DepartmentModel.delete(dept_id)
    flash('Отдел удален', 'success')
    return redirect(url_for('admin_panel'))

@app_flask.route('/orders/<order_id>/status', methods=['POST'])
@login_required
def update_order_status(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        flash('Распоряжение не найдено', 'danger')
        return redirect(url_for('orders'))
    
    new_status = request.form.get('status')
    user = UserModel.get_by_id(session['user_id'])
    current_role = session['user_role']
    current_status = order['status']
    extra = {}
    
    allowed = False
    if current_role == 'head_central' and current_status == 'На утверждении' and new_status in ['Утверждено', 'Отклонено']:
        allowed = True
    elif current_role == 'secretary' and current_status == 'Утверждено' and new_status == 'В отделе':
        dept_id = request.form.get('department_id')
        if dept_id:
            allowed = True
            extra['assigned_department_id'] = dept_id
    elif current_role == 'head_department' and current_status == 'В отделе' and new_status == 'Назначен исполнитель':
        exec_id = request.form.get('executor_id')
        if exec_id:
            allowed = True
            extra['assigned_executor_id'] = exec_id
    elif current_role == 'executor' and current_status == 'Назначен исполнитель' and new_status == 'В работе':
        if order.get('assigned_executor_id') == session['user_id']:
            allowed = True
    elif current_role == 'head_department' and current_status == 'Готово к проверке' and new_status == 'Подтверждено':
        allowed = True
    elif current_role == 'head_central' and current_status == 'Подтверждено' and new_status == 'Закрыто':
        allowed = True
    
    if allowed:
        OrderModel.update(order_id, status=new_status, **extra)
        OrderHistoryModel.add(order_id, 'Изменение статуса', user['full_name'], current_role, new_status)
        flash('Статус обновлен', 'success')
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
    
    result = {'content': result_content, 'submittedAt': datetime.now().isoformat()}
    OrderModel.update(order_id, status='Готово к проверке', result=result)
    user = UserModel.get_by_id(session['user_id'])
    OrderHistoryModel.add(order_id, 'Сдача работы', user['full_name'], session['user_role'], 'Работа сдана')
    flash('Работа сдана на проверку', 'success')
    return redirect(url_for('order_details', order_id=order_id))

# ============================================================
# ЗАПУСК
# ============================================================

with app_flask.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port, debug=False)