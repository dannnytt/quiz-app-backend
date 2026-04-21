from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from sqlalchemy import ForeignKey, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base, int_pk

if TYPE_CHECKING:
    from .quiz_session import QuizSession
    from .session_participant import SessionParticipant
    from .question import Question
    from .answer_option import AnswerOption

class AnswerSubmission(Base):
    __tablename__ = "answer_submissions"
    id: Mapped[int_pk]
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("session_participants.id"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    selected_option_id: Mapped[Optional[int]] = mapped_column(ForeignKey("answer_options.id"), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    points_earned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    session: Mapped[QuizSession] = relationship(back_populates="submissions")
    participant: Mapped[SessionParticipant] = relationship(back_populates="submissions")
    question: Mapped[Question] = relationship()
    selected_option: Mapped[Optional[AnswerOption]] = relationship()