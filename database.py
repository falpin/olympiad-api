import json
import sqlite3
from dotenv import load_dotenv
import os
import string
import random

load_dotenv()

DB_PATH = os.getenv("DB_PATH")

def SQL_request(query, params=(), fetch='one', jsonify_result=False):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)

            if fetch == 'all':
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                result = [
                    {
                        col: json.loads(row[i]) if isinstance(row[i], str) and row[i].startswith('{') else row[i]
                        for i, col in enumerate(columns)
                    }
                    for row in rows
                ]

            elif fetch == 'one':
                row = cursor.fetchone()
                if row:
                    columns = [desc[0] for desc in cursor.description]
                    result = {
                        col: json.loads(row[i]) if isinstance(row[i], str) and row[i].startswith('{') else row[i]
                        for i, col in enumerate(columns)
                    }
                else:
                    result = None
            else:
                conn.commit()
                result = None

        except sqlite3.Error as e:
            print(f"Ошибка SQL: {e}")
            raise

    if jsonify_result and result is not None:
        return json.dumps(result, ensure_ascii=False, indent=2)
    return result

def create_tables():
    # Пользователи
    SQL_request('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        patronymic TEXT,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        school TEXT NOT NULL,
        role TEXT CHECK(role IN ('student', 'teacher', 'admin')) DEFAULT 'student',
        login TEXT,
        password TEXT,
        is_approved BOOLEAN DEFAULT 0
    )''')
    
    # Изображения (для вопросов и новостей)
    SQL_request('''
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data BLOB NOT NULL,
        mime_type TEXT NOT NULL
    )''')
    
    # Тесты
    SQL_request('''
    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        creator_id INTEGER NOT NULL,
        grading_system TEXT NOT NULL,  -- JSON: {"A": 90, "B": 80, ...}
        is_open BOOLEAN DEFAULT 1,
        FOREIGN KEY (creator_id) REFERENCES users(id)
    )''')
    
    # Олимпиады
    SQL_request('''
    CREATE TABLE IF NOT EXISTS olympiads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        creator_id INTEGER NOT NULL,
        grading_system TEXT NOT NULL,  -- JSON
        start_time DATETIME NOT NULL,
        end_time DATETIME NOT NULL,
        duration INTEGER NOT NULL,  -- в минутах
        FOREIGN KEY (creator_id) REFERENCES users(id)
    )''')
    
    # Вопросы (общие для тестов и олимпиад)
    SQL_request('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        type TEXT CHECK(type IN ('single', 'multiple', 'text')) NOT NULL,
        points INTEGER NOT NULL,
        image_id INTEGER,
        FOREIGN KEY (image_id) REFERENCES images(id)
    )''')
    
    # Варианты ответов
    SQL_request('''
    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        is_correct BOOLEAN NOT NULL,
        FOREIGN KEY (question_id) REFERENCES questions(id)
    )''')
    
    # Связь тестов с вопросами
    SQL_request('''
    CREATE TABLE IF NOT EXISTS test_questions (
        test_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        PRIMARY KEY (test_id, question_id),
        FOREIGN KEY (test_id) REFERENCES tests(id),
        FOREIGN KEY (question_id) REFERENCES questions(id)
    )''')
    
    # Связь олимпиад с вопросами
    SQL_request('''
    CREATE TABLE IF NOT EXISTS olympiad_questions (
        olympiad_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        PRIMARY KEY (olympiad_id, question_id),
        FOREIGN KEY (olympiad_id) REFERENCES olympiads(id),
        FOREIGN KEY (question_id) REFERENCES questions(id)
    )''')
    
    # Результаты тестов
    SQL_request('''
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        test_id INTEGER NOT NULL,
        start_time DATETIME NOT NULL,
        end_time DATETIME NOT NULL,
        score INTEGER NOT NULL,
        total_score INTEGER NOT NULL,
        grade TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (test_id) REFERENCES tests(id)
    )''')
    
    # Результаты олимпиад
    SQL_request('''
    CREATE TABLE IF NOT EXISTS olympiad_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        olympiad_id INTEGER NOT NULL,
        start_time DATETIME NOT NULL,
        end_time DATETIME NOT NULL,
        score INTEGER DEFAULT 0,
        total_score INTEGER NOT NULL,
        grade TEXT,
        is_checked BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (olympiad_id) REFERENCES olympiads(id)
    )''')
    
    # Ответы пользователей
    SQL_request('''
    CREATE TABLE IF NOT EXISTS user_answers (
        result_id INTEGER NOT NULL,  -- ID из test_results или olympiad_results
        question_id INTEGER NOT NULL,
        answer_ids TEXT,  -- JSON-массив ID для выбора
        answer_text TEXT,  -- для текстовых ответов
        is_olympiad BOOLEAN NOT NULL,  -- 0=test, 1=olympiad
        PRIMARY KEY (result_id, question_id, is_olympiad)
    )''')
    
    # Новости
    SQL_request('''
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,  -- Markdown
        author_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_published BOOLEAN DEFAULT 0,
        image_id INTEGER,
        FOREIGN KEY (author_id) REFERENCES users(id),
        FOREIGN KEY (image_id) REFERENCES images(id)
    )''')
    
    # Избранное
    SQL_request('''
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Добавлен суррогатный ключ
        user_id INTEGER NOT NULL,
        test_id INTEGER,
        olympiad_id INTEGER,
        CHECK (test_id IS NOT NULL OR olympiad_id IS NOT NULL),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (test_id) REFERENCES tests(id),
        FOREIGN KEY (olympiad_id) REFERENCES olympiads(id)
    )''')
    
    # Добавляем уникальные индексы
    SQL_request('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_fav_user_test 
    ON favorites(user_id, test_id) 
    WHERE test_id IS NOT NULL
    ''')
    
    SQL_request('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_fav_user_olympiad 
    ON favorites(user_id, olympiad_id) 
    WHERE olympiad_id IS NOT NULL
    ''')

def approve_user(user_id):
    # Генерация логина и пароля
    login = ''.join(random.choices(string.ascii_letters, k=7))
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
    
    SQL_request(
        "UPDATE users SET login=?, password=?, is_approved=1 WHERE id=?",
        (login, password, user_id)
    )
    
    # Здесь должна быть отправка email с логином и паролем
    print(f"User {user_id} approved. Login: {login}, Password: {password}")

def register_user(data: dict):
    SQL_request('''
    INSERT INTO users (first_name, last_name, patronymic, email, phone, school)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        data['first_name'],
        data['last_name'],
        data.get('patronymic', ''),
        data['email'],
        data['phone'],
        data['school']
    ))

def save_image(image_data: bytes, mime_type: str) -> int:
    res = SQL_request(
        "INSERT INTO images (data, mime_type) VALUES (?, ?) RETURNING id",
        (image_data, mime_type),
        fetch=True
    )
    return res[0][0]

def create_test(title: str, description: str, creator_id: int, grading_system: dict):
    SQL_request(
        "INSERT INTO tests (title, description, creator_id, grading_system) VALUES (?, ?, ?, ?)",
        (title, description, creator_id, json.dumps(grading_system)))

# Инициализация базы данных
if __name__ == "__main__":
    create_tables()
    print("Database initialized successfully!")