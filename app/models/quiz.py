from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from sqlalchemy import ForeignKey, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk

if TYPE_CHECKING:
    from .user import User
    from .question import Question
    from .quiz_session import QuizSession

class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int_pk]
    creator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    creator: Mapped[Optional[User]] = relationship(back_populates="quizzes")
    questions: Mapped[list[Question]] = relationship(
        back_populates="quiz", 
        order_by="Question.order_index", 
        lazy="selectin"
    )
    sessions: Mapped[list[QuizSession]] = relationship(back_populates="quiz", lazy="selectin")