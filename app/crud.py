# backend/app/crud.py
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case, extract, func, select, delete
from sqlalchemy.orm import selectinload
from . import models, schemas
import uuid
import secrets
import string
from datetime import datetime, timezone

async def get_quizzes(db: AsyncSession):
    result = await db.execute(
        select(models.Quiz)
        .options(selectinload(models.Quiz.questions))
    )
    return result.scalars().all()

async def create_quiz(db: AsyncSession, data: schemas.QuizCreate):
    quiz = models.Quiz(
        id=str(uuid.uuid4()),
        title=data.title,
        desc=data.desc,
        difficulty=data.difficulty,
        time_per_question=data.time_per_question,
        is_custom=True
    )
    for q in data.questions:
        quiz.questions.append(
            models.Question(
                id=str(uuid.uuid4()),
                text=q.text,        # ✅ text, а не q
                options=q.options,
                correct=q.correct,
                explanation=q.explanation
            )
        )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz, ["questions"])
    return quiz

async def update_quiz(db: AsyncSession, quiz_id: str, data: schemas.QuizCreate):
    result = await db.execute(
        select(models.Quiz)
        .options(selectinload(models.Quiz.questions))
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        return None
    
    # Обновляем основные поля
    quiz.title = data.title
    quiz.desc = data.desc
    quiz.difficulty = data.difficulty
    quiz.time_per_question = data.time_per_question
    
    # Полностью перезаписываем вопросы
    await db.execute(delete(models.Question).where(models.Question.quiz_id == quiz_id))
    for q in data.questions:
        quiz.questions.append(
            models.Question(
                id=str(uuid.uuid4()),
                text=q.text,        # ✅ text, а не q
                options=q.options,
                correct=q.correct,
                explanation=q.explanation
            )
        )
    
    await db.commit()
    await db.refresh(quiz, ["questions"])
    return quiz

async def delete_quiz(db: AsyncSession, quiz_id: str):
    result = await db.execute(delete(models.Quiz).where(models.Quiz.id == quiz_id))
    await db.commit()
    return result.rowcount > 0

async def save_result(db: AsyncSession, data: schemas.ResultCreate):
    result = models.Result(
        id=str(uuid.uuid4()),
        quiz_id=data.quiz_id,
        quiz_name=data.quiz_name,
        correct=data.correct,
        total=data.total,
        score=data.score,
        time=data.time
    )
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result

async def get_results(db: AsyncSession):
    result = await db.execute(
        select(models.Result)
        .order_by(models.Result.created_at.desc())
    )
    return result.scalars().all()

async def clear_results(db: AsyncSession):
    await db.execute(delete(models.Result))
    await db.commit()


def _generate_host_code(length: int = 6) -> str:
    """Генерирует уникальный 6-значный код (буквы + цифры)"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


async def create_session(db: AsyncSession, quiz_id: str) -> models.QuizSession:
    """Создаёт новую сессию для квиза"""
    # Проверяем существование квиза
    quiz = await db.get(models.Quiz, quiz_id)
    if not quiz:
        raise ValueError(f"Quiz {quiz_id} not found")
    
    # Генерируем уникальный код
    while True:
        code = _generate_host_code()
        result = await db.execute(
            select(models.QuizSession).where(models.QuizSession.host_code == code)
        )
        if not result.scalar_one_or_none():
            break
    
    session = models.QuizSession(
        id=str(uuid.uuid4()),
        quiz_id=quiz_id,
        host_code=code
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def join_session(db: AsyncSession, session_id: str, nickname: str) -> tuple[models.Player, models.QuizSession]:
    """Присоединяет игрока к сессии"""
    session = await db.get(models.QuizSession, session_id)
    if not session or session.status != "waiting":
        return None, None
    
    # Ограничение на длину никнейма
    nickname = nickname.strip()[:50]
    if len(nickname) < 2:
        return None, None
    
    player = models.Player(
        id=str(uuid.uuid4()),
        session_id=session_id,
        nickname=nickname,
        player_token=secrets.token_urlsafe(32)  # 43 символа, безопасно
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player, session


async def get_session_with_players(db: AsyncSession, session_id: str):
    """Получает сессию с игроками и квизом"""
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(models.QuizSession)
        .options(
            selectinload(models.QuizSession.quiz),
            selectinload(models.QuizSession.players)
        )
        .where(models.QuizSession.id == session_id)
    )
    return result.scalar_one_or_none()



async def get_session_by_code(db: AsyncSession, host_code: str) -> Optional[models.QuizSession]:
    """Находит сессию по коду присоединения"""
    result = await db.execute(
        select(models.QuizSession)
        .where(models.QuizSession.host_code == host_code)
    )
    return result.scalar_one_or_none()


async def start_session(db: AsyncSession, session_id: str) -> Optional[models.QuizSession]:
    """Запускает сессию (переводит в статус active)"""
    session = await db.get(models.QuizSession, session_id)
    if not session or session.status != "waiting":
        return None
    
    session.status = "active"
    session.started_at = datetime.now(timezone.utc)
    session.current_question = 0
    await db.commit()
    await db.refresh(session)
    return session


async def next_question(db: AsyncSession, session_id: str) -> Optional[models.QuizSession]:
    """Переходит к следующему вопросу"""
    session = await db.get(models.QuizSession, session_id)
    if not session or session.status != "active":
        return None
    
    quiz = await db.get(models.Quiz, session.quiz_id)
    if not quiz:
        return None
    
    # Если вопросы закончились — завершаем сессию
    if session.current_question >= len(quiz.questions) - 1:
        session.status = "finished"
        session.finished_at = datetime.now(timezone.utc)
        # Помечаем всех игроков как завершивших
        for player in session.players:
            player.finished = True
    else:
        session.current_question += 1
    
    await db.commit()
    await db.refresh(session)
    return session


async def submit_answer(
    db: AsyncSession, 
    player_token: str, 
    question_index: int, 
    selected_option: int,
    time_left: int
) -> Optional[tuple[models.PlayerAnswer, models.Player]]:
    """Обрабатывает ответ игрока, сохраняет время раздумий и начисляет бонус"""
    
    # 1. Находим игрока
    result = await db.execute(
        select(models.Player).where(models.Player.player_token == player_token)
    )
    player = result.scalar_one_or_none()
    if not player:
        return None
    
    # 2. Проверяем сессию
    session = await get_session_with_players(db, player.session_id)
    if not session or session.status != "active":
        return None
    
    # 3. Проверяем актуальность вопроса
    if question_index != session.current_question:
        return None
    
    # 4. Валидируем квиз и вопрос
    quiz = session.quiz
    if not quiz or question_index < 0 or question_index >= len(quiz.questions):
        return None
    
    question = quiz.questions[question_index]
    is_correct = (selected_option == question.correct)
    
    # 5. 🛡️ Безопасный расчёт времени и бонуса
    max_time = quiz.time_per_question or 30
    # Защита от рассинхрона: time_left не может быть <0 или >max_time
    valid_time_left = max(0, min(int(time_left), max_time))
    
    # Сколько секунд игрок реально думал
    time_spent_ms = int((max_time - valid_time_left) * 1000)
    
    # Бонус за скорость (только за правильный ответ)
    speed_bonus = 0
    if is_correct and max_time > 0:
        speed_bonus = round((valid_time_left / max_time) * 50)
    
    # 6. Сохраняем ответ с временем раздумий
    answer = models.PlayerAnswer(
        id=str(uuid.uuid4()),
        player_id=player.id,
        question_index=question_index,
        selected_option=selected_option,
        is_correct=is_correct,
        response_time_ms=time_spent_ms  # ✅ Ключевое исправление
    )
    db.add(answer)
    
    # 7. Обновляем статистику
    if is_correct:
        player.correct_answers += 1
        player.score += 100 + speed_bonus
    
    await db.commit()
    await db.refresh(answer)
    await db.refresh(player)
    return answer, player


async def finish_session(db: AsyncSession, session_id: str) -> Optional[models.QuizSession]:
    """Завершает сессию (идемпотентно — можно вызывать много раз)"""
    try:
        session = await db.get(models.QuizSession, session_id)
        if not session:
            return None
        
        # Если уже завершена — просто возвращаем (защита от повторных вызовов)
        if session.status == "finished":
            return session
        
        session.status = "finished"
        session.finished_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(session)
        
        return session
        
    except Exception as e:
        import logging
        logging.error(f"finish_session error: {e}")
        await db.rollback()
        raise  # Перебрасываем, чтобы сработал global_exception_handler


async def get_leaderboard(db: AsyncSession, session_id: str) -> List[dict]:
    """Возвращает таблицу лидеров (без хоста)"""
    session = await get_session_with_players(db, session_id)
    if not session:
        return []
    
    # 🔑 Определяем хоста: первый игрок в сессии (или по префиксу ника)
    host_player = session.players[0] if session.players else None
    
    # Фильтруем: исключаем хоста
    players_to_rank = [
        p for p in session.players 
        if host_player is None or p.id != host_player.id  # Исправлено: проверяем через is None / is not None
    ]
    
    # Сортируем: очки (убыв.), затем никнейм
    sorted_players = sorted(
        players_to_rank,
        key=lambda p: (-p.score, p.nickname)
    )
    
    return [
        {
            "rank": i + 1,
            "nickname": p.nickname,
            "score": p.score,
            "correct": p.correct_answers
        }
        for i, p in enumerate(sorted_players)
    ]


async def get_player_by_token(db: AsyncSession, token: str) -> Optional[models.Player]:
    """Находит игрока по токену"""
    result = await db.execute(
        select(models.Player).where(models.Player.player_token == token)
    )
    return result.scalar_one_or_none()

async def get_session_state_data(db: AsyncSession, session_id: str):
    """Возвращает безопасные данные для ответа API"""
    session = await get_session_with_players(db, session_id)
    if not session:
        return None
    
    # Безопасное получение данных о квизе
    quiz = session.quiz
    quiz_title = quiz.title if quiz else "Unknown"
    total_questions = len(quiz.questions) if quiz and quiz.questions else 0
    
    return {
        "session_id": session.id,
        "quiz_id": session.quiz_id,
        "quiz_title": quiz_title,
        "status": session.status,
        "current_question": session.current_question if session.status == "active" else None,
        "total_questions": total_questions,
        "host_code": session.host_code if session.status == "waiting" else None,
        "players": [
            {
                "id": p.id,
                "nickname": p.nickname,
                "score": p.score,
                "correct_answers": p.correct_answers,
                "finished": p.finished
            }
            for p in session.players
        ]
    }

async def get_quiz_analytics(db: AsyncSession, quiz_id: str) -> Optional[dict]:
    """Собирает корректную аналитику по квизу (без отрицательных/огромных значений)"""
    
    quiz = await db.get(models.Quiz, quiz_id)
    if not quiz:
        return None
    
    # 1. Собираем ID всех сессий этого квиза
    sessions_result = await db.execute(
        select(models.QuizSession.id).where(models.QuizSession.quiz_id == quiz_id)
    )
    session_ids = [row[0] for row in sessions_result.all()]
    
    if not session_ids:
        return {
            "quiz_id": quiz_id, "quiz_title": quiz.title, "total_players": 0,
            "total_attempts": 0, "avg_score": 0, "avg_completion_time": 0,
            "questions": [], "created_at": quiz.created_at
        }

    # 2. Уникальные игроки
    total_players = await db.scalar(
        select(func.count(models.Player.id.distinct())).where(
            models.Player.session_id.in_(session_ids)
        )
    ) or 0

    # 3. Статистика по вопросам
    questions_stats = []
    for idx, question in enumerate(quiz.questions):
        # Подсчёт ответов и правильных
        counts = await db.execute(
            select(
                func.count(models.PlayerAnswer.id),
                func.sum(case((models.PlayerAnswer.is_correct == True, 1), else_=0))
            ).where(
                models.PlayerAnswer.question_index == idx,
                models.PlayerAnswer.player_id.in_(
                    select(models.Player.id).where(models.Player.session_id.in_(session_ids))
                )
            )
        )
        total_answers, correct_count = counts.first()
        total_answers = total_answers or 0
        correct_count = correct_count or 0
        
        # ✅ ИСПРАВЛЕННОЕ ВРЕМЯ: берём среднее из response_time_ms
        avg_time_ms = await db.scalar(
            select(func.avg(models.PlayerAnswer.response_time_ms)).where(
                models.PlayerAnswer.question_index == idx,
                models.PlayerAnswer.player_id.in_(
                    select(models.Player.id).where(models.Player.session_id.in_(session_ids))
                )
            )
        )
        # Конвертируем мс → секунды, убираем None/отрицательные
        avg_response_time = round(avg_time_ms / 1000, 1) if avg_time_ms and avg_time_ms > 0 else None

        # Распределение по вариантам (A, B, C, D)
        option_dist = []
        most_wrong = None
        max_wrong = 0
        
        for opt_idx in range(4):
            wrong_count = await db.scalar(
                select(func.count(models.PlayerAnswer.id)).where(
                    models.PlayerAnswer.question_index == idx,
                    models.PlayerAnswer.selected_option == opt_idx,
                    models.PlayerAnswer.is_correct == False,
                    models.PlayerAnswer.player_id.in_(
                        select(models.Player.id).where(models.Player.session_id.in_(session_ids))
                    )
                )
            ) or 0
            option_dist.append(wrong_count)
            
            if opt_idx != question.correct and wrong_count > max_wrong:
                max_wrong = wrong_count
                most_wrong = opt_idx

        questions_stats.append({
            "question_index": idx,
            "question_text": question.text[:100] + "..." if len(question.text) > 100 else question.text,
            "total_answers": total_answers,
            "correct_count": correct_count,
            "wrong_count": total_answers - correct_count,
            "accuracy_rate": round(correct_count / total_answers, 2) if total_answers > 0 else 0,
            "avg_response_time": avg_response_time,  # ✅ Теперь корректное значение в секундах
            "option_distribution": option_dist,
            "most_chosen_wrong": most_wrong
        })

    # 4. Общие метрики из таблицы results
    results_stats = await db.execute(
        select(func.avg(models.Result.score), func.avg(models.Result.time))
        .where(models.Result.quiz_id == quiz_id)
    )
    avg_score, avg_completion = results_stats.first()

    return {
        "quiz_id": quiz_id,
        "quiz_title": quiz.title,
        "total_players": total_players,
        "total_attempts": sum(q["total_answers"] for q in questions_stats),
        "avg_score": round(avg_score or 0, 1),
        "avg_completion_time": round(avg_completion or 0, 1),
        "questions": questions_stats,
        "created_at": quiz.created_at
    }