"""
Analytics schemas for API responses
"""

from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import date, datetime


class AnalyticsResponse(BaseModel):
    """Schema for daily analytics snapshot"""

    id: int
    date: date

    # User Metrics
    total_users: int
    new_users_today: int
    active_users_today: int
    active_users_7d: int
    active_users_30d: int

    # Completion Metrics
    users_in_progress: int
    users_completed_program: int
    completions_today: int
    completion_rate: float

    # Lesson Metrics
    total_lessons_completed: int
    lessons_completed_today: int
    average_lessons_per_user: float

    # Quiz Performance
    total_quiz_attempts: int
    quiz_attempts_today: int
    average_quiz_score: float
    quiz_pass_rate: float

    # Distributions
    channel_distribution: Dict[str, int]
    language_distribution: Dict[str, int]
    day_distribution: Dict[str, int]
    network_distribution: Dict[str, int]

    # Certificate Metrics
    certificates_issued: int
    certificates_issued_today: int
    certificates_verified_today: int

    # Employer Metrics
    total_employers: int
    new_employers_today: int

    # Top Lessons
    top_lessons: List[Dict[str, int]]

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnalyticsSummary(BaseModel):
    """Schema for summary analytics (quick overview)"""

    total_users: int
    active_users_7d: int
    users_completed_program: int
    completion_rate: float
    average_quiz_score: float
    certificates_issued: int
    total_employers: int

    # Calculated properties
    user_retention_rate: float = Field(..., description="7-day retention rate (%)")
    daily_active_rate: float = Field(..., description="DAU/MAU ratio (%)")


class LanguageStats(BaseModel):
    """Schema for language distribution statistics"""

    language: str
    user_count: int
    percentage: float
    average_completion_rate: Optional[float] = None


class DayStats(BaseModel):
    """Schema for day distribution statistics"""

    day: int
    user_count: int
    percentage: float


class NetworkStats(BaseModel):
    """Schema for network operator statistics"""

    network: str
    user_count: int
    percentage: float


class TrendData(BaseModel):
    """Schema for trend data over time"""

    date: date
    value: float
    label: str


class DashboardOverview(BaseModel):
    """Schema for complete dashboard overview"""

    summary: AnalyticsSummary
    language_distribution: List[LanguageStats]
    day_distribution: List[DayStats]
    network_distribution: List[NetworkStats]
    user_growth_trend: List[TrendData]
    completion_trend: List[TrendData]
    last_updated: datetime
