"""
Lesson and quiz schemas for API requests and responses
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class QuizQuestionResponse(BaseModel):
    """Schema for quiz question in lesson response"""

    question: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    # Note: We don't include 'correct' in API response for security


class LessonResponse(BaseModel):
    """Schema for lesson data in API responses"""

    id: int
    topic: str
    day: int
    language: str
    title: str
    content: str
    quiz: List[QuizQuestionResponse]
    reading_time_minutes: int
    word_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class LessonProgressResponse(BaseModel):
    """Schema for lesson progress data"""

    id: int
    user_id: int
    lesson_id: int
    is_completed: bool
    completion_date: Optional[datetime] = None
    attempts_count: int
    best_score: Optional[float] = None
    last_attempt_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuizSubmission(BaseModel):
    """Schema for quiz answer submission"""

    lesson_id: int = Field(..., description="Lesson ID for the quiz")
    user_answers: List[int] = Field(
        ...,
        min_length=5,
        max_length=5,
        description="List of 5 answer indices (0-3)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "lesson_id": 1,
                "user_answers": [0, 2, 1, 3, 0]
            }
        }


class QuizResult(BaseModel):
    """Schema for quiz result response"""

    lesson_id: int
    score: float = Field(..., description="Quiz score (0-100)")
    correct_count: int = Field(..., description="Number of correct answers")
    total_questions: int = Field(default=5)
    passed: bool = Field(..., description="Whether quiz was passed (>= 60%)")
    attempts_used: int = Field(..., description="Number of attempts used")
    attempts_remaining: int = Field(..., description="Remaining attempts (max 3)")
    lesson_completed: bool = Field(..., description="Whether lesson is now complete")
    feedback: str = Field(..., description="Feedback message")

    class Config:
        json_schema_extra = {
            "example": {
                "lesson_id": 1,
                "score": 80.0,
                "correct_count": 4,
                "total_questions": 5,
                "passed": True,
                "attempts_used": 1,
                "attempts_remaining": 2,
                "lesson_completed": True,
                "feedback": "Excellent! You passed the quiz."
            }
        }


class DayProgressResponse(BaseModel):
    """Schema for daily progress summary"""

    day: int
    lessons_completed: int
    total_lessons: int = Field(default=5)
    average_score: Optional[float] = None
    is_complete: bool = Field(..., description="Whether all 5 topics completed")
    completion_date: Optional[datetime] = None


class UserProgressDetail(BaseModel):
    """Schema for detailed user progress"""

    user: Dict[str, Any]
    current_day: int
    total_days: int = Field(default=7)
    overall_completion_percentage: float
    lessons_completed: int
    total_lessons: int = Field(default=35)
    average_quiz_score: Optional[float] = None
    days_progress: List[DayProgressResponse]
    next_lesson: Optional[LessonResponse] = None
    can_advance_to_next_day: bool


class NextLessonResponse(BaseModel):
    """Schema for next lesson recommendation"""

    lesson: Optional[LessonResponse] = None
    day_complete: bool = Field(..., description="Whether current day is complete")
    course_complete: bool = Field(..., description="Whether entire course is complete")
    message: str = Field(..., description="Status message for the user")
