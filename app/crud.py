# backend/app/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from . import models, schemas
import uuid

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