#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭДО ЛДПР - ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ для Render
Оригинальный дизайн, все функции, картинка фона
"""

import os
import json
import secrets
import uuid
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, flash, g
)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

app_flask = Flask(__name__)
app_flask.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app_flask.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")

def get_db():
    if 'db' not in g:
        parsed = urlparse(DATABASE_URL)
        g.db = psycopg2.connect(
            database=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
            cursor_factory=RealDictCursor
        )
    return g.db

@app_flask.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()
    
    # Таблицы
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'executor',
            department_id TEXT,
            avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            head_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
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
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS order_history (
            id SERIAL PRIMARY KEY,
            order_id TEXT NOT NULL,
            action TEXT NOT NULL,
            user_name TEXT,
            user_role TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    db.commit()
    seed_database()
    db.commit()

def seed_database():
    db = get_db()
    cur = db.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()['count']
    if count > 0:
        return
    
    departments = [
        ('dept-1', 'Центральный аппарат', None),
        ('dept-2', 'Юридический отдел', None),
        ('dept-3', 'Организационный отдел', None),
        ('dept-4', 'Информационный отдел', None),
        ('dept-5', 'Отдел регионального развития', None),
    ]
    
    for d in departments:
        cur.execute("INSERT INTO departments (id, name, head_id) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING", d)
    
    users_data = [
        ('u-admin', 'Администратор Системы', 'admin@ldpr.ru', 'admin', 'admin123', 'admin', None),
        ('u-sec', 'Главный Секретарь', 'sec@ldpr.ru', 'secretary', 'sec123', 'secretary', None),
        ('u-head-central', 'Руководитель ЦА', 'headca@ldpr.ru', 'head_central', 'head123', 'head_central', 'dept-1'),
        ('u-head-dept', 'Начальник Юридического Отдела', 'headlaw@ldpr.ru', 'head_department', 'head123', 'head_department', 'dept-2'),
        ('u-ast', 'Помощник Депутата', 'ast@ldpr.ru', 'assistant', 'ast123', 'assistant', None),
        ('u-exec', 'Рядовой Исполнитель', 'exec@ldpr.ru', 'executor', 'exec123', 'executor', 'dept-2'),
        ('u-exec2', 'Специалист ИТ', 'it@ldpr.ru', 'executor2', 'exec123', 'executor', 'dept-4'),
    ]
    
    for uid, full_name, email, username, plain_pwd, role, dept_id in users_data:
        hashed = generate_password_hash(plain_pwd)
        cur.execute(
            """INSERT INTO users (uid, full_name, email, username, password, role, department_id) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (uid) DO UPDATE SET password = EXCLUDED.password, role = EXCLUDED.role""",
            (uid, full_name, email, username, hashed, role, dept_id)
        )
    
    db.commit()
    cur.execute("UPDATE departments SET head_id = 'u-head-central' WHERE id = 'dept-1'")
    cur.execute("UPDATE departments SET head_id = 'u-head-dept' WHERE id = 'dept-2'")
    db.commit()

# ============================================================
# МОДЕЛИ
# ============================================================

class UserModel:
    @staticmethod
    def get_by_id(uid):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE uid = %s", (uid,))
        return cur.fetchone()
    
    @staticmethod
    def get_by_username(username):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cur.fetchone()
    
    @staticmethod
    def get_all():
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users ORDER BY created_at DESC")
        return cur.fetchall()
    
    @staticmethod
    def create(uid, full_name, email, username, password, role='executor', department_id=None):
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO users (uid, full_name, email, username, password, role, department_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (uid, full_name, email, username, password, role, department_id)
            )
            db.commit()
            return True, None
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def update(uid, **kwargs):
        db = get_db()
        cur = db.cursor()
        allowed = ['full_name', 'email', 'username', 'role', 'department_id']
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if updates:
            set_clause = ', '.join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [uid]
            cur.execute(f"UPDATE users SET {set_clause} WHERE uid = %s", values)
            db.commit()
    
    @staticmethod
    def delete(uid):
        db = get_db()
        cur = db.cursor()
        cur.execute("DELETE FROM users WHERE uid = %s", (uid,))
        db.commit()
    
    @staticmethod
    def get_by_department(department_id):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE department_id = %s", (department_id,))
        return cur.fetchall()

class DepartmentModel:
    @staticmethod
    def get_all():
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT d.*, u.full_name as head_name FROM departments d LEFT JOIN users u ON d.head_id = u.uid ORDER BY d.name")
        return cur.fetchall()
    
    @staticmethod
    def get_by_id(dept_id):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT d.*, u.full_name as head_name FROM departments d LEFT JOIN users u ON d.head_id = u.uid WHERE d.id = %s", (dept_id,))
        return cur.fetchone()
    
    @staticmethod
    def create(dept_id, name):
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO departments (id, name) VALUES (%s, %s)", (dept_id, name))
            db.commit()
            return True
        except:
            return False
    
    @staticmethod
    def delete(dept_id):
        db = get_db()
        cur = db.cursor()
        cur.execute("DELETE FROM departments WHERE id = %s", (dept_id,))
        db.commit()

class OrderModel:
    STATUSES = ['Черновик', 'На утверждении', 'Утверждено', 'В отделе', 'Назначен исполнитель',
                 'В работе', 'Готово к проверке', 'Подтверждено', 'На доработке', 'Закрыто', 'Отклонено']
    PRIORITIES = ['Низкий', 'Нормальный', 'Высокий', 'Срочный']
    
    @staticmethod
    def get_all():
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
        return cur.fetchall()
    
    @staticmethod
    def get_by_id(order_id):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
        if order and order.get('result'):
            try:
                order['result'] = json.loads(order['result'])
            except:
                pass
        return order
    
    @staticmethod
    def get_by_department(dept_id):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM orders WHERE assigned_department_id = %s ORDER BY created_at DESC", (dept_id,))
        return cur.fetchall()
    
    @staticmethod
    def create(order_id, title, content, priority, status, created_by, creator_name, deadline=None, assigned_department_id=None):
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO orders (id, title, content, priority, status, created_by, creator_name, deadline, assigned_department_id, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (order_id, title, content, priority, status, created_by, creator_name, deadline, assigned_department_id)
        )
        db.commit()
    
    @staticmethod
    def update(order_id, **kwargs):
        db = get_db()
        cur = db.cursor()
        if 'result' in kwargs and kwargs['result']:
            kwargs['result'] = json.dumps(kwargs['result'], ensure_ascii=False)
        
        allowed = ['title', 'content', 'priority', 'status', 'assigned_department_id',
                    'assigned_executor_id', 'deadline', 'result']
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if updates:
            set_clause = ', '.join(f"{k} = %s" for k in updates) + ', updated_at = CURRENT_TIMESTAMP'
            values = list(updates.values()) + [order_id]
            cur.execute(f"UPDATE orders SET {set_clause} WHERE id = %s", values)
            db.commit()
    
    @staticmethod
    def get_by_user(uid, role, department_id=None):
        db = get_db()
        cur = db.cursor()
        if role == 'admin':
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
        elif role == 'assistant':
            cur.execute("SELECT * FROM orders WHERE created_by = %s ORDER BY created_at DESC", (uid,))
        elif role == 'head_department' and department_id:
            cur.execute("SELECT * FROM orders WHERE assigned_department_id = %s ORDER BY created_at DESC", (department_id,))
        elif role == 'executor':
            cur.execute("SELECT * FROM orders WHERE assigned_executor_id = %s ORDER BY created_at DESC", (uid,))
        elif role == 'secretary':
            cur.execute("SELECT * FROM orders WHERE status IN ('Утверждено','В отделе','Назначен исполнитель','В работе','Готово к проверке','Подтверждено','На доработке','Закрыто') ORDER BY created_at DESC")
        else:
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
        return cur.fetchall()
    
    @staticmethod
    def get_stats(uid=None, role=None, department_id=None):
        orders = OrderModel.get_by_user(uid, role, department_id) if uid else OrderModel.get_all()
        return {
            'total': len(orders),
            'pending': sum(1 for o in orders if o['status'] == 'На утверждении'),
            'approved': sum(1 for o in orders if o['status'] == 'Утверждено'),
            'in_work': sum(1 for o in orders if o['status'] == 'В работе'),
        }

class OrderHistoryModel:
    @staticmethod
    def get_by_order(order_id):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM order_history WHERE order_id = %s ORDER BY created_at DESC", (order_id,))
        return cur.fetchall()
    
    @staticmethod
    def add(order_id, action, user_name, user_role, details=None):
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO order_history (order_id, action, user_name, user_role, details) VALUES (%s, %s, %s, %s, %s)",
            (order_id, action, user_name, user_role, details)
        )
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
# ШАБЛОНЫ - ВАШ ОРИГИНАЛЬНЫЙ ДИЗАЙН
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
        :root { --ldpr-blue: #003399; --ldpr-gold: #FFD700; }
        body { background: #f4f6f9; font-family: 'Segoe UI', sans-serif; }
        .navbar { background: linear-gradient(135deg, #003399, #001a4d); }
        .navbar-brand { font-weight: 900; letter-spacing: -1px; }
        .sidebar { background: white; min-height: calc(100vh - 56px); box-shadow: 2px 0 10px rgba(0,0,0,0.05); }
        .sidebar .nav-link { color: #555; border-radius: 10px; margin: 3px 8px; padding: 10px 16px; font-weight: 500; }
        .sidebar .nav-link:hover { background: #eef; color: #003399; }
        .sidebar .nav-link.active { background: #003399; color: #fff !important; }
        .card { border: none; border-radius: 18px; box-shadow: 0 2px 16px rgba(0,0,0,0.05); }
        .stat-card { border-left: 5px solid #003399; }
        .badge-status { font-size: 0.75rem; font-weight: 600; padding: 6px 14px; border-radius: 20px; }
        .btn-primary { background: #003399; border: none; }
        .btn-primary:hover { background: #002266; }
        .btn-gold { background: #FFD700; color: #000; font-weight: 700; }
        .table th { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #888; }
    </style>
</head>
<body>
    {% if current_user %}
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/"><i class="bi bi-building"></i> ЭДО ЛДПР</a>
            <div class="d-flex align-items-center gap-3">
                <span class="text-light">{{ current_user.full_name }}</span>
                <a href="/logout" class="btn btn-outline-light btn-sm"><i class="bi bi-box-arrow-right"></i> Выход</a>
            </div>
        </div>
    </nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar py-3">
                <div class="text-center mb-4">
                    <div class="bg-primary text-white rounded-circle d-inline-flex align-items-center justify-content-center" style="width:64px;height:64px;font-size:1.5rem;font-weight:700;">{{ current_user.full_name[0] }}</div>
                    <p class="mt-2 mb-0 fw-bold">{{ current_user.full_name }}</p>
                    <small class="text-muted">{{ current_user.role }}</small>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link {{ 'active' if request.path == '/' }}" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a>
                    <a class="nav-link {{ 'active' if '/orders' in request.path }}" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>
                    {% if current_user.role in ['head_department', 'admin'] %}
                    <a class="nav-link {{ 'active' if request.path == '/department' }}" href="/department"><i class="bi bi-people me-2"></i>Отдел</a>
                    {% endif %}
                    {% if current_user.role == 'admin' %}
                    <a class="nav-link {{ 'active' if request.path == '/admin' }}" href="/admin"><i class="bi bi-gear me-2"></i>Админ</a>
                    {% endif %}
                </nav>
            </div>
            <div class="col-md-10 p-4">
                {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                {% for cat, msg in messages %}
                <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
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

# ВАШ ОРИГИНАЛЬНЫЙ ДИЗАЙН ЛОГИНА С КАРТИНКОЙ ФОНА
LOGIN_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход - ЭДО ЛДПР</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        .login-page {
            background-image: url('https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Flag_of_Russia.svg/1200px-Flag_of_Russia.svg.png');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            position: relative;
        }
        .login-page::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 51, 153, 0.85);
            z-index: 1;
        }
        .login-card {
            background: white;
            border-radius: 20px;
            padding: 40px 50px;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            position: relative;
            z-index: 2;
        }
        .login-logo {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            margin-bottom: 10px;
        }
        .login-logo-line {
            height: 2px;
            width: 60px;
            background: #003399;
        }
        .login-logo-text {
            color: #003399;
            font-size: 2rem;
            font-weight: 900;
            letter-spacing: 2px;
        }
        .login-subtitle {
            color: #666;
            text-align: center;
            font-size: 0.7rem;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 30px;
        }
        .login-label {
            color: #003399;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
            display: block;
        }
        .login-input {
            border: 2px solid #003399;
            border-radius: 8px;
            padding: 12px 15px;
            width: 100%;
            font-size: 1rem;
            outline: none;
            transition: all 0.3s;
        }
        .login-input:focus {
            box-shadow: 0 0 15px rgba(0,51,153,0.3);
            border-color: #003399;
        }
        .login-btn {
            background: linear-gradient(180deg, #003399 0%, #001a4d 100%);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 700;
            font-size: 1.1rem;
            padding: 12px;
            width: 100%;
            text-transform: uppercase;
            letter-spacing: 2px;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 10px;
        }
        .login-btn:hover {
            background: linear-gradient(180deg, #0044cc 0%, #002266 100%);
            transform: translateY(-2px);
        }
        .login-alert {
            background: rgba(220, 53, 69, 0.1);
            border: 1px solid #dc3545;
            color: #dc3545;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.85rem;
            text-align: center;
        }
        .input-icon-wrapper {
            position: relative;
        }
        .input-icon {
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: #003399;
            opacity: 0.7;
            font-size: 1.1rem;
        }
        .login-input.with-icon {
            padding-left: 45px;
        }
        .test-accounts {
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
        }
        .test-accounts small {
            color: #999;
            font-size: 0.7rem;
        }
        .test-accounts strong {
            color: #003399;
            font-size: 0.7rem;
        }
    </style>
</head>
<body>
    <div class="login-page">
        <div class="login-card">
            <div class="login-logo">
                <div class="login-logo-line"></div>
                <div class="login-logo-text">ЛДПР</div>
                <div class="login-logo-line"></div>
            </div>
            <div class="login-subtitle">
                Либерально-демократическая<br>партия России
            </div>
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            {% for cat, msg in messages %}
            <div class="login-alert">{{ msg }}</div>
            {% endfor %}
            {% endif %}
            {% endwith %}
            <form method="POST">
                <div class="mb-3">
                    <label class="login-label">Логин</label>
                    <div class="input-icon-wrapper">
                        <i class="bi bi-person input-icon"></i>
                        <input type="text" name="username" class="login-input with-icon" placeholder="Введите логин" required>
                    </div>
                </div>
                <div class="mb-4">
                    <label class="login-label">Пароль</label>
                    <div class="input-icon-wrapper">
                        <i class="bi bi-lock input-icon"></i>
                        <input type="password" name="password" class="login-input with-icon" placeholder="Введите пароль" required>
                    </div>
                </div>
                <button type="submit" class="login-btn">Войти в систему</button>
            </form>
            <div class="test-accounts">
                <small>Тестовые учетные записи:</small><br>
                <small><strong>admin</strong> / admin123 - Администратор</small><br>
                <small><strong>secretary</strong> / sec123 - Секретарь</small><br>
                <small><strong>executor</strong> / exec123 - Исполнитель</small>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''

# ВАШ ОРИГИНАЛЬНЫЙ ДАШБОРД
DASHBOARD_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Рабочий стол - ЭДО ЛДПР{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</h2>
<div class="row mb-4">
    <div class="col-md-3 mb-3"><div class="card stat-card p-3"><small class="text-muted text-uppercase fw-bold" style="font-size:0.65rem;">Мои распоряжения</small><h2 class="fw-bold mb-0">{{ stats.total }}</h2></div></div>
    <div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#f59e0b;"><small class="text-muted text-uppercase fw-bold" style="font-size:0.65rem;">На утверждении</small><h2 class="fw-bold mb-0">{{ stats.pending }}</h2></div></div>
    <div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#10b981;"><small class="text-muted text-uppercase fw-bold" style="font-size:0.65rem;">Утверждено</small><h2 class="fw-bold mb-0">{{ stats.approved }}</h2></div></div>
    <div class="col-md-3 mb-3"><div class="card stat-card p-3" style="border-left-color:#6366f1;"><small class="text-muted text-uppercase fw-bold" style="font-size:0.65rem;">В работе</small><h2 class="fw-bold mb-0">{{ stats.in_work }}</h2></div></div>
</div>
<div class="card p-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h5 class="fw-bold mb-0">Последние распоряжения</h5>
        <a href="/orders" class="btn btn-primary btn-sm">Все распоряжения</a>
    </div>
    {% if orders %}
    <div class="table-responsive">
        <table class="table table-hover">
            <thead><tr><th>Документ</th><th>Статус</th><th>Приоритет</th><th>Создан</th></tr></thead>
            <tbody>
                {% for o in orders %}
                <tr style="cursor:pointer" onclick="location.href='/orders/{{ o.id }}'">
                    <td><strong>{{ o.title }}</strong><br><small class="text-muted">#{{ o.id[:8] }}</small></td>
                    <td><span class="badge badge-status {% if o.status in ['Утверждено','Закрыто'] %}bg-success{% elif o.status == 'Отклонено' %}bg-danger{% elif o.status == 'На утверждении' %}bg-warning text-dark{% else %}bg-primary{% endif %}">{{ o.status }}</span></td>
                    <td><span class="fw-bold {% if o.priority == 'Срочный' %}text-danger{% elif o.priority == 'Высокий' %}text-warning{% else %}text-primary{% endif %}">{{ o.priority }}</span></td>
                    <td><small class="text-muted">{{ o.created_at[:10] if o.created_at else '' }}</small></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <p class="text-muted text-center py-4">Нет распоряжений</p>
    {% endif %}
</div>
{% endblock %}'''

# ОСТАЛЬНЫЕ ШАБЛОНЫ (ORDERS_TEMPLATE, ORDER_DETAILS_TEMPLATE, DEPARTMENT_TEMPLATE, ADMIN_TEMPLATE)
# Они такие же как в вашем оригинальном коде - я добавлю их в следующем сообщении из-за лимита символов

# ШАБЛОН СПИСКА РАСПОРЯЖЕНИЙ
ORDERS_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Реестр распоряжений - ЭДО ЛДПР{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-file-text me-2"></i>Реестр распоряжений</h2>

<div class="card p-3 mb-4">
    <form method="GET" class="row g-3">
        <div class="col-md-4">
            <div class="input-group">
                <span class="input-group-text"><i class="bi bi-search"></i></span>
                <input type="text" name="search" class="form-control" placeholder="Поиск..." value="{{ request.args.get('search','') }}">
            </div>
        </div>
        <div class="col-md-3">
            <select name="status" class="form-select">
                <option value="Все">Все статусы</option>
                {% for s in statuses %}
                <option value="{{ s }}" {% if request.args.get('status') == s %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="col-md-3">
            <select name="priority" class="form-select">
                <option value="Все">Все приоритеты</option>
                {% for p in priorities %}
                <option value="{{ p }}" {% if request.args.get('priority') == p %}selected{% endif %}>{{ p }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="col-md-2">
            <button type="submit" class="btn btn-primary w-100">Фильтр</button>
        </div>
    </form>
</div>

{% if current_user.role in ['assistant'] %}
<button class="btn btn-primary mb-3" data-bs-toggle="modal" data-bs-target="#createModal">
    <i class="bi bi-plus-lg"></i> Создать распоряжение
</button>
{% endif %}

<div class="card">
    <div class="table-responsive">
        <table class="table table-hover mb-0">
            <thead>
                <tr>
                    <th>Документ</th>
                    <th>Приоритет</th>
                    <th>Статус</th>
                    <th>Срок</th>
                    <th>Автор</th>
                    <th>Создан</th>
                </tr>
            </thead>
            <tbody>
                {% for o in orders %}
                <tr style="cursor:pointer" onclick="location.href='/orders/{{ o.id }}'">
                    <td>
                        <strong>{{ o.title }}</strong><br>
                        <small class="text-muted">#{{ o.id[:8] }}</small>
                    </d>
                    <td>
                        <span class="fw-bold {% if o.priority == 'Срочный' %}text-danger{% elif o.priority == 'Высокий' %}text-warning{% else %}text-primary{% endif %}">
                            {{ o.priority }}
                        </span>
                    </d>
                    <td>
                        <span class="badge badge-status 
                            {% if o.status in ['Утверждено','Закрыто'] %}bg-success
                            {% elif o.status == 'Отклонено' %}bg-danger
                            {% elif o.status == 'На утверждении' %}bg-warning text-dark
                            {% else %}bg-primary{% endif %}">
                            {{ o.status }}
                        </span>
                    </d>
                    <td><small>{{ o.deadline or '-' }}</small></d>
                    <td><small>{{ o.creator_name }}</small></d>
                    <td><small class="text-muted">{{ o.created_at[:16] if o.created_at else '' }}</small></d>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- Модальное окно создания распоряжения -->
<div class="modal fade" id="createModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title fw-bold"><i class="bi bi-file-earmark-plus"></i> Новое распоряжение</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST" action="/orders/create">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label fw-bold small text-uppercase text-muted">Заголовок</label>
                        <input type="text" name="title" class="form-control" placeholder="Введите заголовок распоряжения" required>
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label fw-bold small text-uppercase text-muted">Приоритет</label>
                            <select name="priority" class="form-select">
                                <option>Низкий</option>
                                <option selected>Нормальный</option>
                                <option>Высокий</option>
                                <option>Срочный</option>
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label fw-bold small text-uppercase text-muted">Срок исполнения</label>
                            <input type="date" name="deadline" class="form-control">
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label fw-bold small text-uppercase text-muted">Содержание</label>
                        <textarea name="content" class="form-control" rows="6" placeholder="Введите текст распоряжения..." required></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" name="is_draft" value="1" class="btn btn-outline-primary">
                        <i class="bi bi-save"></i> Сохранить черновик
                    </button>
                    <button type="submit" class="btn btn-primary">
                        <i class="bi bi-send"></i> Отправить на утверждение
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}'''

# ШАБЛОН ДЕТАЛЕЙ РАСПОРЯЖЕНИЯ
ORDER_DETAILS_TEMPLATE = '''{% extends "base.html" %}
{% block title %}{{ order.title }} - ЭДО ЛДПР{% endblock %}
{% block content %}
<a href="/orders" class="btn btn-outline-secondary btn-sm mb-3">
    <i class="bi bi-arrow-left"></i> Назад к списку
</a>

<div class="row">
    <div class="col-md-8">
        <div class="card p-4 mb-4">
            <div class="d-flex justify-content-between mb-3">
                <div>
                    <span class="badge bg-primary mb-2">Р №{{ order.id[:8] }}</span>
                    <h3 class="fw-bold">{{ order.title }}</h3>
                </div>
                <span class="badge badge-status 
                    {% if order.status in ['Утверждено','Закрыто'] %}bg-success
                    {% elif order.status == 'Отклонено' %}bg-danger
                    {% elif order.status == 'На утверждении' %}bg-warning text-dark
                    {% else %}bg-primary{% endif %}">
                    {{ order.status }}
                </span>
            </div>
            
            <div class="row mb-3 py-3 border-top border-bottom">
                <div class="col-md-3">
                    <small class="text-muted text-uppercase fw-bold d-block" style="font-size:0.6rem;">Автор</small>
                    <strong>{{ order.creator_name }}</strong>
                </div>
                <div class="col-md-3">
                    <small class="text-muted text-uppercase fw-bold d-block" style="font-size:0.6rem;">Срок</small>
                    <strong>{{ order.deadline or 'Не указан' }}</strong>
                </div>
                <div class="col-md-3">
                    <small class="text-muted text-uppercase fw-bold d-block" style="font-size:0.6rem;">Приоритет</small>
                    <strong>{{ order.priority }}</strong>
                </div>
                <div class="col-md-3">
                    <small class="text-muted text-uppercase fw-bold d-block" style="font-size:0.6rem;">Создано</small>
                    <strong>{{ order.created_at[:10] if order.created_at else '' }}</strong>
                </div>
            </div>
            
            <h6 class="fw-bold text-uppercase text-muted small mb-3">Текст распоряжения</h6>
            <div class="bg-light p-3 rounded" style="white-space:pre-wrap;">{{ order.content }}</div>
            
            {% if order.result %}
            <div class="mt-4 p-3 bg-success bg-opacity-10 rounded border border-success border-opacity-25">
                <h6 class="text-success fw-bold"><i class="bi bi-check-circle-fill"></i> Результат выполнения</h6>
                <div style="white-space:pre-wrap;">{{ order.result.content }}</div>
                <small class="text-muted mt-2 d-block">
                    Подано: {{ order.result.submittedAt[:16] if order.result.submittedAt else '' }}
                </small>
            </div>
            {% endif %}
        </div>
        
        <div class="card p-4">
            <h5 class="fw-bold mb-3"><i class="bi bi-clock-history me-2"></i>История изменений</h5>
            {% for item in history %}
            <div class="d-flex mb-3">
                <div class="me-3">
                    <div class="bg-primary rounded-circle d-inline-flex align-items-center justify-content-center text-white" style="width:28px;height:28px;font-size:0.7rem;">
                        <i class="bi bi-arrow-repeat"></i>
                    </div>
                </div>
                <div>
                    <strong>{{ item.action }}</strong><br>
                    <small class="text-muted">{{ item.details or '' }}</small><br>
                    <small class="text-muted" style="font-size:0.7rem;">{{ item.user_name }} - {{ item.created_at }}</small>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="col-md-4">
        <div class="card p-4">
            <h5 class="fw-bold mb-3"><i class="bi bi-gear"></i> Действия</h5>
            
            {% if current_user.role == 'head_central' and order.status == 'На утверждении' %}
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="Утверждено">
                <button class="btn btn-success w-100 mb-2">
                    <i class="bi bi-check-circle"></i> Утвердить распоряжение
                </button>
            </form>
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="Отклонено">
                <input type="text" name="comment" class="form-control form-control-sm mb-2" placeholder="Причина отклонения">
                <button class="btn btn-danger w-100">
                    <i class="bi bi-x-circle"></i> Отклонить
                </button>
            </form>
            {% endif %}
            
            {% if current_user.role == 'secretary' and order.status == 'Утверждено' %}
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="В отделе">
                <select name="department_id" class="form-select form-select-sm mb-2" required>
                    <option value="">Выберите отдел...</option>
                    {% for d in departments %}
                    <option value="{{ d.id }}">{{ d.name }}</option>
                    {% endfor %}
                </select>
                <button class="btn btn-primary w-100">
                    <i class="bi bi-building"></i> Назначить отдел
                </button>
            </form>
            {% endif %}
            
            {% if current_user.role == 'head_department' and order.status == 'В отделе' %}
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="Назначен исполнитель">
                <select name="executor_id" class="form-select form-select-sm mb-2" required>
                    <option value="">Выберите исполнителя...</option>
                    {% for u in dept_users %}
                    <option value="{{ u.uid }}">{{ u.full_name }}</option>
                    {% endfor %}
                </select>
                <button class="btn btn-primary w-100">
                    <i class="bi bi-person-check"></i> Назначить исполнителя
                </button>
            </form>
            {% endif %}
            
            {% if current_user.role == 'executor' and order.status == 'Назначен исполнитель' and order.assigned_executor_id == current_user.uid %}
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="В работе">
                <button class="btn btn-primary w-100">
                    <i class="bi bi-play-circle"></i> Взять в работу
                </button>
            </form>
            {% endif %}
            
            {% if current_user.role == 'executor' and order.status == 'В работе' and order.assigned_executor_id == current_user.uid %}
            <form method="POST" action="/orders/{{ order.id }}/submit">
                <textarea name="result_content" class="form-control form-control-sm mb-2" rows="4" placeholder="Опишите результат выполнения..." required></textarea>
                <button class="btn btn-success w-100">
                    <i class="bi bi-check-circle"></i> Сдать работу на проверку
                </button>
            </form>
            {% endif %}
            
            {% if current_user.role == 'head_department' and order.status == 'Готово к проверке' %}
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="Подтверждено">
                <button class="btn btn-success w-100 mb-2">
                    <i class="bi bi-check-circle"></i> Подтвердить выполнение
                </button>
            </form>
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="На доработке">
                <input type="text" name="comment" class="form-control form-control-sm mb-2" placeholder="Причина доработки">
                <button class="btn btn-warning w-100">
                    <i class="bi bi-arrow-counterclockwise"></i> Отправить на доработку
                </button>
            </form>
            {% endif %}
            
            {% if current_user.role == 'head_central' and order.status == 'Подтверждено' %}
            <form method="POST" action="/orders/{{ order.id }}/status">
                <input type="hidden" name="status" value="Закрыто">
                <button class="btn btn-success w-100">
                    <i class="bi bi-check-circle"></i> Закрыть распоряжение
                </button>
            </form>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}'''

# ШАБЛОН ОТДЕЛА
DEPARTMENT_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Мой отдел - ЭДО ЛДПР{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-building me-2"></i>Мой отдел</h2>

{% if department %}
<div class="card p-4 mb-4">
    <h4 class="fw-bold">{{ department.name }}</h4>
    <p class="text-muted">
        <i class="bi bi-person-badge"></i> Руководитель: {{ department.head_name or 'Не назначен' }}
    </p>
</div>

<div class="row">
    <div class="col-md-6">
        <div class="card p-4">
            <h5 class="fw-bold mb-3"><i class="bi bi-people"></i> Сотрудники отдела</h5>
            {% if users %}
            <div class="list-group">
                {% for u in users %}
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>{{ u.full_name }}</strong><br>
                        <small class="text-muted">{{ u.role }}</small>
                    </div>
                    <span class="badge bg-primary">{{ u.email }}</span>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p class="text-muted text-center py-4">Нет сотрудников в отделе</p>
            {% endif %}
        </div>
    </div>
    <div class="col-md-6">
        <div class="card p-4">
            <h5 class="fw-bold mb-3"><i class="bi bi-file-text"></i> Распоряжения отдела</h5>
            {% if orders %}
            <div class="list-group">
                {% for o in orders %}
                <a href="/orders/{{ o.id }}" class="list-group-item list-group-item-action">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>{{ o.title }}</strong><br>
                            <small class="text-muted">{{ o.created_at[:10] if o.created_at else '' }}</small>
                        </div>
                        <span class="badge badge-status 
                            {% if o.status in ['Утверждено','Закрыто'] %}bg-success
                            {% elif o.status == 'Отклонено' %}bg-danger
                            {% elif o.status == 'На утверждении' %}bg-warning text-dark
                            {% else %}bg-primary{% endif %}">
                            {{ o.status }}
                        </span>
                    </div>
                </a>
                {% endfor %}
            </div>
            {% else %}
            <p class="text-muted text-center py-4">Нет распоряжений для отдела</p>
            {% endif %}
        </div>
    </div>
</div>
{% else %}
<div class="alert alert-warning">
    <i class="bi bi-exclamation-triangle"></i> Отдел не найден
</div>
{% endif %}
{% endblock %}'''

# ШАБЛОН АДМИНКИ
ADMIN_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Администрирование - ЭДО ЛДПР{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-shield-lock me-2"></i>Администрирование</h2>

<!-- Пользователи -->
<div class="card p-4 mb-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h5 class="fw-bold mb-0"><i class="bi bi-people"></i> Пользователи системы</h5>
        <div>
            <span class="badge bg-primary me-2">{{ users|length }} пользователей</span>
            <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addUserModal">
                <i class="bi bi-plus-lg"></i> Добавить пользователя
            </button>
        </div>
    </div>
    <div class="table-responsive">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>ФИО</th>
                    <th>Логин</th>
                    <th>Роль</th>
                    <th>Email</th>
                    <th>Отдел</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for u in users %}
                <tr>
                    <td><strong>{{ u.full_name }}</strong></d>
                    <td>{{ u.username }}</d>
                    <td><span class="badge bg-secondary">{{ u.role }}</span></d>
                    <td>{{ u.email }}</d>
                    <td>
                        {% for d in departments %}
                            {% if d.id == u.department_id %}{{ d.name }}{% endif %}
                        {% endfor %}
                    </d>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#editUser{{ u.uid }}">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <form method="POST" action="/admin/users/{{ u.uid }}/delete" class="d-inline" onsubmit="return confirm('Удалить пользователя {{ u.full_name }}?')">
                            <button type="submit" class="btn btn-sm btn-outline-danger">
                                <i class="bi bi-trash"></i>
                            </button>
                        </form>
                    </d>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- Отделы -->
<div class="card p-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h5 class="fw-bold mb-0"><i class="bi bi-building"></i> Отделы</h5>
        <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addDeptModal">
            <i class="bi bi-plus-lg"></i> Добавить отдел
        </button>
    </div>
    <div class="table-responsive">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>Название</th>
                    <th>Руководитель</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for d in departments %}
                <tr>
                    <td><strong>{{ d.name }}</strong></d>
                    <td>{{ d.head_name or 'Не назначен' }}</d>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#setHead{{ d.id }}">
                            <i class="bi bi-person-badge"></i> Назначить руководителя
                        </button>
                        <form method="POST" action="/admin/departments/{{ d.id }}/delete" class="d-inline" onsubmit="return confirm('Удалить отдел {{ d.name }}?')">
                            <button type="submit" class="btn btn-sm btn-outline-danger">
                                <i class="bi bi-trash"></i>
                            </button>
                        </form>
                    </d>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- Модальное окно добавления пользователя -->
<div class="modal fade" id="addUserModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title"><i class="bi bi-person-plus"></i> Добавить пользователя</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST" action="/admin/users/create">
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">ФИО</label>
                            <input type="text" name="full_name" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Логин</label>
                            <input type="text" name="username" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" name="email" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Пароль</label>
                            <input type="password" name="password" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Роль</label>
                            <select name="role" class="form-select">
                                <option value="admin">Администратор</option>
                                <option value="secretary">Секретарь</option>
                                <option value="head_central">Руководитель ЦА</option>
                                <option value="head_department">Начальник отдела</option>
                                <option value="assistant">Помощник</option>
                                <option value="executor" selected>Исполнитель</option>
                            </select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Отдел</label>
                            <select name="department_id" class="form-select">
                                <option value="">Без отдела</option>
                                {% for d in departments %}
                                <option value="{{ d.id }}">{{ d.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" class="btn btn-primary">Создать пользователя</button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Модальные окна редактирования пользователей -->
{% for u in users %}
<div class="modal fade" id="editUser{{ u.uid }}" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Редактировать: {{ u.full_name }}</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST" action="/admin/users/{{ u.uid }}/edit">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">ФИО</label>
                        <input type="text" name="full_name" class="form-control" value="{{ u.full_name }}" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Email</label>
                        <input type="email" name="email" class="form-control" value="{{ u.email }}" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Роль</label>
                        <select name="role" class="form-select">
                            <option value="admin" {% if u.role == 'admin' %}selected{% endif %}>Администратор</option>
                            <option value="secretary" {% if u.role == 'secretary' %}selected{% endif %}>Секретарь</option>
                            <option value="head_central" {% if u.role == 'head_central' %}selected{% endif %}>Руководитель ЦА</option>
                            <option value="head_department" {% if u.role == 'head_department' %}selected{% endif %}>Начальник отдела</option>
                            <option value="assistant" {% if u.role == 'assistant' %}selected{% endif %}>Помощник</option>
                            <option value="executor" {% if u.role == 'executor' %}selected{% endif %}>Исполнитель</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Отдел</label>
                        <select name="department_id" class="form-select">
                            <option value="" {% if not u.department_id %}selected{% endif %}>Без отдела</option>
                            {% for d in departments %}
                            <option value="{{ d.id }}" {% if d.id == u.department_id %}selected{% endif %}>{{ d.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" class="btn btn-primary">Сохранить изменения</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endfor %}

<!-- Модальное окно добавления отдела -->
<div class="modal fade" id="addDeptModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Добавить отдел</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST" action="/department/create">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Название отдела</label>
                        <input type="text" name="name" class="form-control" required>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" class="btn btn-primary">Создать отдел</button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Модальные окна назначения руководителя -->
{% for d in departments %}
<div class="modal fade" id="setHead{{ d.id }}" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Назначить руководителя: {{ d.name }}</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST" action="/admin/departments/{{ d.id }}/set_head">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Выберите руководителя</label>
                        <select name="head_id" class="form-select" required>
                            <option value="">-- Выберите --</option>
                            {% for u in users %}
                            {% if u.role == 'head_department' %}
                            <option value="{{ u.uid }}">{{ u.full_name }}</option>
                            {% endif %}
                            {% endfor %}
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" class="btn btn-primary">Назначить руководителя</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endfor %}

{% endblock %}'''

# ============================================================
# МАРШРУТЫ FLASK
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
            session.permanent = True
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
    order_id = 'order-' + str(uuid.uuid4())[:8]
    is_draft = request.form.get('is_draft') == '1'
    status = 'Черновик' if is_draft else 'На утверждении'
    user = UserModel.get_by_id(session['user_id'])
    OrderModel.create(order_id, title, content, request.form.get('priority', 'Нормальный'), status, session['user_id'], user['full_name'], request.form.get('deadline') or None)
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
    dept_users = UserModel.get_by_department(order.get('assigned_department_id')) if order.get('assigned_department_id') else []
    return render_template_string(ORDER_DETAILS_TEMPLATE, order=order, history=history, departments=departments, dept_users=dept_users)

@app_flask.route('/department')
@login_required
def department():
    if session.get('user_role') == 'admin':
        departments = DepartmentModel.get_all()
        return render_template_string('''
        {% extends "base.html" %}
        {% block title %}Управление отделами{% endblock %}
        {% block content %}
        <h2>Управление отделами</h2>
        <div class="card p-3">
            <button class="btn btn-primary mb-3" data-bs-toggle="modal" data-bs-target="#addDeptModal">+ Добавить отдел</button>
            <table class="table">
                <thead><tr><th>Название</th><th>Руководитель</th><th>Действия</th></tr></thead>
                <tbody>
                    {% for d in departments %}
                    <tr>
                        <td>{{ d.name }}</td>
                        <td>{{ d.head_name or 'Не назначен' }}</td>
                        <td><a href="/department/{{ d.id }}" class="btn btn-sm btn-outline-primary">Просмотр</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="modal fade" id="addDeptModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
            <div class="modal-header"><h5 class="modal-title">Добавить отдел</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <form method="POST" action="/department/create"><div class="modal-body"><input type="text" name="name" class="form-control" placeholder="Название" required></div>
            <div class="modal-footer"><button type="submit" class="btn btn-primary">Создать</button></div></form>
        </div></div></div>
        {% endblock %}
        ''', departments=departments)
    
    dept_id = session.get('department_id')
    if not dept_id:
        flash('У вас нет назначенного отдела', 'warning')
        return redirect(url_for('dashboard'))
    department_data = DepartmentModel.get_by_id(dept_id)
    if not department_data:
        flash('Отдел не найден', 'danger')
        return redirect(url_for('dashboard'))
    users = UserModel.get_by_department(dept_id)
    orders = OrderModel.get_by_department(dept_id)
    return render_template_string(DEPARTMENT_TEMPLATE, department=department_data, users=users, orders=orders)

@app_flask.route('/department/<dept_id>')
@login_required
@role_required('admin')
def department_details(dept_id):
    dept = DepartmentModel.get_by_id(dept_id)
    if not dept:
        flash('Отдел не найден', 'danger')
        return redirect(url_for('department'))
    users = UserModel.get_by_department(dept_id)
    orders = OrderModel.get_by_department(dept_id)
    return render_template_string(DEPARTMENT_TEMPLATE, department=dept, users=users, orders=orders)

@app_flask.route('/department/create', methods=['POST'])
@login_required
@role_required('admin')
def create_department():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Введите название отдела', 'danger')
        return redirect(url_for('department'))
    dept_id = 'dept-' + str(uuid.uuid4())[:8]
    if DepartmentModel.create(dept_id, name):
        flash('Отдел создан', 'success')
    else:
        flash('Ошибка при создании отдела', 'danger')
    return redirect(url_for('department'))

@app_flask.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    users = UserModel.get_all()
    departments = DepartmentModel.get_all()
    return render_template_string(ADMIN_TEMPLATE, users=users, departments=departments)

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
    
    allowed = False
    details = f'Статус: {new_status}'
    extra = {}
    
    if current_role == 'head_central' and current_status == 'На утверждении' and new_status in ['Утверждено', 'Отклонено']:
        allowed = True
    elif current_role == 'secretary' and current_status == 'Утверждено':
        dept_id = request.form.get('department_id')
        if dept_id:
            allowed = True
            new_status = 'В отделе'
            extra['assigned_department_id'] = dept_id
            dept = DepartmentModel.get_by_id(dept_id)
            details = f'Назначен отдел: {dept["name"] if dept else dept_id}'
    elif current_role == 'head_department' and current_status == 'В отделе':
        exec_id = request.form.get('executor_id')
        if exec_id:
            allowed = True
            new_status = 'Назначен исполнитель'
            extra['assigned_executor_id'] = exec_id
            executor = UserModel.get_by_id(exec_id)
            details = f'Назначен исполнитель: {executor["full_name"] if executor else exec_id}'
    elif current_role == 'executor' and current_status == 'Назначен исполнитель' and order.get('assigned_executor_id') == session['user_id']:
        allowed = True
        new_status = 'В работе'
    elif current_role == 'head_department' and current_status == 'Готово к проверке' and new_status == 'Подтверждено':
        allowed = True
        details = 'Работа подтверждена начальником отдела'
    elif current_role == 'head_central' and current_status == 'Подтверждено' and new_status == 'Закрыто':
        allowed = True
        details = 'Распоряжение закрыто руководителем ЦА'
    elif current_role in ['head_department', 'head_central'] and current_status in ['Готово к проверке', 'Подтверждено'] and new_status == 'На доработке':
        allowed = True
        details = f'Отправлено на доработку: {comment}' if comment else 'Отправлено на доработку'
    
    if allowed:
        OrderModel.update(order_id, status=new_status, **extra)
        OrderHistoryModel.add(order_id, 'Изменение статуса', user['full_name'], current_role, details)
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
    
    current_role = session['user_role']
    current_status = order['status']
    result_content = request.form.get('result_content', '').strip()
    
    if current_role != 'executor' or current_status != 'В работе' or order.get('assigned_executor_id') != session['user_id']:
        flash('Действие не разрешено', 'danger')
        return redirect(url_for('order_details', order_id=order_id))
    
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
    OrderHistoryModel.add(order_id, 'Сдача работы', user['full_name'], current_role, 'Работа сдана на проверку')
    flash('Работа сдана на проверку', 'success')
    return redirect(url_for('order_details', order_id=order_id))

# Администрирование пользователей
@app_flask.route('/admin/users/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_create_user():
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'executor')
    department_id = request.form.get('department_id') or None
    
    if not full_name or not email or not username or not password:
        flash('Все поля обязательны для заполнения', 'danger')
        return redirect(url_for('admin_panel'))
    
    uid = 'u-' + str(uuid.uuid4())[:8]
    hashed_pwd = generate_password_hash(password)
    success, error = UserModel.create(uid, full_name, email, username, hashed_pwd, role, department_id)
    flash('Пользователь успешно создан' if success else error, 'success' if success else 'danger')
    return redirect(url_for('admin_panel'))

@app_flask.route('/admin/users/<uid>/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_user(uid):
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    role = request.form.get('role')
    department_id = request.form.get('department_id') or None
    
    updates = {}
    if full_name:
        updates['full_name'] = full_name
    if email:
        updates['email'] = email
    if role:
        updates['role'] = role
    updates['department_id'] = department_id
    
    UserModel.update(uid, **updates)
    flash('Пользователь обновлен', 'success')
    return redirect(url_for('admin_panel'))

@app_flask.route('/admin/users/<uid>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_user(uid):
    if uid == session['user_id']:
        flash('Нельзя удалить самого себя', 'danger')
        return redirect(url_for('admin_panel'))
    UserModel.delete(uid)
    flash('Пользователь удален', 'success')
    return redirect(url_for('admin_panel'))

@app_flask.route('/admin/departments/<dept_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_department(dept_id):
    DepartmentModel.delete(dept_id)
    flash('Отдел удален', 'success')
    return redirect(url_for('admin_panel'))

@app_flask.route('/admin/departments/<dept_id>/set_head', methods=['POST'])
@login_required
@role_required('admin')
def admin_set_department_head(dept_id):
    head_id = request.form.get('head_id')
    if not head_id:
        flash('Выберите руководителя', 'danger')
        return redirect(url_for('admin_panel'))
    
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE departments SET head_id = %s WHERE id = %s", (head_id, dept_id))
    cur.execute("UPDATE users SET department_id = %s WHERE uid = %s", (dept_id, head_id))
    db.commit()
    flash('Руководитель назначен', 'success')
    return redirect(url_for('admin_panel'))

# ============================================================
# ЗАПУСК
# ============================================================

with app_flask.app_context():
    init_db()
    print("Database initialized successfully!")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port, debug=False)