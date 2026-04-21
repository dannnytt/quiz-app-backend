from __future__ import annotations
from enum import Enum as PyEnum
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Text, Integer, UniqueConstraint, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk

if TYPE_CHECKING:
    from .quiz import Quiz
    from .answer_option import AnswerOption

class QuestionType(PyEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"

class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("quiz_id", "order_index", name="uq_quiz_question_order"),
        CheckConstraint(
            "type IN ('multiple_choice', 'true_false')",
            name="check_question_type"
        )
    )
    id: Mapped[int_pk]
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[QuestionType] = mapped_column(
        String(20),
        default=QuestionType.MULTIPLE_CHOICE,
        nullable=False
    )
    time_limit_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    points_base: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    answer_options: Mapped[list[AnswerOption]] = relationship(
        back_populates="question",
        order_by="AnswerOption.order_index",
        lazy="selectin"
    )