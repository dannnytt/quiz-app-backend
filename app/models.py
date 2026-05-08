import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base

class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(100), nullable=False)
    desc = Column(String(200))
    emoji = Column(String(10))
    difficulty = Column(String(20), default="medium")
    time_per_question = Column(Integer, default=30)
    is_custom = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")

class Question(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, ForeignKey("quizzes.id", ondelete="CASCADE"))
    text = Column(String(300), nullable=False)
    options = Column(JSON, nullable=False)  # ["A", "B", "C", "D"]
    correct = Column(Integer, nullable=False)
    explanation = Column(String(500), nullable=True)
    quiz = relationship("Quiz", back_populates="questions")

class Result(Base):
    __tablename__ = "results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, nullable=False)
    quiz_name = Column(String(100))
    emoji = Column(String(10))
    correct = Column(Integer)
    total = Column(Integer)
    score = Column(Integer)
    time = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())