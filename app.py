#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭДО ЛДПР - ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ
Все шаблоны в одном файле, без ошибок TemplateNotFound
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
# ВСЕ ШАБЛОНЫ В ОДНОМ ФАЙЛЕ (БЕЗ EXTENDS)
# ============================================================

# ШАБЛОН ВХОДА
LOGIN_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Вход - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        body { background: linear-gradient(135deg, #003399, #001a4d); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-card { background: white; border-radius: 20px; padding: 40px; max-width: 400px; width: 100%; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
        .logo { text-align: center; font-size: 28px; font-weight: 900; color: #003399; }
        .btn-login { background: #003399; color: white; width: 100%; padding: 12px; border: none; border-radius: 10px; font-weight: bold; }
        .btn-login:hover { background: #002266; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo mb-3">ЭДО ЛДПР</div>
        <div class="text-center mb-4 small text-muted">Электронный документооборот</div>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert alert-{{ cat }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" class="form-control mb-3" placeholder="Логин" required>
            <input type="password" name="password" class="form-control mb-3" placeholder="Пароль" required>
            <button type="submit" class="btn-login">Войти</button>
        </form>
        <div class="text-center mt-3 small text-muted">
            admin/admin123 | secretary/sec123 | executor/exec123
        </div>
    </div>
</body>
</html>'''

# ШАБЛОН ДАШБОРДА
DASHBOARD_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Рабочий стол - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        .navbar { background: #003399; }
        .navbar-brand, .nav-link, .navbar-text { color: white !important; }
        .sidebar { background: white; min-height: 100vh; box-shadow: 2px 0 5px rgba(0,0,0,0.1); }
        .sidebar .nav-link { color: #333; }
        .sidebar .nav-link:hover { background: #eef; color: #003399; }
        .card { border-radius: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .stat-card { border-left: 4px solid #003399; }
        .btn-primary { background: #003399; border: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">ЭДО ЛДПР</a>
            <div class="d-flex">
                <span class="navbar-text me-3">{{ current_user.full_name }}</span>
                <a href="/logout" class="btn btn-outline-light btn-sm">Выход</a>
            </div>
        </div>
    </nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar p-3">
                <div class="text-center mb-4">
                    <div class="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center mx-auto mb-2" style="width: 60px; height: 60px;">{{ current_user.full_name[0] }}</div>
                    <h6>{{ current_user.full_name }}</h6>
                    <small class="text-muted">{{ current_user.role }}</small>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a>
                    <a class="nav-link" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>
                    {% if current_user.role == 'admin' %}
                    <a class="nav-link" href="/admin"><i class="bi bi-gear me-2"></i>Админ</a>
                    {% endif %}
                </nav>
            </div>
            <div class="col-md-10 p-4">
                <h2 class="mb-4">Рабочий стол</h2>
                <div class="row mb-4">
                    <div class="col-md-3 mb-3"><div class="card stat-card p-3"><small>Мои распоряжения</small><h2>{{ stats.total }}</h2></div></div>
                    <div class="col-md-3 mb-3"><div class="card stat-card p-3"><small>На утверждении</small><h2>{{ stats.pending }}</h2></div></div>
                    <div class="col-md-3 mb-3"><div class="card stat-card p-3"><small>Утверждено</small><h2>{{ stats.approved }}</h2></div></div>
                    <div class="col-md-3 mb-3"><div class="card stat-card p-3"><small>В работе</small><h2>{{ stats.in_work }}</h2></div></div>
                </div>
                <div class="card p-3">
                    <h5>Последние распоряжения</h5>
                    <table class="table">
                        <thead><tr><th>Название</th><th>Статус</th><th>Создано</th></tr></thead>
                        <tbody>
                            {% for o in orders %}
                            <tr onclick="location.href='/orders/{{ o.id }}'" style="cursor:pointer">
                                <td>{{ o.title }}</d><td>{{ o.status }}</d><td>{{ o.created_at[:10] }}</d>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</body>
</html>'''

# ШАБЛОН СПИСКА РАСПОРЯЖЕНИЙ
ORDERS_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Распоряжения - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        .navbar { background: #003399; }
        .navbar-brand, .navbar-text { color: white !important; }
        .sidebar { background: white; min-height: 100vh; }
        .sidebar .nav-link { color: #333; }
        .sidebar .nav-link:hover { background: #eef; color: #003399; }
        .btn-primary { background: #003399; border: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">ЭДО ЛДПР</a>
            <div class="d-flex"><span class="navbar-text me-3">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div>
        </div>
    </nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar p-3">
                <div class="text-center mb-4">
                    <div class="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center mx-auto mb-2" style="width: 60px; height: 60px;">{{ current_user.full_name[0] }}</div>
                    <h6>{{ current_user.full_name }}</h6>
                    <small class="text-muted">{{ current_user.role }}</small>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a>
                    <a class="nav-link active" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>
                    {% if current_user.role == 'admin' %}<a class="nav-link" href="/admin"><i class="bi bi-gear me-2"></i>Админ</a>{% endif %}
                </nav>
            </div>
            <div class="col-md-10 p-4">
                <h2 class="mb-4">Распоряжения</h2>
                {% if current_user.role == 'assistant' %}
                <button class="btn btn-primary mb-3" data-bs-toggle="modal" data-bs-target="#createModal">+ Создать</button>
                {% endif %}
                <div class="card p-3">
                    <table class="table">
                        <thead><tr><th>Название</th><th>Статус</th><th>Автор</th><th>Создано</th></tr></thead>
                        <tbody>
                            {% for o in orders %}
                            <tr onclick="location.href='/orders/{{ o.id }}'" style="cursor:pointer">
                                <td>{{ o.title }}</d><td>{{ o.status }}</d><td>{{ o.creator_name }}</d><td>{{ o.created_at[:10] }}</d>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    <div class="modal fade" id="createModal" tabindex="-1">
        <div class="modal-dialog"><div class="modal-content">
            <div class="modal-header"><h5>Новое распоряжение</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <form method="POST" action="/orders/create">
                <div class="modal-body">
                    <input type="text" name="title" class="form-control mb-2" placeholder="Заголовок" required>
                    <select name="priority" class="form-select mb-2"><option>Нормальный</option><option>Высокий</option><option>Срочный</option></select>
                    <textarea name="content" class="form-control" rows="5" placeholder="Содержание" required></textarea>
                </div>
                <div class="modal-footer">
                    <button type="submit" name="is_draft" value="1" class="btn btn-secondary">Черновик</button>
                    <button type="submit" class="btn btn-primary">На утверждение</button>
                </div>
            </form>
        </div></div>
    </div>
</body>
</html>'''

# ШАБЛОН ДЕТАЛЕЙ РАСПОРЯЖЕНИЯ
ORDER_DETAILS_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{{ order.title }} - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        .navbar { background: #003399; }
        .navbar-brand, .navbar-text { color: white !important; }
        .sidebar { background: white; min-height: 100vh; }
        .sidebar .nav-link { color: #333; }
        .btn-primary { background: #003399; border: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">ЭДО ЛДПР</a>
            <div class="d-flex"><span class="navbar-text me-3">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div>
        </div>
    </nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar p-3">
                <div class="text-center mb-4">
                    <div class="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center mx-auto mb-2" style="width: 60px; height: 60px;">{{ current_user.full_name[0] }}</div>
                    <h6>{{ current_user.full_name }}</h6>
                    <small class="text-muted">{{ current_user.role }}</small>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a>
                    <a class="nav-link" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>
                </nav>
            </div>
            <div class="col-md-10 p-4">
                <a href="/orders" class="btn btn-secondary btn-sm mb-3">← Назад</a>
                <div class="card p-4">
                    <h3>{{ order.title }}</h3>
                    <div class="row mt-3">
                        <div class="col-md-3"><small>Автор:</small><br><strong>{{ order.creator_name }}</strong></div>
                        <div class="col-md-3"><small>Статус:</small><br><strong class="text-primary">{{ order.status }}</strong></div>
                        <div class="col-md-3"><small>Приоритет:</small><br><strong>{{ order.priority }}</strong></div>
                        <div class="col-md-3"><small>Создано:</small><br><strong>{{ order.created_at[:10] }}</strong></div>
                    </div>
                    <hr>
                    <div class="bg-light p-3 rounded">{{ order.content }}</div>
                </div>
                <div class="card p-4 mt-3">
                    <h5>Действия</h5>
                    {% if current_user.role == 'head_central' and order.status == 'На утверждении' %}
                    <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Утверждено"><button class="btn btn-success w-100">✓ Утвердить</button></form>
                    {% endif %}
                    {% if current_user.role == 'secretary' and order.status == 'Утверждено' %}
                    <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В отделе"><button class="btn btn-primary w-100">Назначить отдел</button></form>
                    {% endif %}
                    {% if current_user.role == 'head_department' and order.status == 'В отделе' %}
                    <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Назначен исполнитель"><button class="btn btn-primary w-100">Назначить исполнителя</button></form>
                    {% endif %}
                    {% if current_user.role == 'executor' and order.status == 'Назначен исполнитель' %}
                    <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В работе"><button class="btn btn-primary w-100">Взять в работу</button></form>
                    {% endif %}
                    {% if current_user.role == 'executor' and order.status == 'В работе' %}
                    <form method="POST" action="/orders/{{ order.id }}/submit"><textarea name="result_content" class="form-control mb-2" placeholder="Результат" required></textarea><button class="btn btn-success w-100">Сдать работу</button></form>
                    {% endif %}
                    {% if current_user.role == 'head_central' and order.status == 'Подтверждено' %}
                    <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Закрыто"><button class="btn btn-success w-100">Закрыть</button></form>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</body>
</html>'''

# ШАБЛОН АДМИНКИ
ADMIN_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Администрирование - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        .navbar { background: #003399; }
        .sidebar { background: white; min-height: 100vh; }
        .btn-primary { background: #003399; border: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">ЭДО ЛДПР</a>
            <div class="d-flex"><span class="navbar-text me-3">{{ current_user.full_name }}</span><a href="/logout" class="btn btn-outline-light btn-sm">Выход</a></div>
        </div>
    </nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar p-3">
                <div class="text-center mb-4">
                    <div class="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center mx-auto mb-2" style="width: 60px; height: 60px;">{{ current_user.full_name[0] }}</div>
                    <h6>{{ current_user.full_name }}</h6>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/">Рабочий стол</a>
                    <a class="nav-link" href="/orders">Распоряжения</a>
                    <a class="nav-link active" href="/admin">Администрирование</a>
                </nav>
            </div>
            <div class="col-md-10 p-4">
                <h2>Пользователи</h2>
                <button class="btn btn-primary mb-3" data-bs-toggle="modal" data-bs-target="#addUserModal">+ Добавить</button>
                <div class="card p-3">
                    <table class="table">
                        <thead><tr><th>ФИО</th><th>Логин</th><th>Роль</th><th>Email</th></tr></thead>
                        <tbody>
                            {% for u in users %}
                            <tr><td>{{ u.full_name }}</d><td>{{ u.username }}</d><td>{{ u.role }}</d><td>{{ u.email }}</d></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    <div class="modal fade" id="addUserModal" tabindex="-1">
        <div class="modal-dialog"><div class="modal-content">
            <div class="modal-header"><h5>Добавить пользователя</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <form method="POST" action="/admin/users/create">
                <div class="modal-body">
                    <input type="text" name="full_name" class="form-control mb-2" placeholder="ФИО" required>
                    <input type="text" name="username" class="form-control mb-2" placeholder="Логин" required>
                    <input type="email" name="email" class="form-control mb-2" placeholder="Email" required>
                    <input type="password" name="password" class="form-control mb-2" placeholder="Пароль" required>
                    <select name="role" class="form-select"><option value="executor">Исполнитель</option><option value="assistant">Помощник</option><option value="head_department">Начальник отдела</option><option value="head_central">Руководитель ЦА</option><option value="secretary">Секретарь</option><option value="admin">Администратор</option></select>
                </div>
                <div class="modal-footer"><button type="submit" class="btn btn-primary">Создать</button></div>
            </form>
        </div></div>
    </div>
</body>
</html>'''

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
    return render_template_string(LOGIN_TEMPLATE)

@app_flask.route('/logout')
def logout():
    session.clear()
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
    return render_template_string(ORDERS_TEMPLATE, orders=all_orders)

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
    return render_template_string(ORDER_DETAILS_TEMPLATE, order=order)

@app_flask.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    users = UserModel.get_all()
    return render_template_string(ADMIN_TEMPLATE, users=users)

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
    user = UserModel.get_by_id(session['user_id'])
    OrderModel.update(order_id, status=new_status)
    OrderHistoryModel.add(order_id, 'Изменение статуса', user['full_name'], session['user_role'], new_status)
    flash('Статус обновлен', 'success')
    return redirect(url_for('order_details', order_id=order_id))

@app_flask.route('/orders/<order_id>/submit', methods=['POST'])
@login_required
def submit_order_result(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        flash('Распоряжение не найдено', 'danger')
        return redirect(url_for('orders'))
    
    result_content = request.form.get('result_content', '').strip()
    result = {'content': result_content, 'submittedAt': datetime.now().isoformat()}
    OrderModel.update(order_id, status='Готово к проверке', result=result)
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