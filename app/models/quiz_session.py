from __future__ import annotations
from enum import Enum as PyEnum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    ForeignKey, String, Integer, JSON, 
    CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk

if TYPE_CHECKING:
    from .quiz import Quiz
    from .user import User
    from .session_participant import SessionParticipant
    from .answer_submission import AnswerSubmission


class SessionStatus(PyEnum):
    WAITING = "waiting"
    ACTIVE = "active"
    FINISHED = "finished"
    

class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting', 'active', 'finished')",
            name="check_quiz_session_status"
        ),
    )
    
    id: Mapped[int_pk]
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    pin_code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    
    status: Mapped[SessionStatus] = mapped_column(
        String(20),
        default=SessionStatus.WAITING,
        nullable=False
    )
    
    current_question_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    settings: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, server_default="{}", nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    quiz: Mapped[Quiz] = relationship(back_populates="sessions")
    host: Mapped[User] = relationship(back_populates="hosted_sessions")
    participants: Mapped[list[SessionParticipant]] = relationship(back_populates="session", lazy="selectin")
    submissions: Mapped[list[AnswerSubmission]] = relationship(back_populates="session", lazy="selectin")