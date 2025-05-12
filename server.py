from flask import Flask, request, jsonify
import sqlite3
from flask_bcrypt import Bcrypt
import secrets
from datetime import datetime
import re
from flask_mail import Mail, Message

app = Flask(__name__)
bcrypt = Bcrypt(app)

# Настройка Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@example.com'
app.config['MAIL_PASSWORD'] = 'your-email-password'
mail = Mail(app)

# Логирование
try:
    import logging
    logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
except:
    print("Не удалось подключить логи")

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'teacher', 'student')) DEFAULT 'student',
            token TEXT UNIQUE
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            description TEXT,
            duration INTEGER, -- Длительность курса в часах
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS olympics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_current_user(token):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE token = ?', (token,)).fetchone()
    conn.close()
    return user

def token_required(f):
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        user = get_current_user(token)
        if not user:
            return jsonify({'message': 'Invalid token'}), 401
        return f(user=user, *args, **kwargs)
    decorated.__name__ = f.__name__  # Устанавливаем имя функции для корректного идентифицирования
    return decorated

def validate_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

def validate_date(date_str):
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

@app.route('/api/register', methods=['POST'], endpoint='register')
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')

    if not all([email, password, name]):
        return jsonify({'message': 'All fields are required'}), 400
    if not validate_email(email):
        return jsonify({'message': 'Invalid email format'}), 400

    conn = get_db_connection()
    existing_user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if existing_user:
        return jsonify({'message': 'Email already exists'}), 409

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    token = secrets.token_urlsafe(16)
    conn.execute('''
        INSERT INTO users (name, email, password, token)
        VALUES (?, ?, ?, ?)
    ''', (name, email, hashed_password, token))
    conn.commit()
    conn.close()
    logging.info(f"User {name} registered with email {email}")
    return jsonify({'message': 'User created', 'token': token}), 201

@app.route('/api/login', methods=['POST'], endpoint='login')
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({'message': 'Email and password are required'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    if not user or not bcrypt.check_password_hash(user['password'], password):
        return jsonify({'message': 'Invalid email or password'}), 401

    logging.info(f"User {user['name']} logged in")
    return jsonify({'token': user['token']}), 200

@app.route('/api/courses', methods=['POST'], endpoint='create_course')
@token_required
def create_course(user):
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'message': 'Access denied'}), 403

    data = request.json
    title = data.get('title')
    description = data.get('description')
    duration = data.get('duration')

    if not title:
        return jsonify({'message': 'Title is required'}), 400
    if not duration:
        return jsonify({'message': 'Duration is required'}), 400

    conn = get_db_connection()
    existing_course = conn.execute('SELECT * FROM courses WHERE title = ?', (title,)).fetchone()
    if existing_course:
        return jsonify({'message': 'Course title must be unique'}), 409

    conn.execute('''
        INSERT INTO courses (title, description, duration, created_by)
        VALUES (?, ?, ?, ?)
    ''', (title, description, duration, user['id']))
    conn.commit()
    conn.close()
    logging.info(f"Course {title} created by user {user['name']}")
    return jsonify({'message': 'Course created'}), 201

@app.route('/api/courses/<int:course_id>', methods=['PUT'], endpoint='update_course')
@token_required
def update_course(user, course_id):
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'message': 'Access denied'}), 403

    data = request.json
    title = data.get('title')
    description = data.get('description')
    duration = data.get('duration')

    conn = get_db_connection()
    course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if not course:
        return jsonify({'message': 'Course not found'}), 404

    if title and title != course['title']:
        existing_course = conn.execute('SELECT * FROM courses WHERE title = ?', (title,)).fetchone()
        if existing_course:
            return jsonify({'message': 'Course title must be unique'}), 409

    conn.execute('''
        UPDATE courses SET title = ?, description = ?, duration = ? WHERE id = ?
    ''', (title or course['title'], description or course['description'], duration or course['duration'], course_id))
    conn.commit()
    conn.close()
    logging.info(f"Course {course_id} updated by user {user['name']}")
    return jsonify({'message': 'Course updated'}), 200

