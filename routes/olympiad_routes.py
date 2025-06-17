from .main_routes import *
from database import SQL_request
import json
from datetime import datetime

# Создание олимпиады

# Получение списка олимпиад
@api.route('/olympiads', methods=['GET'])
@auth_decorator()
def get_olympiads():
    try:
        # Для студентов: только доступные олимпиады
        # Для преподавателей: все олимпиады
        now = datetime.utcnow().isoformat()
        
        if g.user and g.user['role'] in ['teacher', 'admin']:
            olympiads = SQL_request(
                "SELECT * FROM olympiads",
                fetch="all"
            )
        else:
            olympiads = SQL_request(
                "SELECT * FROM olympiads WHERE start_time <= ? AND end_time >= ?",
                (now, now),
                fetch="all"
            )
        
        return jsonify(olympiads), 200

    except Exception as e:
        logger.error(f"Ошибка получения списка олимпиад: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@api.route('/olympiads/<int:olympiad_id>/questions', methods=['POST'])
@auth_decorator(role='teacher')
def add_question_to_olympiad(olympiad_id):
    try:
        # Проверяем, что тест существует и принадлежит текущему пользователю
        olympiad = SQL_request('SELECT creator_id FROM olympiads WHERE id = ?', (olympiad_id,), fetch="one")
        if not olympiad:
            return jsonify({"error": "Олимпиада не найден"}), 404
        
        if olympiad['creator_id'] != g.user['id'] and g.user['role'] != 'admin':
            return jsonify({"error": "Вы не можете изменять этот тест"}), 403
        
        data = request.form.to_dict()
        files = request.files
        
        # Валидация данных вопроса
        if not data.get('content') or not data.get('type') or not data.get('points'):
            return jsonify({"error": "Необходимы содержание, тип и баллы вопроса"}), 400
        
        # Обработка изображения вопроса
        image_id = None
        if 'image' in files:
            filename = save_question_image(files['image'])
            if filename:
                image_id = SQL_request('''
                    INSERT INTO images (data, mime_type)
                    VALUES (?, ?)
                    RETURNING id
                ''', (files['image'].read(), files['image'].content_type), fetch='one')["id"]
        
        # Создание вопроса
        question_id = SQL_request('''
            INSERT INTO questions (content, type, points, image_id)
            VALUES (?, ?, ?, ?)
            RETURNING id
        ''', (
            data['content'],
            data['type'],
            int(data['points']),
            image_id
        ), fetch="one")["id"]

        # Добавление вариантов ответов
        answers = json.loads(data.get('answers', '[]'))
        for answer in answers:
            SQL_request('''
                INSERT INTO answers (question_id, content, is_correct)
                VALUES (?, ?, ?)
            ''', (
                question_id,
                answer['content'],
                answer.get('is_correct', False)
            ))
        
        # Связывание вопроса с тестом
        SQL_request('''
            INSERT INTO olympiad_questions (olympiad_id, question_id)
            VALUES (?, ?)
        ''', (olympiad_id, question_id))
        
        logger.info(f"Добавлен вопрос ID {question_id} в олимпиаду {olympiad_id}")
        return jsonify({"message": "Вопрос добавлен", "question_id": question_id}), 201
    except Exception as e:
        logger.error(f"Ошибка добавления вопроса в олимпиаду {olympiad_id}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Получение олимпиды
@api.route('/olympiads/<int:olympiad_id>', methods=['GET'])
@auth_decorator()
def get_olympiad(olympiad_id):
    try:
        # Для студентов: только доступные олимпиады
        # Для преподавателей: все олимпиады
        now = datetime.utcnow().isoformat()
        
        if g.user and g.user['role'] in ['teacher', 'admin']:
            olympiads = SQL_request(
                "SELECT * FROM olympiads WHERE id = ?", (olympiad_id,),
                fetch="one"
            )
        else:
            olympiads = SQL_request(
                "SELECT * FROM olympiads WHERE start_time <= ? AND end_time >= ? and id",
                (now, now, olympiad_id),
                fetch="one"
            )

        if olympiads is None:
            return jsonify({"error":"Олимпиада не найдена"}), 400


        questions = SQL_request('''
            SELECT q.id, q.content, q.type, q.points, q.image_id
            FROM questions q
            JOIN olympiad_questions tq ON q.id = tq.question_id
            WHERE tq.olympiad_id = ?
            ORDER BY tq.rowid
        ''', (olympiad_id,), fetch="all")
        
        # Для каждого вопроса получаем варианты ответов
        for question in questions:
            answers = SQL_request('''
                SELECT id, content, is_correct
                FROM answers
                WHERE question_id = ?
                ORDER BY id
            ''', (question['id'],), fetch="all")
            question['answers'] = answers
        
        olympiads['questions'] = questions
        
        return jsonify(olympiads), 200

    except Exception as e:
        print(f"Ошибка получения списка олимпиад: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/olympiads', methods=['POST'])
@auth_decorator('teacher')
def create_olympiad():
    try:
        data = request.get_json()
        
        # Валидация данных
        if not data.get('title') or not data.get('grading_system'):
            return jsonify({"error": "Необходимы название и система оценивания"}), 400
        
        # Создание олимпиадаа
        olympiad_id = SQL_request('''
            INSERT INTO olympiads (title, description, creator_id, grading_system, start_time, end_time, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        ''', (
            data['title'],
            data.get('description', ''),
            g.user['id'],
            json.dumps(data['grading_system']),
            data.get('start_time'),
            data.get('end_time'),
            data.get('duration')
        ), fetch="one")["id"]
        
        logger.info(f"Создана новая олимпиада ID {olympiad_id} пользователем {g.user['id']}")
        return jsonify({"message": "олимпиада создана", "olympiad_id": olympiad_id}), 201
    except Exception as e:
        logger.error(f"Ошибка создания олимпиадаа: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


# Начало прохождения олимпиады
@api.route('/olympiads/<int:olympiad_id>/start', methods=['POST'])
@auth_decorator()
def start_olympiad(olympiad_id):
    try:
        # Проверка доступности олимпиады
        olympiad = SQL_request(
            "SELECT * FROM olympiads WHERE id = ?",
            (olympiad_id,),
            fetch="one"
        )
        if not olympiad:
            return jsonify({"error": "Олимпиада не найдена"}), 404
        
        now = datetime.utcnow()
        start_time = datetime.strptime(olympiad['start_time'], '%d-%m-%Y %H:%M')
        end_time = datetime.strptime(olympiad['end_time'], '%d-%m-%Y %H:%M')
        
        if now < start_time:
            return jsonify({"error": "Олимпиада еще не началась"}), 403
        if now > end_time:
            return jsonify({"error": "Олимпиада уже завершилась"}), 403

        
        # Проверка, что пользователь еще не начал олимпиаду
        existing_result = SQL_request(
            "SELECT id FROM olympiad_results WHERE user_id = ? AND olympiad_id = ?",
            (g.user['id'], olympiad_id),
            fetch="one"
        )

        if existing_result:
            return jsonify({"message": "Вы уже начали эту олимпиаду", "result_id":existing_result}), 200
        
        # Расчет времени окончания
        end_time = now + timedelta(minutes=olympiad['duration'])
        if end_time > datetime.strptime(olympiad['end_time'], '%d-%m-%Y %H:%M'):
            end_time = datetime.strptime(olympiad['end_time'], '%d-%m-%Y %H:%M')

        rr = SQL_request(
                    "SELECT SUM(points) FROM questions q JOIN olympiad_questions oq ON q.id = oq.question_id WHERE oq.olympiad_id = ?",
                    (olympiad_id,),
                    fetch="one"
                )['SUM(points)']
        print(rr)
        # Созданиеие записи о прохождении
        result_id = SQL_request(
            '''INSERT INTO olympiad_results 
            (user_id, olympiad_id, start_time, end_time, total_score) 
            VALUES (?, ?, ?, ?, ?) RETURNING id''',
            (
                g.user['id'],
                olympiad_id,
                now.isoformat(),
                end_time.isoformat(),
                # Расчет максимального балла
                SQL_request(
                    "SELECT SUM(points) FROM questions q JOIN olympiad_questions oq ON q.id = oq.question_id WHERE oq.olympiad_id = ?",
                    (olympiad_id,),
                    fetch="one"
                )['SUM(points)']
            ),
            fetch="one"
        )
        
        logger.info(f"Пользователь {g.user['id']} начал олимпиаду {olympiad_id}")
        return jsonify({
            "message": "Олимпиада начата",
            "result_id": result_id,
            "end_time": end_time.isoformat()
        }), 200

    except Exception as e:
        print(f"Ошибка начала олимпиады: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Отправка ответа на вопрос олимпиады
@api.route('/olympiads/answers', methods=['POST'])
@auth_decorator(role='student')
def submit_olympiad_answer():
    try:
        data = request.get_json()
        required_fields = ['result_id', 'question_id', 'answer']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Не хватает обязательных полей"}), 400
        
        # Проверка принадлежности результата пользователю
        result = SQL_request(
            "SELECT * FROM olympiad_results WHERE id = ? AND user_id = ?",
            (data['result_id'], g.user['id']),
            fetch="one"
        )
        if not result:
            return jsonify({"error": "Результат не найден"}), 404
        
        # Проверка времени
        if datetime.utcnow() > datetime.fromisoformat(result['end_time']):
            return jsonify({"error": "Время на прохождение олимпиады истекло"}), 403
        # Сохранение ответа
        SQL_request(
            '''INSERT OR REPLACE INTO user_answers 
            (result_id, question_id, answer_ids, answer_text, is_olympiad) 
            VALUES (?, ?, ?, ?, 1)''',
            (
                data['result_id'],
                data['question_id'],
                json.dumps(data['answer'].get('answer_ids')) if 'answer_ids' in data['answer'] else None,
                data['answer'].get('answer_text')
            )
        )
        
        logger.info(f"Пользователь {g.user['id']} ответил на вопрос {data['question_id']} в олимпиаде")
        return jsonify({"message": "Ответ сохранен"}), 200

    except Exception as e:
        print(f"Ошибка сохранения ответа: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Завершение олимпиады
@api.route('/olympiads/<int:result_id>/finish', methods=['POST'])
@auth_decorator(role='student')
def finish_olympiad(result_id):
    try:
        # Обновление времени завершения
        SQL_request(
            "UPDATE olympiad_results SET end_time = ? WHERE id = ? AND user_id = ?",
            (datetime.utcnow().isoformat(), result_id, g.user['id'])
        )
        
        logger.info(f"Пользователь {g.user['id']} завершил олимпиаду (результат {result_id})")
        return jsonify({"message": "Олимпиада завершена"}), 200

    except Exception as e:
        logger.error(f"Ошибка завершения олимпиады: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Проверка олимпиады преподавателем
@api.route('/olympiads/results/<int:result_id>/review', methods=['POST'])
@auth_decorator('teacher')
def review_olympiad(result_id):
    try:
        data = request.get_json()
        if 'scores' not in data:
            return jsonify({"error": "Не указаны баллы за ответы"}), 400
        
        # Проверка прав доступа
        olymoiad = SQL_request(
            '''SELECT o.*, o.creator_id 
            FROM olympiad_results r 
            JOIN olympiads o ON r.olympiad_id = o.id 
            WHERE r.id = ?''',
            (result_id,),
            fetch="one"
        )

        result = SQL_request("SELECT * FROM olympiad_results WHERE id = ?", (result_id,))
        if not result:
            return jsonify({"error": "Результат не найден"}), 404
        
        if olymoiad['creator_id'] != g.user['id'] and g.user['role'] != 'admin':
            return jsonify({"error": "Нет прав на проверку этой олимпиады"}), 403
        
        total_score = data['scores']

        if data['scores'] > total_score:
            return jsonify({"error": "Превышено количество баллов"}), 400
        
        # Расчет оценки
        grading_system = (olymoiad['grading_system'])
        percentage = (total_score / result['total_score']) * 100
        grade = None
        for g_grade, g_percent in sorted(grading_system.items(), key=lambda x: x[1], reverse=True):
            if percentage >= g_percent:
                grade = g_grade
                break
        # Обновление общего результата
        SQL_request(
            "UPDATE olympiad_results SET score = ?, grade = ?, is_checked = 1 WHERE id = ?",
            (total_score, grade, result_id)
        )
        
        logger.info(f"Олимпиада {result_id} проверена преподавателем {g.user['id']}")
        return jsonify({"message": "Олимпиада проверена", "total_score": total_score, "grade": grade}), 200

    except Exception as e:
        print(f"Ошибка проверки олимпиады: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


# Получение результатов олимпиады
@api.route('/olympiads/results/<int:result_id>', methods=['GET'])
@auth_decorator()
def get_olympiad_result(result_id):
    try:
        # Проверка прав доступа
        result = SQL_request(
            "SELECT * FROM olympiad_results WHERE id = ?",
            (result_id,),
            fetch="one"
        )
        if not result:
            return jsonify({"error": "Результат не найден"}), 404
        
        if g.user['role'] == 'student' and result['user_id'] != g.user['id']:
            return jsonify({"error": "Нет доступа к этому результату"}), 403
        
        # Для преподавателя проверяем, что он создатель олимпиады
        if g.user['role'] in ['teacher', 'admin']:
            olympiad = SQL_request(
                "SELECT creator_id FROM olympiads WHERE id = ?",
                (result['olympiad_id'],),
                fetch="one"
            )
            if olympiad['creator_id'] != g.user['id'] and g.user['role'] != 'admin':
                return jsonify({"error": "Нет прав доступа к этому результату"}), 403
        
        # Получение ответов
        answers = SQL_request(
            "SELECT * FROM user_answers WHERE result_id = ? AND is_olympiad = 1",
            (result_id,),
            fetch="all"
        )
        
        result['answers'] = answers
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Ошибка получения результата: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# Добавление олимпиады в избранное
@api.route('/olympiads/<int:olympiad_id>/favorite', methods=['POST'])
@auth_decorator()
def add_olympiad_to_favorite(olympiad_id):
    try:
        # Проверка существования олимпиады
        olympiad = SQL_request(
            "SELECT id FROM olympiads WHERE id = ?",
            (olympiad_id,),
            fetch="one"
        )
        if not olympiad:
            return jsonify({"error": "Олимпиада не найдена"}), 404
        
        # Добавление в избранное
        SQL_request(
            "INSERT OR IGNORE INTO favorites (user_id, olympiad_id) VALUES (?, ?)",
            (g.user['id'], olympiad_id)
        )
        
        return jsonify({"message": "Олимпиада добавлена в избранное"}), 200

    except Exception as e:
        logger.error(f"Ошибка добавления в избранное: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500