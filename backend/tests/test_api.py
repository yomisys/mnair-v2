"""
Tests for API endpoints (Module 5A)
Tests authentication, lessons, progress, quiz, and certificates APIs
"""

from __future__ import annotations
import pytest
from httpx import AsyncClient
from datetime import datetime
from unittest.mock import patch, Mock

from app.main import app
from app.models.user import User
from app.models.lesson import Lesson
from app.models.certificate import Certificate
from app.utils.auth import create_access_token


# ============================================================================
# Authentication API Tests
# ============================================================================


class TestAuthAPI:
    """Test authentication endpoints"""

    @pytest.mark.asyncio
    async def test_register_user_success(self, test_db):
        """Test successful user registration"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "phone_number": "+2348012345678",
                    "name": "Test User",
                    "language": "en",
                    "consent_given": True
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["phone_number"] == "+2348012345678"
            assert data["name"] == "Test User"
            assert data["language"] == "en"
            assert data["role"] == "learner"
            assert data["current_day"] == 1

    @pytest.mark.asyncio
    async def test_register_duplicate_phone(self, test_db):
        """Test registration with duplicate phone number"""
        # Create existing user
        user = User(
            phone_number="+2348012345678",
            name="Existing User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "phone_number": "+2348012345678",
                    "name": "New User",
                    "language": "en",
                    "consent_given": True
                }
            )

            assert response.status_code == 400
            assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_invalid_phone(self, test_db):
        """Test registration with invalid phone number"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "phone_number": "1234567890",  # Invalid
                    "name": "Test User",
                    "language": "en",
                    "consent_given": True
                }
            )

            assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_without_consent(self, test_db):
        """Test registration without data consent"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "phone_number": "+2348012345678",
                    "name": "Test User",
                    "language": "en",
                    "consent_given": False
                }
            )

            assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_login_learner_success(self, test_db):
        """Test successful login for learner (passwordless)"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "phone_number": "+2348012345678"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert data["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, test_db):
        """Test login with non-existent phone number"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "phone_number": "+2348099999999"
                }
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_current_user_profile(self, test_db):
        """Test getting current user profile"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == user.id
            assert data["phone_number"] == "+2348012345678"
            assert data["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_get_user_progress(self, test_db):
        """Test getting user progress summary"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me/progress",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == user.id
            assert data["current_day"] == 1
            assert data["total_lessons"] == 35
            assert data["lessons_completed"] == 0
            assert data["completion_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_update_user_language(self, test_db):
        """Test updating user's preferred language"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/auth/me/language?language=hausa",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["language"] == "hausa"

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, test_db):
        """Test accessing protected endpoint without token"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")

            assert response.status_code == 403  # HTTPBearer returns 403


# ============================================================================
# Lessons API Tests
# ============================================================================


class TestLessonsAPI:
    """Test lesson and quiz endpoints"""

    @pytest.mark.asyncio
    async def test_get_next_lesson(self, test_db):
        """Test getting next lesson for user"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=1
        )
        test_db.add(user)

        # Create lesson
        lesson = Lesson(
            lesson_id="day1_what_is_ai_en",
            topic="what_is_ai",
            day=1,
            language="en",
            title="What is AI?",
            content="AI is...",
            quiz=[{"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0}] * 5,
            estimated_duration_minutes=5,
            word_count=300
        )
        test_db.add(lesson)
        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/lessons/next",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["lesson"] is not None
            assert data["day_complete"] is False
            assert data["course_complete"] is False

    @pytest.mark.asyncio
    async def test_get_lesson_by_id(self, test_db):
        """Test getting specific lesson by ID"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=1
        )
        test_db.add(user)

        # Create lesson
        lesson = Lesson(
            lesson_id="day1_what_is_ai_en",
            topic="what_is_ai",
            day=1,
            language="en",
            title="What is AI?",
            content="AI is...",
            quiz=[{"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0}] * 5,
            estimated_duration_minutes=5,
            word_count=300
        )
        test_db.add(lesson)
        await test_db.commit()
        await test_db.refresh(user)
        await test_db.refresh(lesson)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/lessons/{lesson.id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == lesson.id
            assert data["title"] == "What is AI?"
            assert len(data["quiz"]) == 5

    @pytest.mark.asyncio
    async def test_get_lessons_by_day(self, test_db):
        """Test getting all lessons for a specific day"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=1
        )
        test_db.add(user)

        # Create multiple lessons for day 1
        topics = ["what_is_ai", "how_ai_works", "ai_in_nigeria"]
        for topic in topics:
            lesson = Lesson(
                lesson_id=f"day1_{topic}_en",
                topic=topic,
                day=1,
                language="en",
                title=f"Lesson: {topic}",
                content=f"Content for {topic}",
                quiz=[{"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0}] * 5,
                estimated_duration_minutes=5,
                word_count=300
            )
            test_db.add(lesson)

        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/lessons/day/1",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert all(lesson["day"] == 1 for lesson in data)

    @pytest.mark.asyncio
    async def test_submit_quiz_success(self, test_db):
        """Test successful quiz submission"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=1
        )
        test_db.add(user)

        # Create lesson with quiz
        lesson = Lesson(
            lesson_id="day1_what_is_ai_en",
            topic="what_is_ai",
            day=1,
            language="en",
            title="What is AI?",
            content="AI is...",
            quiz=[
                {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0},
                {"question": "Q2", "options": ["A", "B", "C", "D"], "correct": 1},
                {"question": "Q3", "options": ["A", "B", "C", "D"], "correct": 2},
                {"question": "Q4", "options": ["A", "B", "C", "D"], "correct": 3},
                {"question": "Q5", "options": ["A", "B", "C", "D"], "correct": 0},
            ],
            estimated_duration_minutes=5,
            word_count=300
        )
        test_db.add(lesson)
        await test_db.commit()
        await test_db.refresh(user)
        await test_db.refresh(lesson)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lessons/quiz/submit",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "lesson_id": lesson.id,
                    "user_answers": [0, 1, 2, 3, 0]  # All correct
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["score"] == 100.0
            assert data["correct_count"] == 5
            assert data["passed"] is True
            assert data["lesson_completed"] is True


# ============================================================================
# Certificates API Tests
# ============================================================================


class TestCertificatesAPI:
    """Test certificate endpoints"""

    @pytest.mark.asyncio
    async def test_generate_certificate_course_not_complete(self, test_db):
        """Test certificate generation when course not complete"""
        # Create user who hasn't completed course
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=3  # Not finished
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/certificates/generate",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 400
            assert "not complete" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_my_certificate_not_found(self, test_db):
        """Test getting certificate when none exists"""
        # Create user
        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=7
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)

        # Create token
        token = create_access_token(data={"sub": str(user.id)})

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/certificates/me",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_verify_certificate_not_found(self, test_db):
        """Test verifying non-existent certificate (public endpoint)"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/certificates/verify/MNAIR-2024-999-INVALID"
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
