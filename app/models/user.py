from __future__ import annotations
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk, str_uniq

if TYPE_CHECKING:
    from .quiz import Quiz
    from .quiz_session import QuizSession

class User(Base):
    __tablename__ = "users"
    id: Mapped[int_pk]
    username: Mapped[str_uniq]
    email: Mapped[str_uniq]
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    quizzes: Mapped[list[Quiz]] = relationship(back_populates="creator", lazy="selectin")
    hosted_sessions: Mapped[list[QuizSession]] = relationship(back_populates="host", lazy="selectin")