from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

class QuestionBase(BaseModel):
    text: str = Field(..., max_length=300)
    options: List[str]
    correct: int
    explanation: Optional[str] = Field(None, max_length=500)

class QuestionOut(QuestionBase):
    id: str
    quiz_id: str
    model_config = ConfigDict(from_attributes=True)

class QuizCreate(BaseModel):
    title: str = Field(..., max_length=100)
    desc: Optional[str] = Field(None, max_length=200)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    time_per_question: int = Field(default=30, ge=10, le=120)
    questions: List[QuestionBase]

class QuizOut(QuizCreate):
    id: str
    is_custom: bool
    created_at: datetime
    questions: List[QuestionOut]
    model_config = ConfigDict(from_attributes=True)

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

class SessionCreate(BaseModel):
    quiz_id: str

class SessionJoin(BaseModel):
    host_code: str
    nickname: str = Field(..., min_length=2, max_length=50)

class SessionOut(BaseModel):
    id: str
    quiz_id: str
    host_code: str
    status: str
    current_question: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class PlayerOut(BaseModel):
    id: str
    nickname: str
    score: int
    correct_answers: int
    finished: bool
    model_config = ConfigDict(from_attributes=True)

class SessionStateOut(BaseModel):
    session_id: str
    quiz_id: str
    quiz_title: str
    status: str
    current_question: Optional[int] = None
    total_questions: int
    host_code: Optional[str] = None
    players: List[PlayerOut]
    model_config = ConfigDict(from_attributes=True)

class AnswerSubmit(BaseModel):
    player_token: str
    question_index: int
    selected_option: int
    time_left: int = Field(..., ge=0, le=300)

class AnswerResult(BaseModel):
    correct: bool
    explanation: Optional[str] = None
    score: int
    correct_answers: int

class LeaderboardEntry(BaseModel):
    rank: int
    nickname: str
    score: int
    correct: int

class LeaderboardOut(BaseModel):
    session_id: str
    status: str
    leaderboard: List[LeaderboardEntry]

class QuestionStats(BaseModel):
    question_index: int
    question_text: str
    total_answers: int
    correct_count: int
    wrong_count: int
    accuracy_rate: float
    avg_response_time: Optional[float]
    option_distribution: List[int]
    most_chosen_wrong: Optional[int]

class QuizAnalytics(BaseModel):
    quiz_id: str
    quiz_title: str
    total_players: int
    total_attempts: int
    avg_score: float
    avg_completion_time: float
    questions: List[QuestionStats]
    created_at: datetime
    
    class Config:
        from_attributes = True