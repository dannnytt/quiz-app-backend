# app/models.py
import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base

class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(100), nullable=False)
    desc = Column(String(200))
    difficulty = Column(String(20), default="medium")
    time_per_question = Column(Integer, default=30)
    is_custom = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    questions = relationship(
        "Question", 
        back_populates="quiz", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    sessions = relationship(
        "QuizSession", 
        back_populates="quiz", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class Question(Base):
    __tablename__ = "questions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    text = Column(String(300), nullable=False)
    options = Column(JSON, nullable=False)
    correct = Column(Integer, nullable=False)
    explanation = Column(String(500), nullable=True)
    
    quiz = relationship("Quiz", back_populates="questions")


class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    host_code = Column(String(6), unique=True, nullable=False, index=True)
    status = Column(String(20), default="waiting")  # waiting, active, finished
    current_question = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    quiz = relationship("Quiz", back_populates="sessions")
    players = relationship(
        "Player", 
        back_populates="session", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class Player(Base):
    __tablename__ = "players"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("quiz_sessions.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String(50), nullable=False)
    player_token = Column(String(64), unique=True, nullable=False, index=True)
    score = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    finished = Column(Boolean, default=False)
    
    session = relationship("QuizSession", back_populates="players")
    answers = relationship(
        "PlayerAnswer", 
        back_populates="player", 
        cascade="all, delete-orphan"
    )


class PlayerAnswer(Base):
    __tablename__ = "player_answers"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    question_index = Column(Integer, nullable=False)
    selected_option = Column(Integer, nullable=True)
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime(timezone=True), server_default=func.now())
    response_time_ms = Column(Integer, nullable=True)
    player = relationship("Player", back_populates="answers")


class Result(Base):
    __tablename__ = "results"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, nullable=False)
    quiz_name = Column(String(100))
    correct = Column(Integer)
    total = Column(Integer)
    score = Column(Integer)
    time = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())