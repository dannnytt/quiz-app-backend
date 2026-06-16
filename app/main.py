from contextlib import asynccontextmanager
import os
import shutil
import uuid

from fastapi import FastAPI, Depends, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
import re

from .database import engine, Base, get_db, async_session_maker
from .seed import seed_default_quizzes
from . import crud, schemas, schemas_auth
from .auth import (
    verify_password, create_access_token, 
    get_current_user, require_user
)
from . import models


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # Создаём все таблицы (включая users)
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session_maker() as session:
        inserted = await seed_default_quizzes(session)
        if inserted:
            print("Default quizzes seeded successfully!")
        else:
            print("Database already contains quizzes. Skipping seed.")
    
    yield
    await engine.dispose()


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="QuizMaster API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        re.compile(r"http://192\.168\.\d+\.\d+:\d+"),
        re.compile(r"http://10\.\d+\.\d+\.\d+:\d+"),
        re.compile(r"https://.*\.tuna\.am"),
        re.compile(r"https://.*\.trycloudflare\.com"),
        re.compile(r"https://.*\.devtunnels\.ms"),
        re.compile(r"https://.*\.ngrok-free\.app"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# АУТЕНТИФИКАЦИЯ
@app.post("/api/auth/register", response_model=schemas_auth.TokenResponse)
async def register(data: schemas_auth.UserRegister, db: AsyncSession = Depends(get_db)):
    """Регистрация нового пользователя"""
    # Проверяем, не занят ли email
    existing = await crud.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    
    user = await crud.create_user(db, data)
    token = create_access_token(user.id)
    
    return schemas_auth.TokenResponse(
        access_token=token,
        user=schemas_auth.UserOut.model_validate(user)
    )


@app.post("/api/auth/login", response_model=schemas_auth.TokenResponse)
async def login(data: schemas_auth.UserLogin, db: AsyncSession = Depends(get_db)):
    """Вход в систему"""
    user = await crud.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    
    token = create_access_token(user.id)
    return schemas_auth.TokenResponse(
        access_token=token,
        user=schemas_auth.UserOut.model_validate(user)
    )


@app.get("/api/auth/me", response_model=schemas_auth.UserOut)
async def get_me(user: models.User = Depends(require_user)):
    """Получить информацию о текущем пользователе"""
    return user


@app.get("/api/auth/verify")
async def verify_token(user: models.User = Depends(require_user)):
    """Проверка валидности токена"""
    return {"status": "ok", "user_id": user.id}


# КВИЗЫ
@app.get("/api/quizzes")
async def read_quizzes(db: AsyncSession = Depends(get_db)):
    """Получить все квизы (публично)"""
    return await crud.get_quizzes(db)


@app.get("/api/quizzes/my")
async def read_my_quizzes(
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_user)
):
    """Получить свои квизы"""
    return await crud.get_user_quizzes(db, user.id)


@app.post("/api/quizzes")
async def create_quiz(
    data: schemas.QuizCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_user)
):
    """Создать квиз (только авторизованные)"""
    quiz = await crud.create_quiz(db, data, user.id)
    # Возвращаем в том же формате, что и get_quizzes
    return {
        "id": quiz.id,
        "title": quiz.title,
        "desc": quiz.desc,
        "difficulty": quiz.difficulty,
        "time_per_question": quiz.time_per_question,
        "is_custom": quiz.is_custom,
        "created_at": quiz.created_at,
        "cover_image": quiz.cover_image,
        "owner_id": quiz.owner_id,
        "owner_nickname": user.nickname,
        "questions": quiz.questions,
    }


