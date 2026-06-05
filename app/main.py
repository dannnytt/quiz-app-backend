from contextlib import asynccontextmanager
import os
import shutil
import uuid

from fastapi import FastAPI, Depends, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine, Base, get_db, async_session_maker
from .seed import seed_default_quizzes
from . import crud, schemas
from .auth import get_admin_token  # ✅ ИМПОРТ ПРОВЕРКИ АДМИНА
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ============================================================
# ✅ ПУБЛИЧНЫЕ ЭНДПОИНТЫ (доступны всем пользователям)
# ============================================================

@app.post("/api/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """Загрузка изображения — публичный доступ"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")
    
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {"url": f"/uploads/{unique_filename}"}


@app.get("/api/quizzes", response_model=list[schemas.QuizOut])
async def read_quizzes(db: AsyncSession = Depends(get_db)):
    """Получение списка квизов — публичный доступ"""
    return await crud.get_quizzes(db)


# --- Сессии (мультиплеер) ---

@app.post("/api/sessions", response_model=schemas.SessionOut)
async def create_session(data: schemas.SessionCreate, db: AsyncSession = Depends(get_db)):
    """Создание сессии — публичный доступ"""
    try:
        session = await crud.create_session(db, data.quiz_id)
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/sessions/join", response_model=dict)
async def join_session(data: schemas.SessionJoin, db: AsyncSession = Depends(get_db)):
    """Присоединение игрока к сессии — публичный доступ"""
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
    """Получение состояния сессии — публичный доступ"""
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
    """Запуск сессии — публичный доступ"""
    session = await crud.start_session(db, session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot start session")
    return {"status": "started", "session_id": session_id}


@app.post("/api/sessions/{session_id}/next")
async def next_question_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    """Переход к следующему вопросу — публичный доступ"""
    session = await crud.next_question(db, session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot advance question")
    return {
        "status": session.status,
        "current_question": session.current_question,
    }


@app.post("/api/sessions/{session_id}/answers", response_model=schemas.AnswerResult)
async def submit_answer_endpoint(
    session_id: str,
    data: schemas.AnswerSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Отправка ответа игрока — публичный доступ"""
    result = await crud.submit_answer(
        db,
        data.player_token,
        data.question_index,
        data.selected_option,
        data.time_left,
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
    """Завершение сессии — публичный доступ"""
    session = await crud.finish_session(db, session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Cannot finish session")
    return {"status": "finished", "session_id": session_id}


@app.get("/api/sessions/{session_id}/leaderboard", response_model=schemas.LeaderboardOut)
async def get_leaderboard_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    """Получение таблицы лидеров — публичный доступ"""
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
    """Получение списка игроков — публичный доступ"""
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


# ============================================================
# 🔒 АДМИНСКИЕ ЭНДПОИНТЫ (требуют Bearer-токен администратора)
# ============================================================

@app.post("/api/quizzes", response_model=schemas.QuizOut)
async def create_quiz(
    data: schemas.QuizCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_token),  # 🔒 ЗАЩИТА
):
    """Создание квиза — только для админа"""
    return await crud.create_quiz(db, data)


@app.put("/api/quizzes/{quiz_id}", response_model=schemas.QuizOut)
async def update_quiz(
    quiz_id: str,
    data: schemas.QuizCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_token),  # 🔒 ЗАЩИТА
):
    """Обновление квиза — только для админа"""
    updated = await crud.update_quiz(db, quiz_id, data)
    if not updated:
        raise HTTPException(404, "Quiz not found")
    return updated


@app.delete("/api/quizzes/{quiz_id}")
async def delete_quiz(
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_token),  # 🔒 ЗАЩИТА
):
    """Удаление квиза — только для админа"""
    if not await crud.delete_quiz(db, quiz_id):
        raise HTTPException(404, "Quiz not found")
    return {"detail": "Deleted"}


@app.post("/api/results", response_model=schemas.ResultOut)
async def save_result(
    data: schemas.ResultCreate,
    db: AsyncSession = Depends(get_db),
    # _admin: str = Depends(get_admin_token),  # 🔒 ЗАЩИТА
):
    """Сохранение результата — только для админа"""
    return await crud.save_result(db, data)


@app.get("/api/quizzes/{quiz_id}/analytics", response_model=schemas.QuizAnalytics)
async def get_quiz_analytics_endpoint(
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_token),  # 🔒 ЗАЩИТА
):
    """Аналитика по квизу — только для админа"""
    analytics = await crud.get_quiz_analytics(db, quiz_id)
    if not analytics:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return analytics