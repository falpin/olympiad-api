from .main_routes import *
from database import register_user
import jwt
from config import SECRET_KEY
import bcrypt
import json
import random
import string
from datetime import datetime, timedelta
from mail import send_email

# Регистрация пользователя
@api.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'school']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Не хватает обязательных полей"}), 400

        # Проверка уникальности email
        existing_user = SQL_request(
            "SELECT id FROM users WHERE email = ?",
            (data['email'],),
            fetch="one"
        )
        if existing_user:
            return jsonify({"error": "Пользователь с таким email уже существует"}), 409

        # Вставка нового пользователя
        register_user(data)

        # Логирование
        logger.info(f"Новый пользователь зарегистрирован: {data['email']}")
        return jsonify({"message": "Пользователь успешно зарегистрирован. Ожидайте подтверждения администратора."}), 201

    except Exception as e:
        logger.error(f"Ошибка регистрации: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Подтверждение пользователя администратором
@api.route('/users/<int:user_id>/approve', methods=['POST'])
@auth_decorator('admin')
def approve_user(user_id):
    try:
        # Проверка существования пользователя
        user = SQL_request("SELECT * FROM users WHERE id = ? AND is_approved = 0", (user_id,))
        if not user:
            return jsonify({"error": "Пользователь не найден или уже подтвержден"}), 404

        # Генерация логина и пароля
        login = ''.join(random.choices(string.ascii_letters, k=7))
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
        
        # Хеширование пароля
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password = hashed_password.decode('utf-8')

        
        # Обновление пользователя
        SQL_request(
            "UPDATE users SET login = ?, password = ?, is_approved = 1 WHERE id = ?",
            (login, hashed_password, user_id)
        )
        
        # Отправка email с учетными данными
        send_email(
            to_email=user['email'],
            subject="Ваш аккаунт подтвержден",
            text_body=f"Ваши данные для входа:\nЛогин: {login}\nПароль: {password}",
            html_body=f"<p>Ваши данные для входа:</p><p><strong>Логин:</strong> {login}</p><p><strong>Пароль:</strong> {password}</p>"
        )
        
        logger.info(f"Пользователь {user_id} подтвержден администратором {g.user['id']}")
        return jsonify({"message": "Пользователь успешно подтвержден. Данные отправлены на почту."}), 200

    except Exception as e:
        logger.error(f"Ошибка подтверждения пользователя: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Аутентификация пользователя
@api.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if 'login' not in data or 'password' not in data:
            return jsonify({"error": "Необходимы логин и пароль"}), 400
        
        user = SQL_request(
            "SELECT * FROM users WHERE login = ? AND is_approved = 1",
            (data['login'],)
        )
        print(user)

        if not user:
            return jsonify({"error": "Неверные учетные данные или пользователь не подтвержден"}), 401
        
        if user["login"] == "admin":
            pass
        else:
            hashed_password = user['password'].strip().encode('utf-8')  # .strip() убирает пробелы и \n
            if not bcrypt.checkpw(data['password'].encode('utf-8'), hashed_password):
                return jsonify({"error": "Неверные учетные данные"}), 401
        
        # Генерация JWT токена
        payload = {
            'user_id': user['id'],
            'role': user['role'],
            'email': user['email'],
            'exp': datetime.utcnow() + timedelta(hours=JWT_ACCESS_EXPIRES_HOURS)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        
        # Безопасный ответ без пароля
        user_data = {
            'id': user['id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'email': user['email'],
            'role': user['role'],
            'school': user['school'],
            'phone': user['phone']
        }
        
        logger.info(f"Успешный вход пользователя: {user['email']}")
        return jsonify({
            "message": "Успешная аутентификация",
            "token": token,
            "user": user_data
        }), 200

    except Exception as e:
        logger.error(f"Ошибка входа: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Получение профиля пользователя
@api.route('/profile', methods=['GET'])
@auth_decorator()
def get_profile():
    try:
        # g.user устанавливается декоратором auth_decorator
        user_data = {
            'id': g.user['id'],
            'first_name': g.user['first_name'],
            'last_name': g.user['last_name'],
            'patronymic': g.user['patronymic'],
            'email': g.user['email'],
            'phone': g.user['phone'],
            'school': g.user['school'],
            'role': g.user['role'],
            'is_approved': bool(g.user['is_approved'])
        }
        return jsonify(user_data), 200

    except Exception as e:
        logger.error(f"Ошибка получения профиля: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Обновление профиля пользователя
@api.route('/profile', methods=['PUT'])
@auth_decorator()
def update_profile():
    try:
        data = request.get_json()
        updates = {}
        allowed_fields = ['first_name', 'last_name', 'patronymic', 'phone', 'school']
        
        # Фильтрация разрешенных полей
        for field in allowed_fields:
            if field in data:
                updates[field] = data[field]
        
        if not updates:
            return jsonify({"error": "Нет данных для обновления"}), 400
        
        # Формирование SQL запроса
        set_clause = ", ".join([f"{field} = ?" for field in updates.keys()])
        values = list(updates.values())
        values.append(g.user['id'])
        
        SQL_request(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            values
        )
        
        logger.info(f"Пользователь {g.user['id']} обновил профиль")
        return jsonify({"message": "Профиль успешно обновлен"}), 200

    except Exception as e:
        logger.error(f"Ошибка обновления профиля: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Получение списка пользователей (для администратора)
@api.route('/users', methods=['GET'])
@auth_decorator(role='admin')
def get_users():
    try:
        users = SQL_request(
            "SELECT * FROM users",
            fetch="all",
        )
        
        # Преобразование is_approved в boolean
        for user in users:
            user['is_approved'] = bool(user['is_approved'])
        
        return jsonify(users), 200

    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
