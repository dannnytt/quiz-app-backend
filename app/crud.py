from typing import List, Optional
import uuid
import secrets
import string
import os
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case, func, select, delete
from sqlalchemy.orm import selectinload

from . import models, schemas, schemas_auth
from .auth import hash_password
from .config import UPLOAD_DIR


# ========== ПОЛЬЗОВАТЕЛИ ==========

async def create_user(db: AsyncSession, data: schemas_auth.UserRegister) -> models.User:
    """Создаёт нового пользователя"""
    user = models.User(
        id=str(uuid.uuid4()),
        email=data.email,
        nickname=data.nickname,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
    result = await db.execute(select(models.User).where(models.User.email == email))
    return result.scalar_one_or_none()


# ========== КВИЗЫ ==========

async def get_quizzes(db: AsyncSession):
    """Получить все квизы (публичные + пользовательские)"""
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.questions),
            selectinload(models.Quiz.owner)
        )
    )
    quizzes = result.scalars().all()
    
    # Добавляем owner_nickname для удобства фронта
    out = []
    for q in quizzes:
        quiz_dict = {
            "id": q.id,
            "title": q.title,
            "desc": q.desc,
            "difficulty": q.difficulty,
            "time_per_question": q.time_per_question,
            "is_custom": q.is_custom,
            "created_at": q.created_at,
            "cover_image": q.cover_image,
            "owner_id": q.owner_id,
            "owner_nickname": q.owner.nickname if q.owner else None,
            "questions": q.questions,
        }
        out.append(quiz_dict)
    return out


async def get_user_quizzes(db: AsyncSession, user_id: str):
    """Получить квизы конкретного пользователя"""
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.questions),
            selectinload(models.Quiz.owner)
        )
        .where(models.Quiz.owner_id == user_id)
        .order_by(models.Quiz.created_at.desc())
    )
    quizzes = result.scalars().all()
    
    out = []
    for q in quizzes:
        out.append({
            "id": q.id,
            "title": q.title,
            "desc": q.desc,
            "difficulty": q.difficulty,
            "time_per_question": q.time_per_question,
            "is_custom": q.is_custom,
            "created_at": q.created_at,
            "cover_image": q.cover_image,
            "owner_id": q.owner_id,
            "owner_nickname": q.owner.nickname if q.owner else None,
            "questions": q.questions,
        })
    return out


async def create_quiz(db: AsyncSession, data: schemas.QuizCreate, owner_id: str):
    """Создать квиз с указанием владельца"""
    quiz = models.Quiz(
        id=str(uuid.uuid4()),
        title=data.title,
        desc=data.desc,
        difficulty=data.difficulty,
        time_per_question=data.time_per_question,
        is_custom=True,
        cover_image=data.cover_image,
        owner_id=owner_id,  # ✅ Владелец
    )
    for q in data.questions:
        quiz.questions.append(
            models.Question(
                id=str(uuid.uuid4()),
                text=q.text,
                options=q.options,
                correct=q.correct,
                explanation=q.explanation,
                image=q.image,
            )
        )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz, ["questions", "owner"])
    return quiz