@app.route('/api/courses/<int:course_id>', methods=['DELETE'], endpoint='delete_course')
@token_required
def delete_course(user, course_id):
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'message': 'Access denied'}), 403

    conn = get_db_connection()
    course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if not course:
        return jsonify({'message': 'Course not found'}), 404

    conn.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    conn.commit()
    conn.close()
    logging.info(f"Course {course_id} deleted by user {user['name']}")
    return jsonify({'message': 'Course deleted'}), 200

@app.route('/api/olympics', methods=['POST'], endpoint='create_olympic')
@token_required
def create_olympic(user):
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'message': 'Access denied'}), 403

    data = request.json
    title = data.get('title')
    description = data.get('description')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not all([title, start_date, end_date]):
        return jsonify({'message': 'Title, start_date and end_date are required'}), 400
    if not validate_date(start_date) or not validate_date(end_date):
        return jsonify({'message': 'Invalid date format (YYYY-MM-DD)'}), 400

    conn = get_db_connection()
    existing_olympic = conn.execute('SELECT * FROM olympics WHERE title = ?', (title,)).fetchone()
    if existing_olympic:
        return jsonify({'message': 'Olympic title must be unique'}), 409

    conn.execute('''
        INSERT INTO olympics (title, description, start_date, end_date, created_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, description, start_date, end_date, user['id']))
    conn.commit()
    conn.close()
    logging.info(f"Olympic {title} created by user {user['name']}")
    return jsonify({'message': 'Olympic created'}), 201

@app.route('/api/olympics/<int:olympic_id>', methods=['PUT'], endpoint='update_olympic')
@token_required
def update_olympic(user, olympic_id):
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'message': 'Access denied'}), 403

    data = request.json
    title = data.get('title')
    description = data.get('description')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    conn = get_db_connection()
    olympic = conn.execute('SELECT * FROM olympics WHERE id = ?', (olympic_id,)).fetchone()
    if not olympic:
        return jsonify({'message': 'Olympic not found'}), 404

    if title and title != olympic['title']:
        existing_olympic = conn.execute('SELECT * FROM olympics WHERE title = ?', (title,)).fetchone()
        if existing_olympic:
            return jsonify({'message': 'Olympic title must be unique'}), 409

    if start_date and not validate_date(start_date):
        return jsonify({'message': 'Invalid start_date format (YYYY-MM-DD)'}), 400
    if end_date and not validate_date(end_date):
        return jsonify({'message': 'Invalid end_date format (YYYY-MM-DD)'}), 400

    conn.execute('''
        UPDATE olympics SET title = ?, description = ?, start_date = ?, end_date = ? WHERE id = ?
    ''', (title or olympic['title'], description or olympic['description'], start_date or olympic['start_date'], end_date or olympic['end_date'], olympic_id))
    conn.commit()
    conn.close()
    logging.info(f"Olympic {olympic_id} updated by user {user['name']}")
    return jsonify({'message': 'Olympic updated'}), 200

@app.route('/api/olympics/<int:olympic_id>', methods=['DELETE'], endpoint='delete_olympic')
@token_required
def delete_olympic(user, olympic_id):
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'message': 'Access denied'}), 403

    conn = get_db_connection()
    olympic = conn.execute('SELECT * FROM olympics WHERE id = ?', (olympic_id,)).fetchone()
    if not olympic:
        return jsonify({'message': 'Olympic not found'}), 404

    conn.execute('DELETE FROM olympics WHERE id = ?', (olympic_id,))
    conn.commit()
    conn.close()
    logging.info(f"Olympic {olympic_id} deleted by user {user['name']}")
    return jsonify({'message': 'Olympic deleted'}), 200

@app.route('/api/olympics/<int:olympic_id>', methods=['GET'], endpoint='get_olympic')
def get_olympic(olympic_id):
    conn = get_db_connection()
    olympic = conn.execute('SELECT * FROM olympics WHERE id = ?', (olympic_id,)).fetchone()
    conn.close()
    if not olympic:
        return jsonify({'message': 'Olympic not found'}), 404
    return jsonify(dict(olympic)), 200

@app.route('/api/courses/<int:course_id>', methods=['GET'], endpoint='get_course')
def get_course(course_id):
    conn = get_db_connection()
    course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    conn.close()
    if not course:
        return jsonify({'message': 'Course not found'}), 404
    return jsonify(dict(course)), 200

@app.route('/api/olympics', methods=['GET'], endpoint='get_olympics')
def get_olympics():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    conn = get_db_connection()
    olympics = conn.execute('SELECT id, title, start_date, end_date FROM olympics LIMIT ? OFFSET ?', (per_page, (page - 1) * per_page)).fetchall()
    conn.close()
    return jsonify([dict(o) for o in olympics]), 200

@app.route('/api/courses', methods=['GET'], endpoint='get_courses')
def get_courses():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    conn = get_db_connection()
    courses = conn.execute('SELECT id, title, created_at FROM courses LIMIT ? OFFSET ?', (per_page, (page - 1) * per_page)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in courses]), 200

@app.route('/api/users/<int:user_id>/role', methods=['PUT'], endpoint='update_role')
@token_required
def update_role(user, user_id):
    if user['role'] != 'admin':
        return jsonify({'message': 'Access denied'}), 403

    data = request.json
    new_role = data.get('role')

    if not new_role or new_role not in ['admin', 'teacher', 'student']:
        return jsonify({'message': 'Invalid role'}), 400

    conn = get_db_connection()
    user_to_update = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user_to_update:
        return jsonify({'message': 'User not found'}), 404

    conn.execute('''
        UPDATE users SET role = ? WHERE id = ?
    ''', (new_role, user_id))
    conn.commit()
    conn.close()
    logging.info(f"User {user_id} role updated to {new_role} by admin {user['name']}")
    return jsonify({'message': 'Role updated'}), 200

@app.route('/api/users', methods=['GET'], endpoint='get_users')
@token_required
def get_users(user):
    if user['role'] != 'admin':
        return jsonify({'message': 'Access denied'}), 403

    conn = get_db_connection()
    users = conn.execute('SELECT id, name, email, role FROM users').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users]), 200

@app.route('/api/forgot-password', methods=['POST'], endpoint='forgot_password')
def forgot_password():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'message': 'Email is required'}), 400
    if not validate_email(email):
        return jsonify({'message': 'Invalid email format'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    reset_token = secrets.token_urlsafe(16)
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO password_resets (email, token)
        VALUES (?, ?)
    ''', (email, reset_token))
    conn.commit()
    conn.close()

    msg = Message('Password Reset Request', sender='your-email@example.com', recipients=[email])
    msg.body = f"To reset your password, visit the following link:\n\nhttp://localhost:5000/api/reset-password?token={reset_token}"
    mail.send(msg)

    logging.info(f"Password reset request sent to {email}")
    return jsonify({'message': 'Password reset email sent'}), 200

@app.route('/api/reset-password', methods=['POST'], endpoint='reset_password')
def reset_password():
    data = request.json
    token = data.get('token')
    new_password = data.get('new_password')

    if not all([token, new_password]):
        return jsonify({'message': 'Token and new_password are required'}), 400

    conn = get_db_connection()
    reset_record = conn.execute('SELECT * FROM password_resets WHERE token = ?', (token,)).fetchone()
    if not reset_record:
        return jsonify({'message': 'Invalid token'}), 401

    user = conn.execute('SELECT * FROM users WHERE email = ?', (reset_record['email'],)).fetchone()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user['id']))
    conn.execute('DELETE FROM password_resets WHERE token = ?', (token,))
    conn.commit()
    conn.close()

    logging.info(f"Password reset for user {user['name']}")
    return jsonify({'message': 'Password reset successful'}), 200

# app.run(debug=True)