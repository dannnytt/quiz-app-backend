# backend/app/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

# === QUESTION ===
class QuestionBase(BaseModel):
    text: str = Field(..., max_length=300)      # ✅ text вместо q
    options: List[str]
    correct: int
    explanation: Optional[str] = Field(None, max_length=500)

class QuestionOut(QuestionBase):
    id: str
    quiz_id: str
    model_config = ConfigDict(from_attributes=True)

# === QUIZ ===
class QuizCreate(BaseModel):
    title: str = Field(..., max_length=100)
    desc: Optional[str] = Field(None, max_length=200)
    emoji: str = Field(default="📝", max_length=10)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    time_per_question: int = Field(default=30, ge=10, le=120)
    questions: List[QuestionBase]

class QuizOut(QuizCreate):
    id: str
    is_custom: bool
    created_at: datetime
    questions: List[QuestionOut]  # ✅ Вложенная схема
    model_config = ConfigDict(from_attributes=True)

# === RESULT ===
class ResultCreate(BaseModel):
    quiz_id: str
    quiz_name: str
    emoji: str
    correct: int
    total: int
    score: int
    time: int

class ResultOut(ResultCreate):
    id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)