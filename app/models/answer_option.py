from __future__ import annotations
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk

if TYPE_CHECKING:
    from .question import Question

class AnswerOption(Base):
    __tablename__ = "answer_options"
    id: Mapped[int_pk]
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    answer_text: Mapped[str] = mapped_column(String(255), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped[Question] = relationship(back_populates="answer_options")