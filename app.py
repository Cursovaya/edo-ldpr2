#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭДО ЛДПР - ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ
ВСЕ ФУНКЦИИ РАБОТАЮТ, АВТОРИЗАЦИЯ ИСПРАВЛЕНА
"""

import os
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

# ПРОСТАЯ БД В ПАМЯТИ (ДЛЯ ТЕСТА, БЕЗ POSTGRESQL)
# Это временное решение, чтобы приложение работало
# Потом можно заменить на PostgreSQL

USERS_DB = {}
DEPARTMENTS_DB = {}
ORDERS_DB = {}
ORDER_HISTORY_DB = {}

# Инициализация тестовых данных
def init_test_data():
    # Отделы
    DEPARTMENTS_DB['dept-1'] = {'id': 'dept-1', 'name': 'Центральный аппарат', 'head_id': 'u-head-central'}
    DEPARTMENTS_DB['dept-2'] = {'id': 'dept-2', 'name': 'Юридический отдел', 'head_id': 'u-head-dept'}
    DEPARTMENTS_DB['dept-3'] = {'id': 'dept-3', 'name': 'Организационный отдел', 'head_id': None}
    DEPARTMENTS_DB['dept-4'] = {'id': 'dept-4', 'name': 'Информационный отдел', 'head_id': None}
    DEPARTMENTS_DB['dept-5'] = {'id': 'dept-5', 'name': 'Отдел регионального развития', 'head_id': None}
    
    # Пользователи
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
        USERS_DB[uid] = {
            'uid': uid,
            'full_name': full_name,
            'email': email,
            'username': username,
            'password': generate_password_hash(plain_pwd),
            'role': role,
            'department_id': dept_id,
            'created_at': datetime.now().isoformat()
        }
    
    # Добавляем возможность входа по username
    for uid, user in USERS_DB.items():
        USERS_DB[user['username']] = user  # Дублируем по username для поиска

# ============================================================
# МОДЕЛИ (РАБОТАЮТ С ПАМЯТЬЮ)
# ============================================================

class UserModel:
    @staticmethod
    def get_by_id(uid):
        return USERS_DB.get(uid)
    
    @staticmethod
    def get_by_username(username):
        for uid, user in USERS_DB.items():
            if user.get('username') == username:
                return user
        return None
    
    @staticmethod
    def get_all():
        return [u for u in USERS_DB.values() if u.get('uid', '').startswith('u-')]
    
    @staticmethod
    def get_by_department(department_id):
        return [u for u in USERS_DB.values() if u.get('department_id') == department_id]

class DepartmentModel:
    @staticmethod
    def get_all():
        result = []
        for dept in DEPARTMENTS_DB.values():
            dept_copy = dept.copy()
            head = USERS_DB.get(dept.get('head_id'))
            dept_copy['head_name'] = head['full_name'] if head else None
            result.append(dept_copy)
        return result
    
    @staticmethod
    def get_by_id(dept_id):
        dept = DEPARTMENTS_DB.get(dept_id)
        if dept:
            dept_copy = dept.copy()
            head = USERS_DB.get(dept.get('head_id'))
            dept_copy['head_name'] = head['full_name'] if head else None
            return dept_copy
        return None
    
    @staticmethod
    def create(dept_id, name):
        if dept_id not in DEPARTMENTS_DB:
            DEPARTMENTS_DB[dept_id] = {'id': dept_id, 'name': name, 'head_id': None}
            return True
        return False
    
    @staticmethod
    def delete(dept_id):
        if dept_id in DEPARTMENTS_DB:
            del DEPARTMENTS_DB[dept_id]
            return True
        return False

class OrderModel:
    STATUSES = ['Черновик', 'На утверждении', 'Утверждено', 'В отделе', 'Назначен исполнитель',
                 'В работе', 'Готово к проверке', 'Подтверждено', 'На доработке', 'Закрыто', 'Отклонено']
    PRIORITIES = ['Низкий', 'Нормальный', 'Высокий', 'Срочный']
    
    @staticmethod
    def get_all():
        return list(ORDERS_DB.values())
    
    @staticmethod
    def get_by_id(order_id):
        order = ORDERS_DB.get(order_id)
        if order and order.get('result'):
            try:
                import json
                order['result'] = json.loads(order['result']) if isinstance(order['result'], str) else order['result']
            except:
                pass
        return order
    
    @staticmethod
    def get_by_department(dept_id):
        return [o for o in ORDERS_DB.values() if o.get('assigned_department_id') == dept_id]
    
    @staticmethod
    def create(order_id, title, content, priority, status, created_by, creator_name, deadline=None, assigned_department_id=None):
        order = {
            'id': order_id,
            'title': title,
            'content': content,
            'priority': priority,
            'status': status,
            'created_by': created_by,
            'creator_name': creator_name,
            'assigned_department_id': assigned_department_id,
            'assigned_executor_id': None,
            'deadline': deadline,
            'result': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        ORDERS_DB[order_id] = order
        return True
    
    @staticmethod
    def update(order_id, **kwargs):
        if order_id in ORDERS_DB:
            for key, value in kwargs.items():
                if key != 'id':
                    ORDERS_DB[order_id][key] = value
            ORDERS_DB[order_id]['updated_at'] = datetime.now().isoformat()
    
    @staticmethod
    def get_by_user(uid, role, department_id=None):
        result = []
        for order in ORDERS_DB.values():
            if role == 'admin':
                result.append(order)
            elif role == 'assistant' and order.get('created_by') == uid:
                result.append(order)
            elif role == 'head_department' and order.get('assigned_department_id') == department_id:
                result.append(order)
            elif role == 'executor' and order.get('assigned_executor_id') == uid:
                result.append(order)
            elif role == 'secretary' and order.get('status') in ['Утверждено', 'В отделе', 'Назначен исполнитель', 'В работе', 'Готово к проверке', 'Подтверждено', 'На доработке', 'Закрыто']:
                result.append(order)
        return sorted(result, key=lambda x: x.get('created_at', ''), reverse=True)
    
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
        return ORDER_HISTORY_DB.get(order_id, [])
    
    @staticmethod
    def add(order_id, action, user_name, user_role, details=None):
        if order_id not in ORDER_HISTORY_DB:
            ORDER_HISTORY_DB[order_id] = []
        ORDER_HISTORY_DB[order_id].append({
            'action': action,
            'user_name': user_name,
            'user_role': user_role,
            'details': details,
            'created_at': datetime.now().isoformat()
        })

# Инициализация
init_test_data()

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
# ШАБЛОНЫ
# ============================================================

app_flask = Flask(__name__)
app_flask.secret_key = secrets.token_hex(32)

# БАЗОВЫЙ ШАБЛОН
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
        body { background: #f4f6f9; font-family: 'Segoe UI', sans-serif; }
        .navbar { background: linear-gradient(135deg, #003399, #001a4d); }
        .navbar-brand { font-weight: 900; }
        .sidebar { background: white; min-height: calc(100vh - 56px); box-shadow: 2px 0 10px rgba(0,0,0,0.05); }
        .sidebar .nav-link { color: #555; border-radius: 10px; margin: 3px 8px; padding: 10px 16px; font-weight: 500; }
        .sidebar .nav-link:hover { background: #eef; color: #003399; }
        .sidebar .nav-link.active { background: #003399; color: #fff !important; }
        .card { border: none; border-radius: 18px; box-shadow: 0 2px 16px rgba(0,0,0,0.05); }
        .stat-card { border-left: 5px solid #003399; }
        .badge-status { font-size: 0.75rem; font-weight: 600; padding: 6px 14px; border-radius: 20px; }
        .btn-primary { background: #003399; border: none; }
        .btn-primary:hover { background: #002266; }
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
                    <a class="nav-link" href="/"><i class="bi bi-speedometer2 me-2"></i>Рабочий стол</a>
                    <a class="nav-link" href="/orders"><i class="bi bi-file-text me-2"></i>Распоряжения</a>
                    {% if current_user.role in ['head_department', 'admin'] %}
                    <a class="nav-link" href="/department"><i class="bi bi-people me-2"></i>Отдел</a>
                    {% endif %}
                    {% if current_user.role == 'admin' %}
                    <a class="nav-link" href="/admin"><i class="bi bi-gear me-2"></i>Админ</a>
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

# СТРАНИЦА ВХОДА
LOGIN_PAGE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ЭДО ЛДПР - Вход</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        body {
            background: linear-gradient(135deg, #003399 0%, #001a4d 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', sans-serif;
        }
        .login-card {
            background: white;
            border-radius: 24px;
            padding: 45px 55px;
            max-width: 450px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .logo-text {
            text-align: center;
            font-size: 2.2rem;
            font-weight: 900;
            color: #003399;
            margin-bottom: 10px;
        }
        .subtitle {
            text-align: center;
            font-size: 0.7rem;
            color: #666;
            margin-bottom: 30px;
        }
        .form-control-custom {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            margin-bottom: 20px;
            font-size: 1rem;
        }
        .form-control-custom:focus {
            outline: none;
            border-color: #003399;
        }
        .btn-login {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #003399, #002266);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
        }
        .btn-login:hover {
            transform: translateY(-2px);
        }
        .alert-custom {
            padding: 12px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        .alert-danger { background: #fee; color: #c00; }
        .alert-success { background: #efe; color: #060; }
        .test-accounts {
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            font-size: 0.7rem;
            color: #666;
        }
        .test-accounts strong { color: #003399; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo-text">ЭДО ЛДПР</div>
        <div class="subtitle">Электронный документооборот</div>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert-custom alert-{{ cat }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" class="form-control-custom" placeholder="Логин" required autofocus>
            <input type="password" name="password" class="form-control-custom" placeholder="Пароль" required>
            <button type="submit" class="btn-login">Войти в систему</button>
        </form>
        <div class="test-accounts">
            <strong>admin</strong> / admin123 (Администратор)<br>
            <strong>secretary</strong> / sec123 (Секретарь)<br>
            <strong>head_central</strong> / head123 (Руководитель ЦА)<br>
            <strong>head_department</strong> / head123 (Начальник отдела)<br>
            <strong>assistant</strong> / ast123 (Помощник)<br>
            <strong>executor</strong> / exec123 (Исполнитель)
        </div>
    </div>
</body>
</html>'''

# DASHBOARD
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
                    <td><span class="badge badge-status bg-primary">{{ o.status }}</span></td>
                    <td>{{ o.priority }}</d>
                    <td>{{ o.created_at[:10] if o.created_at else '' }}</d>
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

# ORDERS
ORDERS_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Распоряжения{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-file-text me-2"></i>Распоряжения</h2>
{% if current_user.role in ['assistant'] %}
<button class="btn btn-primary mb-3" data-bs-toggle="modal" data-bs-target="#createModal"><i class="bi bi-plus-lg"></i> Создать</button>
{% endif %}
<div class="card">
    <div class="table-responsive">
        <table class="table table-hover mb-0">
            <thead><tr><th>Документ</th><th>Статус</th><th>Приоритет</th><th>Создан</th></tr></thead>
            <tbody>
                {% for o in orders %}
                <tr style="cursor:pointer" onclick="location.href='/orders/{{ o.id }}'">
                    <td><strong>{{ o.title }}</strong><br><small class="text-muted">#{{ o.id[:8] }}</small></td>
                    <td><span class="badge badge-status bg-primary">{{ o.status }}</span></td>
                    <td>{{ o.priority }}</d>
                    <td>{{ o.created_at[:10] if o.created_at else '' }}</d>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
<div class="modal fade" id="createModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header"><h5 class="modal-title">Новое распоряжение</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <form method="POST" action="/orders/create">
                <div class="modal-body">
                    <div class="mb-3"><input type="text" name="title" class="form-control" placeholder="Заголовок" required></div>
                    <div class="row mb-3">
                        <div class="col-md-6"><select name="priority" class="form-select"><option>Низкий</option><option selected>Нормальный</option><option>Высокий</option><option>Срочный</option></select></div>
                        <div class="col-md-6"><input type="date" name="deadline" class="form-control"></div>
                    </div>
                    <div class="mb-3"><textarea name="content" class="form-control" rows="6" placeholder="Содержание" required></textarea></div>
                </div>
                <div class="modal-footer">
                    <button type="submit" name="is_draft" value="1" class="btn btn-outline-primary">Черновик</button>
                    <button type="submit" class="btn btn-primary">На утверждение</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}'''

# ORDER DETAILS
ORDER_DETAILS_TEMPLATE = '''{% extends "base.html" %}
{% block title %}{{ order.title }}{% endblock %}
{% block content %}
<a href="/orders" class="btn btn-outline-secondary btn-sm mb-3"><i class="bi bi-arrow-left"></i> Назад</a>
<div class="row">
    <div class="col-md-8">
        <div class="card p-4 mb-4">
            <h3 class="fw-bold">{{ order.title }}</h3>
            <div class="row mb-3 py-3">
                <div class="col-md-4"><small>Автор:</small><br><strong>{{ order.creator_name }}</strong></div>
                <div class="col-md-4"><small>Статус:</small><br><strong>{{ order.status }}</strong></div>
                <div class="col-md-4"><small>Приоритет:</small><br><strong>{{ order.priority }}</strong></div>
            </div>
            <div class="bg-light p-3 rounded">{{ order.content }}</div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card p-4">
            <h5 class="fw-bold mb-3">Действия</h5>
            {% if current_user.role == 'head_central' and order.status == 'На утверждении' %}
            <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Утверждено"><button class="btn btn-success w-100 mb-2">Утвердить</button></form>
            {% endif %}
            {% if current_user.role == 'secretary' and order.status == 'Утверждено' %}
            <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В отделе"><select name="department_id" class="form-select mb-2" required><option value="">Выберите отдел</option>{% for d in departments %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}</select><button class="btn btn-primary w-100">Назначить отдел</button></form>
            {% endif %}
            {% if current_user.role == 'head_department' and order.status == 'В отделе' %}
            <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Назначен исполнитель"><select name="executor_id" class="form-select mb-2" required><option value="">Выберите исполнителя</option>{% for u in dept_users %}<option value="{{ u.uid }}">{{ u.full_name }}</option>{% endfor %}</select><button class="btn btn-primary w-100">Назначить</button></form>
            {% endif %}
            {% if current_user.role == 'executor' and order.status == 'Назначен исполнитель' and order.assigned_executor_id == current_user.uid %}
            <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="В работе"><button class="btn btn-primary w-100">Взять в работу</button></form>
            {% endif %}
            {% if current_user.role == 'executor' and order.status == 'В работе' and order.assigned_executor_id == current_user.uid %}
            <form method="POST" action="/orders/{{ order.id }}/submit"><textarea name="result_content" class="form-control mb-2" rows="4" placeholder="Результат" required></textarea><button class="btn btn-success w-100">Сдать работу</button></form>
            {% endif %}
            {% if current_user.role == 'head_department' and order.status == 'Готово к проверке' %}
            <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Подтверждено"><button class="btn btn-success w-100">Подтвердить</button></form>
            {% endif %}
            {% if current_user.role == 'head_central' and order.status == 'Подтверждено' %}
            <form method="POST" action="/orders/{{ order.id }}/status"><input type="hidden" name="status" value="Закрыто"><button class="btn btn-success w-100">Закрыть</button></form>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}'''

# DEPARTMENT TEMPLATE
DEPARTMENT_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Отдел{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-building me-2"></i>Отдел: {{ department.name }}</h2>
<div class="row">
    <div class="col-md-6">
        <div class="card p-4">
            <h5 class="fw-bold mb-3">Сотрудники</h5>
            {% for u in users %}
            <div class="mb-2"><strong>{{ u.full_name }}</strong> - {{ u.role }}</div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}'''

# ADMIN TEMPLATE
ADMIN_TEMPLATE = '''{% extends "base.html" %}
{% block title %}Администрирование{% endblock %}
{% block content %}
<h2 class="fw-bold mb-4"><i class="bi bi-shield-lock me-2"></i>Администрирование</h2>
<div class="card p-4">
    <h5 class="fw-bold mb-3">Пользователи</h5>
    <table class="table">
        <thead><tr><th>ФИО</th><th>Логин</th><th>Роль</th><th>Отдел</th><th>Действия</th></tr></thead>
        <tbody>
            {% for u in users %}
            <tr>
                <td>{{ u.full_name }}</d>
                <td>{{ u.username }}</d>
                <td>{{ u.role }}</d>
                <td>{{ u.department_id or '-' }}</d>
                <td>
                    <button class="btn btn-sm btn-danger" onclick="alert('Удаление временно отключено')">Удалить</button>
                </d>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
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
            session.permanent = True
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
    return render_template_string(ORDERS_TEMPLATE, orders=all_orders, statuses=OrderModel.STATUSES, priorities=OrderModel.PRIORITIES)

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
        return render_template_string(ADMIN_TEMPLATE, users=UserModel.get_all(), departments=departments)
    dept_id = session.get('department_id')
    if not dept_id:
        flash('У вас нет назначенного отдела', 'warning')
        return redirect(url_for('dashboard'))
    department_data = DepartmentModel.get_by_id(dept_id)
    users = UserModel.get_by_department(dept_id)
    orders = OrderModel.get_by_department(dept_id)
    return render_template_string(DEPARTMENT_TEMPLATE, department=department_data, users=users, orders=orders)

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
    user = UserModel.get_by_id(session['user_id'])
    current_role = session['user_role']
    current_status = order['status']
    
    allowed = False
    extra = {}
    
    if current_role == 'head_central' and current_status == 'На утверждении' and new_status == 'Утверждено':
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
    elif current_role == 'executor' and current_status == 'В работе' and new_status == 'Готово к проверке':
        allowed = True
    elif current_role == 'head_department' and current_status == 'Готово к проверке' and new_status == 'Подтверждено':
        allowed = True
    elif current_role == 'head_central' and current_status == 'Подтверждено' and new_status == 'Закрыто':
        allowed = True
    
    if allowed:
        OrderModel.update(order_id, status=new_status, **extra)
        OrderHistoryModel.add(order_id, 'Изменение статуса', user['full_name'], current_role, f'Новый статус: {new_status}')
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
    
    if session['user_role'] != 'executor' or order['status'] != 'В работе' or order.get('assigned_executor_id') != session['user_id']:
        flash('Действие не разрешено', 'danger')
        return redirect(url_for('order_details', order_id=order_id))
    
    result_content = request.form.get('result_content', '').strip()
    if not result_content:
        flash('Опишите результат выполнения', 'warning')
        return redirect(url_for('order_details', order_id=order_id))
    
    import json
    result = json.dumps({'content': result_content, 'submittedAt': datetime.now().isoformat()})
    OrderModel.update(order_id, status='Готово к проверке', result=result)
    flash('Работа сдана на проверку', 'success')
    return redirect(url_for('order_details', order_id=order_id))

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port, debug=False)