async def update_quiz(db: AsyncSession, quiz_id: str, data: schemas.QuizCreate, user_id: str):
    """Обновить квиз. Только владелец может редактировать."""
    result = await db.execute(
        select(models.Quiz)
        .options(selectinload(models.Quiz.questions))
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        return None
    
    # ✅ Проверка владельца
    if quiz.owner_id != user_id:
        raise PermissionError("Вы не являетесь владельцем этого квиза")
    
    quiz.title = data.title
    quiz.desc = data.desc
    quiz.difficulty = data.difficulty
    quiz.time_per_question = data.time_per_question
    quiz.cover_image = data.cover_image
    
    await db.execute(delete(models.Question).where(models.Question.quiz_id == quiz_id))
    for q in data.questions:
        quiz.questions.append(
            models.Question(
                id=str(uuid.uuid4()),
                text=q.text,
                options=q.options,
                correct=q.correct,
                explanation=q.explanation,
                image=q.image,
            )
        )
    
    await db.commit()
    await db.refresh(quiz, ["questions"])
    return quiz


async def delete_quiz(db: AsyncSession, quiz_id: str, user_id: str):
    """Удалить квиз. Только владелец может удалять."""
    result = await db.execute(
        select(models.Quiz)
        .options(selectinload(models.Quiz.questions))
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        return False
    
    # ✅ Проверка владельца
    if quiz.owner_id != user_id:
        raise PermissionError("Вы не являетесь владельцем этого квиза")
    
    # Собираем файлы для удаления
    files_to_delete = []
    if quiz.cover_image:
        files_to_delete.append(quiz.cover_image)
    for question in quiz.questions:
        if question.image:
            files_to_delete.append(question.image)
    
    await db.execute(delete(models.Quiz).where(models.Quiz.id == quiz_id))
    await db.commit()
    
    # Удаляем файлы
    for file_path in files_to_delete:
        try:
            filename = os.path.basename(file_path.lstrip("/").replace("\\", "/"))
            absolute_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(absolute_path):
                os.remove(absolute_path)
        except OSError as e:
            print(f"Failed to delete file {file_path}: {e}")
    
    return True


# ========== СЕССИИ (мультиплеер) — БЕЗ ИЗМЕНЕНИЙ ==========

def _generate_host_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


async def create_session(db: AsyncSession, quiz_id: str) -> models.QuizSession:
    quiz = await db.get(models.Quiz, quiz_id)
    if not quiz:
        raise ValueError(f"Quiz {quiz_id} not found")
    
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


async def join_session(db: AsyncSession, session_id: str, nickname: str):
    session = await db.get(models.QuizSession, session_id)
    if not session or session.status != "waiting":
        return None, None
    
    nickname = nickname.strip()[:50]
    if len(nickname) < 2:
        return None, None
    
    player = models.Player(
        id=str(uuid.uuid4()),
        session_id=session_id,
        nickname=nickname,
        player_token=secrets.token_urlsafe(32)
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player, session


async def get_session_with_players(db: AsyncSession, session_id: str):
    result = await db.execute(
        select(models.QuizSession)
        .options(
            selectinload(models.QuizSession.quiz),
            selectinload(models.QuizSession.players)
        )
        .where(models.QuizSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_session_by_code(db: AsyncSession, host_code: str):
    result = await db.execute(
        select(models.QuizSession).where(models.QuizSession.host_code == host_code)
    )
    return result.scalar_one_or_none()


async def start_session(db: AsyncSession, session_id: str):
    session = await db.get(models.QuizSession, session_id)
    if not session or session.status != "waiting":
        return None
    
    session.status = "active"
    session.started_at = datetime.now(timezone.utc)
    session.current_question = 0
    await db.commit()
    await db.refresh(session)
    return session


async def next_question(db: AsyncSession, session_id: str):
    session = await db.get(models.QuizSession, session_id)
    if not session or session.status != "active":
        return None
    
    quiz = await db.get(models.Quiz, session.quiz_id)
    if not quiz:
        return None
    
    if session.current_question >= len(quiz.questions) - 1:
        session.status = "finished"
        session.finished_at = datetime.now(timezone.utc)
        for player in session.players:
            player.finished = True
    else:
        session.current_question += 1
    
    await db.commit()
    await db.refresh(session)
    return session


async def submit_answer(db: AsyncSession, player_token: str, question_index: int, 
                       selected_option: int, time_left: int):
    result = await db.execute(
        select(models.Player).where(models.Player.player_token == player_token)
    )
    player = result.scalar_one_or_none()
    if not player:
        return None
    
    session = await get_session_with_players(db, player.session_id)
    if not session or session.status != "active":
        return None
    
    if question_index != session.current_question:
        return None
    
    quiz = session.quiz
    if not quiz or question_index < 0 or question_index >= len(quiz.questions):
        return None
    
    question = quiz.questions[question_index]
    is_correct = (selected_option == question.correct)
    
    max_time = quiz.time_per_question or 30
    valid_time_left = max(0, min(int(time_left), max_time))
    time_spent_ms = int((max_time - valid_time_left) * 1000)
    
    speed_bonus = 0
    if is_correct and max_time > 0:
        speed_bonus = round((valid_time_left / max_time) * 50)
    
    answer = models.PlayerAnswer(
        id=str(uuid.uuid4()),
        player_id=player.id,
        question_index=question_index,
        selected_option=selected_option,
        is_correct=is_correct,
        response_time_ms=time_spent_ms
    )
    db.add(answer)
    
    if is_correct:
        player.correct_answers += 1
        player.score += 100 + speed_bonus
    
    await db.commit()
    await db.refresh(answer)
    await db.refresh(player)
    return answer, player


async def finish_session(db: AsyncSession, session_id: str):
    try:
        session = await db.get(models.QuizSession, session_id)
        if not session:
            return None
        
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
        raise


async def get_leaderboard(db: AsyncSession, session_id: str):
    session = await get_session_with_players(db, session_id)
    if not session:
        return []
    
    host_player = session.players[0] if session.players else None
    players_to_rank = [
        p for p in session.players 
        if host_player is None or p.id != host_player.id
    ]
    
    sorted_players = sorted(players_to_rank, key=lambda p: (-p.score, p.nickname))
    
    return [
        {"rank": i + 1, "nickname": p.nickname, "score": p.score, "correct": p.correct_answers}
        for i, p in enumerate(sorted_players)
    ]


async def get_session_state_data(db: AsyncSession, session_id: str):
    session = await get_session_with_players(db, session_id)
    if not session:
        return None
    
    quiz = session.quiz
    return {
        "session_id": session.id,
        "quiz_id": session.quiz_id,
        "quiz_title": quiz.title if quiz else "Unknown",
        "status": session.status,
        "current_question": session.current_question if session.status == "active" else None,
        "total_questions": len(quiz.questions) if quiz and quiz.questions else 0,
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


# ========== РЕЗУЛЬТАТЫ ==========

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


# ========== АНАЛИТИКА ==========

async def get_quiz_analytics(db: AsyncSession, quiz_id: str):
    """Аналитика по квизу"""
    quiz = await db.get(models.Quiz, quiz_id)
    if not quiz:
        return None
    
    sessions_result = await db.execute(
        select(models.QuizSession.id).where(models.QuizSession.quiz_id == quiz_id)
    )
    session_ids = [row[0] for row in sessions_result.all()]
    
    if not session_ids:
        return {
            "quiz_id": quiz_id,
            "quiz_title": quiz.title,
            "total_players": 0,
            "total_attempts": 0,
            "avg_score": 0,
            "avg_completion_time": 0,
            "avg_response_time": 0,  # ✅ Добавлено
            "questions": [],
            "created_at": quiz.created_at
        }

    total_players = await db.scalar(
        select(func.count(models.Player.id.distinct())).where(
            models.Player.session_id.in_(session_ids)
        )
    ) or 0

    questions_stats = []
    total_answers_all = 0
    total_time_sum = 0
    total_time_count = 0

    for idx, question in enumerate(quiz.questions):
        counts = await db.execute(
            select(
                func.count(models.PlayerAnswer.id),
                func.sum(case((models.PlayerAnswer.is_correct == True, 1), else_=0))
            ).where(
                models.PlayerAnswer.question_index == idx,
                models.PlayerAnswer.player_id.in_(
                    select(models.Player.id).where(
                        models.Player.session_id.in_(session_ids)
                    )
                )
            )
        )
        result = counts.first()
        total_answers = result[0] or 0
        correct_count = result[1] or 0
        wrong_count = total_answers - correct_count
        
        total_answers_all += total_answers

        # Среднее время для этого вопроса
        avg_time_ms = await db.scalar(
            select(func.avg(models.PlayerAnswer.response_time_ms)).where(
                models.PlayerAnswer.question_index == idx,
                models.PlayerAnswer.player_id.in_(
                    select(models.Player.id).where(
                        models.Player.session_id.in_(session_ids)
                    )
                ),
                models.PlayerAnswer.response_time_ms.isnot(None)
            )
        )
        avg_response_time = round(avg_time_ms / 1000, 1) if avg_time_ms else None
        
        # ✅ Суммируем для общего среднего
        if avg_time_ms:
            total_time_sum += avg_time_ms
            total_time_count += 1

        option_dist = []
        most_wrong = None
        max_wrong = 0
        
        for opt_idx in range(4):
            wrong_count_opt = await db.scalar(
                select(func.count(models.PlayerAnswer.id)).where(
                    models.PlayerAnswer.question_index == idx,
                    models.PlayerAnswer.selected_option == opt_idx,
                    models.PlayerAnswer.is_correct == False,
                    models.PlayerAnswer.player_id.in_(
                        select(models.Player.id).where(
                            models.Player.session_id.in_(session_ids)
                        )
                    )
                )
            ) or 0
            option_dist.append(wrong_count_opt)
            
            if opt_idx != question.correct and wrong_count_opt > max_wrong:
                max_wrong = wrong_count_opt
                most_wrong = opt_idx

        accuracy_rate = round(correct_count / total_answers, 2) if total_answers > 0 else 0

        questions_stats.append({
            "question_index": idx,
            "question_text": question.text[:100] + "..." if len(question.text) > 100 else question.text,
            "total_answers": total_answers,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "accuracy_rate": accuracy_rate,
            "avg_response_time": avg_response_time,
            "option_distribution": option_dist,
            "most_chosen_wrong": most_wrong,
            "correct_option": question.correct
        })

    results_stats = await db.execute(
        select(func.avg(models.Result.score), func.avg(models.Result.time))
        .where(models.Result.quiz_id == quiz_id)
    )
    avg_score, avg_completion = results_stats.first()
    avg_score = round(avg_score or 0, 1)
    avg_completion = round(avg_completion or 0, 1)
    
    # ✅ Вычисляем общее среднее время ответа
    overall_avg_time = round((total_time_sum / total_time_count / 1000), 1) if total_time_count > 0 else 0

    return {
        "quiz_id": quiz_id,
        "quiz_title": quiz.title,
        "total_players": total_players,
        "total_attempts": total_answers_all,
        "avg_score": avg_score,
        "avg_completion_time": avg_completion,
        "avg_response_time": overall_avg_time,  # ✅ Возвращаем общее среднее время
        "questions": questions_stats,
        "created_at": quiz.created_at
    }