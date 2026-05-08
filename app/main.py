from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base, get_db, async_session_maker
from .seed import seed_default_quizzes
from . import crud, schemas
from sqlalchemy.ext.asyncio import AsyncSession

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Создаём таблицы, если их нет
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Сидим дефолтные данные
    async with async_session_maker() as session:
        inserted = await seed_default_quizzes(session)
        if inserted:
            print("✅ Default quizzes seeded successfully!")
        else:
            print("ℹ️  Database already contains quizzes. Skipping seed.")
    
    yield  # Сервер запущен

    # Очистка при выключении (опционально)
    await engine.dispose()

app = FastAPI(title="QuizMaster API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

@app.get("/api/quizzes", response_model=list[schemas.QuizOut])
async def read_quizzes(db: AsyncSession = Depends(get_db)):
    return await crud.get_quizzes(db)

@app.post("/api/quizzes", response_model=schemas.QuizOut)
async def create_quiz(data: schemas.QuizCreate, db: AsyncSession = Depends(get_db)):
    return await crud.create_quiz(db, data)

@app.put("/api/quizzes/{quiz_id}", response_model=schemas.QuizOut)
async def update_quiz(quiz_id: str, data: schemas.QuizCreate, db: AsyncSession = Depends(get_db)):
    updated = await crud.update_quiz(db, quiz_id, data)
    if not updated: raise HTTPException(404, "Quiz not found")
    return updated

@app.delete("/api/quizzes/{quiz_id}")
async def delete_quiz(quiz_id: str, db: AsyncSession = Depends(get_db)):
    if not await crud.delete_quiz(db, quiz_id): raise HTTPException(404)
    return {"detail": "Deleted"}

@app.post("/api/results", response_model=schemas.ResultOut)
async def save_result(data: schemas.ResultCreate, db: AsyncSession = Depends(get_db)):
    return await crud.save_result(db, data)

@app.get("/api/results", response_model=list[schemas.ResultOut])
async def get_results(db: AsyncSession = Depends(get_db)):
    return await crud.get_results(db)

@app.delete("/api/results")
async def clear_results(db: AsyncSession = Depends(get_db)):
    await crud.clear_results(db)
    return {"detail": "Cleared"}