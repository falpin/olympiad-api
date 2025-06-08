from flask import request, jsonify, g, abort
from . import api, SQL_request, auth_decorator, logger
import json
from datetime import datetime
import sqlite3
from werkzeug.utils import secure_filename
import os
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS
import ast
import re

# Вспомогательные функции
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_string(text):
    if text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r'[^\w]', '', text)
    return text


def save_question_image(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, 'questions', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        return filename
    return None

# Роуты для тестов
@api.route('/tests', methods=['GET'])
def get_tests():
    try:
        # Получаем список всех тестов с информацией о создателе
        tests = SQL_request('''
            SELECT t.id, t.title, t.description, t.grading_system, t.is_open,
                   u.id as creator_id, u.first_name as creator_first_name, 
                   u.last_name as creator_last_name
            FROM tests t
            JOIN users u ON t.creator_id = u.id
            WHERE t.is_open = 1
        ''', fetch="all")
        
        return jsonify(tests), 200
    except Exception as e:
        logger.error(f"Ошибка получения списка тестов: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests', methods=['POST'])
@auth_decorator(role='teacher')
def create_test():
    try:
        data = request.get_json()
        
        # Валидация данных
        if not data.get('title') or not data.get('grading_system'):
            return jsonify({"error": "Необходимы название и система оценивания"}), 400
        
        # Создание теста
        test_id = SQL_request('''
            INSERT INTO tests (title, description, creator_id, grading_system, is_open)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        ''', (
            data['title'],
            data.get('description', ''),
            g.user['id'],
            json.dumps(data['grading_system']),
            data.get('is_open', True)
        ), fetch="one")["id"]
        
        logger.info(f"Создан новый тест ID {test_id} пользователем {g.user['id']}")
        return jsonify({"message": "Тест создан", "test_id": test_id}), 201
    except Exception as e:
        logger.error(f"Ошибка создания теста: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests/<int:test_id>', methods=['GET'])
def get_test(test_id):
    try:
        # Получаем основную информацию о тесте
        test = SQL_request('''
            SELECT t.id, t.title, t.description, t.grading_system, t.is_open,
                   u.id as creator_id, u.first_name as creator_first_name, 
                   u.last_name as creator_last_name
            FROM tests t
            JOIN users u ON t.creator_id = u.id
            WHERE t.id = ?
        ''', (test_id,), fetch="one")
        
        if not test:
            return jsonify({"error": "Тест не найден"}), 404
        
        # Получаем вопросы теста
        questions = SQL_request('''
            SELECT q.id, q.content, q.type, q.points, q.image_id
            FROM questions q
            JOIN test_questions tq ON q.id = tq.question_id
            WHERE tq.test_id = ?
            ORDER BY tq.rowid
        ''', (test_id,), fetch="all")
        
        # Для каждого вопроса получаем варианты ответов
        for question in questions:
            answers = SQL_request('''
                SELECT id, content, is_correct
                FROM answers
                WHERE question_id = ?
                ORDER BY id
            ''', (question['id'],), fetch="all")
            question['answers'] = answers
        
        test['questions'] = questions
        
        return jsonify(test), 200
    except Exception as e:
        logger.error(f"Ошибка получения теста {test_id}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests/<int:test_id>/questions', methods=['POST'])
@auth_decorator(role='teacher')
def add_question_to_test(test_id):
    try:
        # Проверяем, что тест существует и принадлежит текущему пользователю
        test = SQL_request('SELECT creator_id FROM tests WHERE id = ?', (test_id,), fetch="one")
        if not test:
            return jsonify({"error": "Тест не найден"}), 404
        
        if test['creator_id'] != g.user['id'] and g.user['role'] != 'admin':
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
            INSERT INTO test_questions (test_id, question_id)
            VALUES (?, ?)
        ''', (test_id, question_id))
        
        logger.info(f"Добавлен вопрос ID {question_id} в тест {test_id}")
        return jsonify({"message": "Вопрос добавлен", "question_id": question_id}), 201
    except Exception as e:
        logger.error(f"Ошибка добавления вопроса в тест {test_id}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests/<int:test_id>/answer', methods=['POST'])
@auth_decorator()
def answer_test_question(test_id):
    try:
        data = request.get_json()
        
        # Проверяем, что у пользователя есть активная попытка прохождения теста
        active_attempt = SQL_request('''
            SELECT id FROM test_results 
            WHERE user_id = ? AND test_id = ? AND end_time IS 0
            ORDER BY start_time DESC LIMIT 1
        ''', (g.user['id'], test_id), fetch="one")
        
        if not active_attempt:
            return jsonify({"error": "Нет активной попытки прохождения теста"}), 400
        
        result_id = active_attempt['id']
        question_id = data.get('question_id')
        
        if not question_id:
            return jsonify({"error": "Не указан ID вопроса"}), 400
        
        # Проверяем, что вопрос принадлежит тесту
        question_exists = SQL_request('''
            SELECT 1 FROM test_questions 
            WHERE test_id = ? AND question_id = ?
        ''', (test_id, question_id), fetch="one")
        
        if not question_exists:
            return jsonify({"error": "Вопрос не принадлежит этому тесту"}), 404
        
        # Удаляем предыдущие ответы на этот вопрос (если есть)
        SQL_request('''
            DELETE FROM user_answers 
            WHERE result_id = ? AND question_id = ? AND is_olympiad = 0
        ''', (result_id, question_id))
        
        # Сохраняем ответ в зависимости от типа вопроса
        question_type = SQL_request('''
            SELECT type FROM questions WHERE id = ?
        ''', (question_id,), fetch="one")['type']
        
        if question_type == 'text':
            # Для текстового ответа
            answer_text = data.get('answer_text')
            SQL_request('''
                INSERT INTO user_answers 
                (result_id, question_id, answer_text, is_olympiad)
                VALUES (?, ?, ?, 0)
            ''', (result_id, question_id, answer_text))
        else:
            # Для вопросов с выбором ответа
            answer_ids = data.get('answer_ids', [])
            if not isinstance(answer_ids, list) and answer_text is not None:
                return jsonify({"error": "answer_ids должен быть массивом"}), 400
            
            SQL_request('''
                INSERT INTO user_answers 
                (result_id, question_id, answer_ids, is_olympiad)
                VALUES (?, ?, ?, 0)
            ''', (result_id, question_id, json.dumps(answer_ids)))
        
        return jsonify({"message": "Ответ сохранен"}), 200
    
    except Exception as e:
        logger.error(f"Ошибка сохранения ответа: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@api.route('/tests/<int:test_id>/progress', methods=['GET'])
@auth_decorator()
def get_test_progress(test_id):
    try:
        # Получаем активную попытку
        active_attempt = SQL_request('''
            SELECT id FROM test_results 
            WHERE user_id = ? AND test_id = ? AND end_time IS 0
            ORDER BY start_time DESC LIMIT 1
        ''', (g.user['id'], test_id), fetch="one")
        
        if not active_attempt:
            return jsonify({"error": "Нет активной попытки прохождения теста"}), 400
        
        result_id = active_attempt['id']
        
        # Получаем все вопросы теста
        questions = SQL_request('''
            SELECT q.id, q.content, q.type, q.points, q.image_id
            FROM questions q
            JOIN test_questions tq ON q.id = tq.question_id
            WHERE tq.test_id = ?
            ORDER BY tq.rowid
        ''', (test_id,), fetch="all")
        
        # Получаем ответы пользователя
        user_answers = SQL_request('''
            SELECT question_id, answer_ids, answer_text
            FROM user_answers
            WHERE result_id = ? AND is_olympiad = 0
        ''', (result_id,), fetch="all")
        
        # Формируем ответ
        response = {
            "test_id": test_id,
            "result_id": result_id,
            "questions": []
        }
        
        for question in questions:
            question_data = {
                "id": question['id'],
                "content": question['content'],
                "type": question['type'],
                "points": question['points'],
                "image_id": question['image_id']
            }
            
            # Добавляем ответ пользователя, если есть
            user_answer = next(
                (ua for ua in user_answers if ua['question_id'] == question['id']), 
                None
            )
            
            if user_answer:
                if question['type'] == 'text':
                    question_data['user_answer'] = {
                        "text": user_answer['answer_text']
                    }
                else:
                    question_data['user_answer'] = {
                        "answer_ids": json.loads(user_answer['answer_ids']) if user_answer['answer_ids'] else []
                    }
            
            response['questions'].append(question_data)
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Ошибка получения прогресса по тесту: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests/<int:test_id>/start', methods=['POST'])
@auth_decorator()
def start_test(test_id):
    try:
        # Проверяем, что тест существует и доступен
        test = SQL_request('''
            SELECT id, title, grading_system
            FROM tests
            WHERE id = ? AND is_open = 1
        ''', (test_id,), fetch='one')
        
        if not test:
            return jsonify({"error": "Тест не найден или недоступен"}), 404
        
        # Создаем запись о начале теста
        result_id = SQL_request('''
            INSERT INTO test_results (
                user_id, test_id, start_time, end_time, score, total_score, grade
            ) VALUES (?, ?, datetime('now'), 0, 0, (
                SELECT SUM(points) FROM questions q
                JOIN test_questions tq ON q.id = tq.question_id
                WHERE tq.test_id = ?
            ), NULL)
            RETURNING id
        ''', (g.user['id'], test_id, test_id), fetch="one")["id"]
        
        return jsonify({
            "message": "Тест начат",
            "result_id": result_id,
            "test_title": test['title']
        }), 200
    except Exception as e:
        logger.error(f"Ошибка начала теста {test_id} пользователем {g.user['id']}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests/results/<int:result_id>/submit', methods=['POST'])
@auth_decorator()
def submit_test(result_id):
    try:
        
        active_attempt = SQL_request('''
            SELECT id FROM test_results 
            WHERE user_id = ? AND test_id = ? AND end_time IS 0
            ORDER BY start_time DESC LIMIT 1
        ''', (g.user['id'], result_id), fetch="one")
        
        if not active_attempt:
            return jsonify({"error": "Нет активной попытки прохождения теста"}), 400
        
        result_id = active_attempt['id']
        
        # Получаем все вопросы теста
        questions = SQL_request('''
            SELECT q.id, q.content, q.type, q.points, q.image_id
            FROM questions q
            JOIN test_questions tq ON q.id = tq.question_id
            WHERE tq.test_id = ?
            ORDER BY tq.rowid
        ''', (result_id,), fetch="all")
        
        # Получаем ответы пользователя
        user_answers = SQL_request('''
            SELECT question_id, answer_ids, answer_text
            FROM user_answers
            WHERE result_id = ? AND is_olympiad = 0
        ''', (result_id,), fetch="all")

        data = {"answers":user_answers}

        
        # Проверяем, что результат существует и принадлежит текущему пользователю
        result = SQL_request('''
            SELECT id, user_id, test_id, score, total_score
            FROM test_results
            WHERE id = ? AND user_id = ? AND end_time IS 0
        ''', (result_id, g.user['id']))
        
        if not result:
            return jsonify({"error": "Результат не найден или тест уже завершен"}), 404
        
        # Получаем вопросы теста с правильными ответами
        questions = SQL_request('''
            SELECT q.id, q.points, q.type,
                   GROUP_CONCAT(a.id) as correct_answers
            FROM questions q
            JOIN test_questions tq ON q.id = tq.question_id
            LEFT JOIN answers a ON a.question_id = q.id AND a.is_correct = 1
            WHERE tq.test_id = (SELECT test_id FROM test_results WHERE id = ?)
            GROUP BY q.id
        ''', (result_id,), fetch="all")
        
        # Проверяем ответы пользователя
        total_score = 0
        user_answers = data.get('answers', [])

        for question in questions:
            question_id = question['id']
            user_answer = next((a for a in user_answers if a['question_id'] == question_id), None)
            if user_answer is None:
                continue


            if question['type'] == 'text':
                answer_text = user_answer["answer_text"]
                correct_answers = SQL_request("SELECT content FROM answers WHERE question_id = ? AND is_correct = 1", (question_id,))['content']
                correct_answers_normalized = normalize_string(correct_answers)
                answer_text_normalized = normalize_string(answer_text)
                if correct_answers_normalized == answer_text_normalized:
                    total_score += question['points']
                    continue

            correct_answers = (question['correct_answers'])
                        
            # Проверяем правильность ответа
            if question['type'] == 'single':
                user_selected = ast.literal_eval(user_answer["answer_ids"])
                if user_selected and int(user_selected[0]) == int(correct_answers):
                    total_score += question['points']
            elif question['type'] == 'multiple':
                correct_answers = [int(num.strip()) for num in correct_answers.split(",")]
                user_selected = ast.literal_eval(user_answer["answer_ids"])
                is_correct = sorted(correct_answers) == sorted(user_selected)
                if is_correct:
                    total_score += question['points']

        # Получаем систему оценивания
        grading_system = SQL_request('''
            SELECT grading_system FROM tests WHERE id = ?
        ''', (result['test_id'],), fetch="one")['grading_system']
        
        # Определяем оценку
        percentage = (total_score / result['total_score']) * 100
        grade = None
        for g_grade, g_percent in sorted(grading_system.items(), key=lambda x: x[1], reverse=True):
            if percentage >= g_percent:
                grade = g_grade
                break
        
        # Обновляем результат теста
        SQL_request('''
            UPDATE test_results
            SET end_time = datetime('now'),
                score = ?,
                grade = ?
            WHERE id = ?
        ''', (total_score, grade, result_id))
        
        logger.info(f"Пользователь {g.user['id']} завершил тест {result['test_id']} с результатом {total_score}/{result['total_score']}")
        return jsonify({
            "message": "Тест завершен",
            "score": total_score,
            "total_score": result['total_score'],
            "percentage": round(percentage, 2),
            "grade": grade
        }), 200
    except Exception as e:
        logger.error(f"Ошибка завершения теста {result_id}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/tests/results/<int:result_id>', methods=['GET'])
@auth_decorator()
def get_test_result(result_id):
    try:
        # Получаем основной результат
        result = SQL_request('''
            SELECT r.id, r.user_id, r.test_id, r.start_time, r.end_time,
                   r.score, r.total_score, r.grade,
                   t.title as test_title
            FROM test_results r
            JOIN tests t ON r.test_id = t.id
            WHERE r.id = ? AND (r.user_id = ? OR ? IN (SELECT id FROM users WHERE role = 'teacher'))
        ''', (result_id, g.user['id'], g.user['id']), fetch="one")
        
        if not result:
            return jsonify({"error": "Результат не найден или нет доступа"}), 404
        
        # Получаем вопросы и ответы пользователя
        questions = SQL_request('''
            SELECT q.id, q.content, q.type, q.points, q.image_id,
                   ua.answer_ids, ua.answer_text
            FROM questions q
            JOIN test_questions tq ON q.id = tq.question_id
            LEFT JOIN user_answers ua ON ua.question_id = q.id AND ua.result_id = ? AND ua.is_olympiad = 0
            WHERE tq.test_id = ?
            ORDER BY tq.rowid
        ''', (result_id, result['test_id']), fetch="all")
        
        # Получаем правильные ответы для вопросов
        for question in questions:
            if question['type'] != 'text':
                correct_answers = SQL_request('''
                    SELECT id, content
                    FROM answers
                    WHERE question_id = ? AND is_correct = 1
                ''', (question['id'],), fetch="all")
                question['correct_answers'] = correct_answers
            
            if question['answer_ids']:
                question['answer_ids'] = json.loads(question['answer_ids'])
        
        result['questions'] = questions
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Ошибка получения результата теста {result_id}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@api.route('/users/<int:user_id>/tests', methods=['GET'])
@auth_decorator()
def get_user_test_results(user_id):
    try:
        results = SQL_request('''
            SELECT r.id, r.test_id, r.start_time, r.end_time,
                   r.score, r.total_score, r.grade,
                   t.title as test_title
            FROM test_results r
            JOIN tests t ON r.test_id = t.id
            WHERE r.user_id = ?
            ORDER BY r.end_time DESC
        ''', (user_id,), fetch="all")
        
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Ошибка получения результатов тестов пользователя {user_id}: {str(e)}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500