@app.put("/api/quizzes/{quiz_id}")
async def update_quiz(
    quiz_id: str,
    data: schemas.QuizCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_user)
):
    """Обновить квиз (только владелец)"""
    try:
        quiz = await crud.update_quiz(db, quiz_id, data, user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    
    return {
        "id": quiz.id,
        "title": quiz.title,
        "desc": quiz.desc,
        "difficulty": quiz.difficulty,
        "time_per_question": quiz.time_per_question,
        "is_custom": quiz.is_custom,
        "created_at": quiz.created_at,
        "cover_image": quiz.cover_image,
        "owner_id": quiz.owner_id,
        "owner_nickname": user.nickname,
        "questions": quiz.questions,
    }


@app.delete("/api/quizzes/{quiz_id}")
async def delete_quiz(
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_user)
):
    """Удалить квиз (только владелец)"""
    try:
        deleted = await crud.delete_quiz(db, quiz_id, user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    if not deleted:
        raise HTTPException(404, "Quiz not found")
    return {"detail": "Deleted"}


# ЗАГРУЗКА ИЗОБРАЖЕНИЙ
@app.post("/api/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    user: models.User = Depends(require_user)  # Только авторизованные
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")
    
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {"url": f"/uploads/{unique_filename}"}


# СЕССИИ (мультиплеер) — публичные
@app.post("/api/sessions", response_model=schemas.SessionOut)
async def create_session(data: schemas.SessionCreate, db: AsyncSession = Depends(get_db)):
    try:
        session = await crud.create_session(db, data.quiz_id)
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/sessions/join", response_model=dict)
async def join_session(data: schemas.SessionJoin, db: AsyncSession = Depends(get_db)):
    session = await crud.get_session_by_code(db, data.host_code)
    if not session or session.status != "waiting":
        raise HTTPException(status_code=404, detail="Session not found or closed")
    
    player, session = await crud.join_session(db, session.id, data.nickname)
    if not player:
        raise HTTPException(status_code=400, detail="Invalid nickname")
    
    return {
        "session_id": session.id,
        "player_token": player.player_token,
        "nickname": player.nickname,
        "quiz_id": session.quiz_id,
    }


@app.get("/api/sessions/{session_id}", response_model=schemas.SessionStateOut)
async def get_session_state(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        data = await crud.get_session_state_data(db, session_id)
        if not data:
            raise HTTPException(status_code=404, detail="Session not found")
        return data
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Session state error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/api/sessions/{session_id}/start")
async def start_session_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await crud.start_session(db, session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot start session")
    return {"status": "started", "session_id": session_id}


@app.post("/api/sessions/{session_id}/next")
async def next_question_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await crud.next_question(db, session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot advance question")
    return {"status": session.status, "current_question": session.current_question}


@app.post("/api/sessions/{session_id}/answers", response_model=schemas.AnswerResult)
async def submit_answer_endpoint(
    session_id: str,
    data: schemas.AnswerSubmit,
    db: AsyncSession = Depends(get_db),
):
    result = await crud.submit_answer(
        db, data.player_token, data.question_index,
        data.selected_option, data.time_left,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Invalid answer submission")
    
    answer, player = result
    session = await crud.get_session_with_players(db, player.session_id)
    explanation = None
    if session and session.quiz:
        q = session.quiz.questions[data.question_index]
        explanation = q.explanation
    
    return {
        "correct": answer.is_correct,
        "explanation": explanation,
        "score": player.score,
        "correct_answers": player.correct_answers,
    }


@app.post("/api/sessions/{session_id}/finish")
async def finish_session_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await crud.finish_session(db, session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot finish session")
    return {"status": "finished", "session_id": session_id}


@app.get("/api/sessions/{session_id}/leaderboard", response_model=schemas.LeaderboardOut)
async def get_leaderboard_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await crud.get_session_with_players(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    leaderboard = await crud.get_leaderboard(db, session_id)
    return {
        "session_id": session_id,
        "status": session.status,
        "leaderboard": [schemas.LeaderboardEntry(**entry) for entry in leaderboard],
    }


@app.get("/api/sessions/{session_id}/players")
async def get_session_players(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await crud.get_session_with_players(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "players": [
            {"nickname": p.nickname, "score": p.score, "finished": p.finished}
            for p in session.players
        ],
        "count": len(session.players),
    }


# РЕЗУЛЬТАТЫ И АНАЛИТИКА
@app.post("/api/results", response_model=schemas.ResultOut)
async def save_result(data: schemas.ResultCreate, db: AsyncSession = Depends(get_db)):
    """Сохранение результата — публично"""
    return await crud.save_result(db, data)


@app.get("/api/quizzes/{quiz_id}/analytics", response_model=schemas.QuizAnalytics)
async def get_quiz_analytics_endpoint(
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_user)  # Только авторизованные
):
    """Аналитика — только владелец квиза"""
    # Проверяем, что квиз принадлежит пользователю
    quiz = await db.get(models.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    if quiz.owner_id and quiz.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Вы не являетесь владельцем этого квиза")
    
    analytics = await crud.get_quiz_analytics(db, quiz_id)
    if not analytics:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return analytics