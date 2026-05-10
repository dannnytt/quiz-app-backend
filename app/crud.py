# backend/app/crud.py
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
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
        emoji=data.emoji,
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
    quiz.emoji = data.emoji
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
        emoji=data.emoji,
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
    selected_option: int
) -> Optional[tuple[models.PlayerAnswer, models.Player]]:
    """Обрабатывает ответ игрока"""
    # Находим игрока по токену
    result = await db.execute(
        select(models.Player)
        .where(models.Player.player_token == player_token)
    )
    player = result.scalar_one_or_none()
    if not player:
        return None
    
    # Проверяем сессию
    session = await get_session_with_players(db, player.session_id)
    if not session or session.status != "active":
        return None
    
    # Проверяем, что вопрос соответствует текущему
    if question_index != session.current_question:
        return None
    
    # Получаем правильный ответ
    quiz = session.quiz
    if question_index < 0 or question_index >= len(quiz.questions):
        return None
    
    question = quiz.questions[question_index]
    is_correct = (selected_option == question.correct)
    
    # Сохраняем ответ
    answer = models.PlayerAnswer(
        id=str(uuid.uuid4()),
        player_id=player.id,
        question_index=question_index,
        selected_option=selected_option,
        is_correct=is_correct
    )
    db.add(answer)
    
    # Обновляем статистику игрока
    if is_correct:
        player.correct_answers += 1
        # Базовые очки + бонус за скорость (опционально)
        player.score += 100
    
    await db.commit()
    await db.refresh(answer)
    await db.refresh(player)
    return answer, player


async def finish_session(db: AsyncSession, session_id: str) -> Optional[models.QuizSession]:
    """Завершает сессию и сохраняет результаты"""
    session = await get_session_with_players(db, session_id)
    if not session:
        return None
    
    session.status = "finished"
    session.finished_at = datetime.now(timezone.utc)
    
    # Сохраняем результаты каждого игрока в общую таблицу
    for player in session.players:
        time_spent = 0
        if session.started_at and session.finished_at:
            time_spent = int((session.finished_at - session.started_at).total_seconds())
        
        result = models.Result(
            id=str(uuid.uuid4()),
            quiz_id=session.quiz_id,
            quiz_name=session.quiz.title,
            emoji=session.quiz.emoji,
            correct=player.correct_answers,
            total=len(session.quiz.questions),
            score=player.score,
            time=time_spent
        )
        db.add(result)
    
    await db.commit()
    await db.refresh(session)
    return session


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