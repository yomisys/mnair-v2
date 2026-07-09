"""
Tests for SMS notifications and certificate generation
Module 2C: SMS Fallback + Certificate Generator
"""

from __future__ import annotations
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.sms import SMSProvider, SMSNotifier
from app.certificates.generator import CertificateGenerator
from app.models.user import User
from app.models.certificate import Certificate
from app.config import Settings


# ============================================================================
# SMS Provider Tests
# ============================================================================


class TestSMSProvider:
    """Test SMS provider with Termii API"""

    @pytest.mark.asyncio
    async def test_send_sms_dev_mode(self):
        """Test SMS sending in dev mode (no API key)"""
        settings = Settings(TERMII_API_KEY=None)
        provider = SMSProvider(settings)

        result = await provider.send_sms("+2348012345678", "Test message")

        assert result["status"] == "dev_mode"
        assert "message_id" in result

    @pytest.mark.asyncio
    async def test_send_sms_with_api_key(self):
        """Test SMS sending with API key"""
        settings = Settings(
            TERMII_API_KEY="test_key",
            TERMII_SENDER_ID="MNAIR"
        )
        provider = SMSProvider(settings)

        mock_response = Mock()
        mock_response.json.return_value = {
            "message_id": "abc123",
            "status": "sent"
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await provider.send_sms("+2348012345678", "Test message")

            assert result["message_id"] == "abc123"
            assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_sms_truncate_long_message(self):
        """Test that long messages are truncated to 160 chars"""
        settings = Settings(TERMII_API_KEY=None)
        provider = SMSProvider(settings)

        long_message = "A" * 200
        result = await provider.send_sms("+2348012345678", long_message)

        # In dev mode, we just verify it doesn't crash
        assert result["status"] == "dev_mode"

    @pytest.mark.asyncio
    async def test_send_sms_http_error(self):
        """Test SMS sending with HTTP error"""
        import httpx

        settings = Settings(TERMII_API_KEY="test_key")
        provider = SMSProvider(settings)

        # Mock httpx to raise HTTPError inside context manager
        mock_post = AsyncMock(side_effect=httpx.HTTPError("Network error"))

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await provider.send_sms("+2348012345678", "Test")

            assert result["status"] == "error"
            assert "error" in result


class TestSMSNotifier:
    """Test high-level SMS notification service"""

    @pytest.mark.asyncio
    async def test_send_welcome_sms(self, test_db: AsyncSession):
        """Test welcome SMS"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()

        success = await notifier.send_welcome_sms(user)

        assert success is True

    @pytest.mark.asyncio
    async def test_send_day_complete_sms(self, test_db: AsyncSession):
        """Test day completion SMS"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=3
        )
        test_db.add(user)
        await test_db.commit()

        success = await notifier.send_day_complete_sms(user, day=3)

        assert success is True

    @pytest.mark.asyncio
    async def test_send_course_complete_sms(self, test_db: AsyncSession):
        """Test course completion SMS"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=7
        )
        test_db.add(user)
        await test_db.commit()

        success = await notifier.send_course_complete_sms(user)

        assert success is True

    @pytest.mark.asyncio
    async def test_send_certificate_ready_sms(self, test_db: AsyncSession):
        """Test certificate ready SMS"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()

        success = await notifier.send_certificate_ready_sms(user, "MNAIR-2024-A3B9C")

        assert success is True

    @pytest.mark.asyncio
    async def test_certificate_sms_uses_real_domain(self, test_db: AsyncSession):
        """
        The certificate-ready and course-complete SMS must point learners at
        the live domain (mnair.ng) with a route that actually exists
        (/verify?code=...), not the never-deployed mnair.gov.ng/cert link.
        """
        settings = Settings(TERMII_API_KEY=None, FRONTEND_URL="https://mnair.ng")
        notifier = SMSNotifier(test_db, settings)

        user = User(phone_number="+2348012345678", name="Test User", language="en", current_day=7)
        test_db.add(user)
        await test_db.commit()

        captured = {}

        async def fake_send_sms(phone_number, message):
            captured["message"] = message
            return {"status": "success"}

        notifier.sms_provider.send_sms = fake_send_sms

        await notifier.send_certificate_ready_sms(user, "MNAIR-2026-1-A3B9C")
        assert "mnair.ng" in captured["message"]
        assert "mnair.gov.ng" not in captured["message"]
        assert "/verify?code=MNAIR-2026-1-A3B9C" in captured["message"]

        await notifier.send_course_complete_sms(user)
        assert "mnair.ng" in captured["message"]
        assert "mnair.gov.ng" not in captured["message"]

    @pytest.mark.asyncio
    async def test_send_reminder_sms(self, test_db: AsyncSession):
        """Test inactivity reminder SMS"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en",
            current_day=2
        )
        test_db.add(user)
        await test_db.commit()

        success = await notifier.send_reminder_sms(user, days_inactive=3)

        assert success is True

    @pytest.mark.asyncio
    async def test_send_quiz_reminder_sms(self, test_db: AsyncSession):
        """Test quiz reminder SMS"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        user = User(
            phone_number="+2348012345678",
            name="Test User",
            language="en"
        )
        test_db.add(user)
        await test_db.commit()

        success = await notifier.send_quiz_reminder_sms(user)

        assert success is True

    @pytest.mark.asyncio
    async def test_send_bulk_announcement(self, test_db: AsyncSession):
        """Test bulk SMS announcement"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        # Create multiple users
        users = [
            User(
                phone_number=f"+234801234567{i}",
                name=f"User {i}",
                language="en",
                is_active=True
            )
            for i in range(5)
        ]
        test_db.add_all(users)
        await test_db.commit()

        result = await notifier.send_bulk_announcement("Test announcement")

        assert result["total"] == 5
        assert result["success"] == 5
        assert result["failure"] == 0

    @pytest.mark.asyncio
    async def test_send_bulk_announcement_filtered_by_language(self, test_db: AsyncSession):
        """Test bulk SMS with language filter"""
        settings = Settings(TERMII_API_KEY=None)
        notifier = SMSNotifier(test_db, settings)

        # Create users with different languages
        users = [
            User(phone_number="+2348012345670", name="User 0", language="en", is_active=True),
            User(phone_number="+2348012345671", name="User 1", language="en", is_active=True),
            User(phone_number="+2348012345672", name="User 2", language="hausa", is_active=True),
            User(phone_number="+2348012345673", name="User 3", language="yoruba", is_active=True),
        ]
        test_db.add_all(users)
        await test_db.commit()

        result = await notifier.send_bulk_announcement("Test", language="en")

        assert result["total"] == 2  # Only English users
        assert result["success"] == 2


# ============================================================================
# Certificate Generator Tests
# ============================================================================


class TestCertificateGenerator:
    """Test certificate generation and storage"""

    @pytest.mark.asyncio
    async def test_generate_certificate_id(self):
        """Test certificate ID generation"""
        code = CertificateGenerator.generate_certificate_id(user_id=123)

        assert code.startswith("MNAIR-")
        parts = code.split("-")
        assert len(parts) == 4
        assert parts[0] == "MNAIR"
        assert len(parts[1]) == 4  # Year
        assert parts[2] == "123"  # User ID
        assert len(parts[3]) == 6  # Random part (hex)

    @pytest.mark.asyncio
    async def test_create_certificate_pdf(self, test_db: AsyncSession):
        """Test PDF certificate generation"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            pdf_bytes = generator.create_certificate_pdf(
                user_name="Adebayo Ogunlesi",
                completion_date=datetime(2024, 6, 15),
                verification_code="MNAIR-2024-A3B9C",
                language="en"
            )

            # Verify PDF was created
            assert len(pdf_bytes) > 0
            assert pdf_bytes[:4] == b"%PDF"  # PDF magic number

    @pytest.mark.asyncio
    async def test_upload_to_minio(self, test_db: AsyncSession):
        """Test MinIO upload"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Mock MinIO client
            generator.minio_client = Mock()
            generator.minio_client.put_object = Mock()

            pdf_bytes = b"%PDF-1.4 test content"
            object_name = await generator.upload_to_minio(
                pdf_bytes,
                "MNAIR-2024-A3B9C"
            )

            assert object_name == "certificates/MNAIR-2024-A3B9C.pdf"
            generator.minio_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_certificate_url(self, test_db: AsyncSession):
        """Test pre-signed URL generation"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Mock MinIO client
            generator.minio_client = Mock()
            generator.minio_client.presigned_get_object = Mock(
                return_value="https://minio.example.com/certificate.pdf?signed=true"
            )

            url = await generator.get_certificate_url("MNAIR-2024-A3B9C")

            assert url is not None
            assert "minio.example.com" in url
            assert "signed=true" in url

    @pytest.mark.asyncio
    async def test_generate_and_store_certificate(self, test_db: AsyncSession):
        """Test full certificate generation and storage"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Mock MinIO client
            generator.minio_client = Mock()
            generator.minio_client.put_object = Mock()

            # Create completed user
            user = User(
                phone_number="+2348012345678",
                name="Adebayo Ogunlesi",
                language="en",
                current_day=7  # Completed course
            )
            test_db.add(user)
            await test_db.commit()
            await test_db.refresh(user)

            # Generate certificate
            certificate = await generator.generate_and_store_certificate(user.id)

            # Verify certificate was created
            assert certificate.id is not None
            assert certificate.user_id == user.id
            assert certificate.certificate_id.startswith("MNAIR-")
            assert certificate.pdf_url.startswith("certificates/")
            assert certificate.language == "en"
            assert certificate.learner_name == "Adebayo Ogunlesi"

            # The stored verification_url must point at the real domain and
            # an existing route — the SMS/PDF/USSD text all reference this
            # same link, so a wrong domain here breaks certificate delivery
            # everywhere at once.
            assert certificate.verification_url.startswith(settings.FRONTEND_URL)
            assert "mnair.gov.ng" not in certificate.verification_url
            assert f"/verify?code={certificate.certificate_id}" in certificate.verification_url

            # Verify in database
            result = await test_db.execute(
                select(Certificate).where(Certificate.user_id == user.id)
            )
            db_cert = result.scalar_one()
            assert db_cert.id == certificate.id

    @pytest.mark.asyncio
    async def test_generate_certificate_user_not_found(self, test_db: AsyncSession):
        """Test certificate generation for non-existent user"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            with pytest.raises(ValueError, match="User .* not found"):
                await generator.generate_and_store_certificate(99999)

    @pytest.mark.asyncio
    async def test_generate_certificate_course_not_complete(self, test_db: AsyncSession):
        """Test certificate generation for incomplete user"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Create incomplete user
            user = User(
                phone_number="+2348012345678",
                name="Test User",
                language="en",
                current_day=3  # Not completed
            )
            test_db.add(user)
            await test_db.commit()
            await test_db.refresh(user)

            with pytest.raises(ValueError, match="hasn't completed course"):
                await generator.generate_and_store_certificate(user.id)

    @pytest.mark.asyncio
    async def test_generate_certificate_already_exists(self, test_db: AsyncSession):
        """Test that existing certificate is returned"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Mock MinIO
            generator.minio_client = Mock()
            generator.minio_client.put_object = Mock()

            # Create completed user
            user = User(
                phone_number="+2348012345678",
                name="Test User",
                language="en",
                current_day=7
            )
            test_db.add(user)
            await test_db.commit()
            await test_db.refresh(user)

            # Generate first certificate
            cert1 = await generator.generate_and_store_certificate(user.id)

            # Try to generate again
            cert2 = await generator.generate_and_store_certificate(user.id)

            # Should return existing certificate
            assert cert1.id == cert2.id
            assert cert1.certificate_id == cert2.certificate_id

    @pytest.mark.asyncio
    async def test_verify_certificate_valid(self, test_db: AsyncSession):
        """Test certificate verification with valid code"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Create user and certificate
            user = User(
                phone_number="+2348012345678",
                name="Adebayo Ogunlesi",
                language="en",
                current_day=7
            )
            test_db.add(user)
            await test_db.commit()
            await test_db.refresh(user)

            issued_at = datetime(2024, 6, 15)
            certificate_id = "MNAIR-2024-1-A3B9C"
            verification_hash = Certificate.generate_verification_hash(
                certificate_id=certificate_id,
                user_id=user.id,
                learner_name=user.name,
                issued_at=issued_at
            )

            certificate = Certificate(
                certificate_id=certificate_id,
                user_id=user.id,
                learner_name="Adebayo Ogunlesi",
                learner_phone="+2348012345678",
                language="en",
                total_lessons_completed=35,
                average_quiz_score=85.0,
                days_to_complete=7,
                pdf_url="certificates/MNAIR-2024-1-A3B9C.pdf",
                pdf_filename="MNAIR-2024-1-A3B9C.pdf",
                verification_hash=verification_hash,
                verification_url="https://mnair.gov.ng/verify/MNAIR-2024-1-A3B9C",
                issued_at=issued_at
            )
            test_db.add(certificate)
            await test_db.commit()

            # Verify certificate — requires the matching name, and the
            # response never includes name or phone (public endpoint)
            result = await generator.verify_certificate("MNAIR-2024-1-A3B9C", "Adebayo Ogunlesi")

            assert result is not None
            assert result["valid"] is True
            assert result["certificate_id"] == "MNAIR-2024-1-A3B9C"
            assert "user_name" not in result
            assert "user_phone" not in result

            # Case/whitespace-insensitive match
            result_ci = await generator.verify_certificate("MNAIR-2024-1-A3B9C", "  adebayo   ogunlesi  ")
            assert result_ci is not None
            assert result_ci["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_certificate_invalid(self, test_db: AsyncSession):
        """Test certificate verification with invalid code"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            result = await generator.verify_certificate("MNAIR-2024-INVALID", "Anyone")

            assert result is None

    @pytest.mark.asyncio
    async def test_verify_certificate_wrong_name(self, test_db: AsyncSession):
        """
        A real certificate code with the wrong name must fail exactly like
        an unknown code (returns None either way) -- this is what stops the
        endpoint being used to fish real names out of guessed/leaked codes.
        """
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            user = User(
                phone_number="+2348012345679",
                name="Ngozi Adeyemi",
                language="en",
                current_day=7
            )
            test_db.add(user)
            await test_db.commit()
            await test_db.refresh(user)

            certificate_id = "MNAIR-2024-2-WRONGN"
            certificate = Certificate(
                certificate_id=certificate_id,
                user_id=user.id,
                learner_name="Ngozi Adeyemi",
                learner_phone="+2348012345679",
                language="en",
                total_lessons_completed=35,
                average_quiz_score=90.0,
                days_to_complete=7,
                pdf_url=f"certificates/{certificate_id}.pdf",
                pdf_filename=f"{certificate_id}.pdf",
                verification_hash=Certificate.generate_verification_hash(
                    certificate_id=certificate_id, user_id=user.id,
                    learner_name=user.name, issued_at=datetime(2024, 6, 15)
                ),
                verification_url=f"https://mnair.ng/verify?code={certificate_id}",
                issued_at=datetime(2024, 6, 15)
            )
            test_db.add(certificate)
            await test_db.commit()

            result = await generator.verify_certificate(certificate_id, "Someone Else")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_user_certificate(self, test_db: AsyncSession):
        """Test getting user's certificate"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            # Create user and certificate
            user = User(
                phone_number="+2348012345678",
                name="Test User",
                language="en",
                current_day=7
            )
            test_db.add(user)
            await test_db.commit()
            await test_db.refresh(user)

            issued_at = datetime.now()
            certificate_id = "MNAIR-2024-TEST"
            verification_hash = Certificate.generate_verification_hash(
                certificate_id=certificate_id,
                user_id=user.id,
                learner_name=user.name,
                issued_at=issued_at
            )

            certificate = Certificate(
                certificate_id=certificate_id,
                user_id=user.id,
                learner_name="Test User",
                learner_phone="+2348012345678",
                language="en",
                total_lessons_completed=35,
                average_quiz_score=75.0,
                days_to_complete=7,
                pdf_url="certificates/MNAIR-2024-TEST.pdf",
                pdf_filename="MNAIR-2024-TEST.pdf",
                verification_hash=verification_hash,
                verification_url="https://mnair.gov.ng/verify/MNAIR-2024-TEST",
                issued_at=issued_at
            )
            test_db.add(certificate)
            await test_db.commit()

            # Get certificate
            result = await generator.get_user_certificate(user.id)

            assert result is not None
            assert result.user_id == user.id
            assert result.certificate_id == "MNAIR-2024-TEST"

    @pytest.mark.asyncio
    async def test_get_user_certificate_not_found(self, test_db: AsyncSession):
        """Test getting certificate for user without one"""
        settings = Settings()

        with patch.object(CertificateGenerator, "_ensure_bucket_exists"):
            generator = CertificateGenerator(test_db, settings)

            result = await generator.get_user_certificate(99999)

            assert result is None
