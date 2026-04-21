## Сущность "Пользователь" (users)
- id: uuid/serial pk
- username: varchar unique
- email: varchar unique
- password_hash: varchar

---

## Сущность "Квиз" (quizzes)
- id: uuid/serial pk
- creator_id: fk -> users, nullable
- title: varchar
- description: text
- is_published: bool

---

## Сущность "Вопрос" (questions)
- id: uuid/serial pk
- quiz_id: fk -> quizzes
- text: text 
- type: varchar/enum
- time_limit_sec: int
- points_base: int
- order_index: int

question_type: multiple_choice,true_false

---

## Сущность "Вариант ответа" (answer_options)
- id: uuid/serial pk
- question_id: fk -> questions
- answer_text: text
- is_correct: bool
- order_index: int

---

## Сущность "Сессия квиза" (quiz_sessions)
- id: uuid/serial pk
- quiz_id: fk -> quizzes
- host_id: fk -> users
- pin_code: varchar(6) unique
- status: varchar/enum
- current_question_index: int
- settings: JSONB
- started_at: timestamp
- finished_at timestamp
- created_at: timestamp

status: waiting, active, finished

---

## Сущность "Участник сессии" (session_participants)
- id: uuid/serial pk
- session_id: fk -> quiz_sessions
- user_id: fk -> users, nullable
- nickname: varchar, not null
- total_score: int
- current_streak

## answer_submissions
- id: uuid/serial pk
- session_id: fk -> quiz_sessions
- participant_id: fk -> session_participants
- question_id: fk -> questions
- selected_answer_id: fk -> answer_options
- is_correct: bool
- points_earned: int