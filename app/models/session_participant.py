from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from sqlalchemy import ForeignKey, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk

if TYPE_CHECKING:
    from .quiz_session import QuizSession
    from .user import User
    from .answer_submission import AnswerSubmission

class SessionParticipant(Base):
    __tablename__ = "session_participants"
    id: Mapped[int_pk]
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    current_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    session: Mapped[QuizSession] = relationship(back_populates="participants")
    user: Mapped[Optional[User]] = relationship()
    submissions: Mapped[list[AnswerSubmission]] = relationship(back_populates="participant", lazy="selectin")