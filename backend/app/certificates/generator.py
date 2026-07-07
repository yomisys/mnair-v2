"""
Certificate Generator for MNAIR Platform
Generates PDF certificates with Nigerian branding and verification codes
"""

from __future__ import annotations
import io
import secrets
from datetime import datetime
from typing import Optional, Dict, Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from minio import Minio
from minio.error import S3Error

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.certificate import Certificate
from app.config import Settings


class CertificateGenerator:
    """
    Generates and manages PDF certificates for course completion
    Uses ReportLab for PDF generation and MinIO for storage
    """

    # Nigerian flag colors
    NIGERIAN_GREEN = HexColor("#008751")
    NIGERIAN_WHITE = HexColor("#FFFFFF")

    # Certificate colors
    BORDER_COLOR = HexColor("#1a472a")
    TITLE_COLOR = HexColor("#2d5016")
    TEXT_COLOR = HexColor("#333333")
    ACCENT_COLOR = HexColor("#f4a460")

    def __init__(self, db: AsyncSession, settings: Settings):
        """
        Initialize certificate generator

        Args:
            db: Database session
            settings: Application settings
        """
        self.db = db
        self.settings = settings

        # Initialize MinIO client
        self.minio_client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        """Create MinIO bucket if it doesn't exist"""
        try:
            if not self.minio_client.bucket_exists(self.settings.MINIO_BUCKET):
                self.minio_client.make_bucket(self.settings.MINIO_BUCKET)
                print(f"[INFO] Created MinIO bucket: {self.settings.MINIO_BUCKET}")
        except S3Error as e:
            print(f"[ERROR] MinIO bucket creation failed: {e}")

    @staticmethod
    def generate_certificate_id(user_id: int) -> str:
        """
        Generate unique certificate ID
        Format: MNAIR-YYYY-USERID-RANDOM (e.g., MNAIR-2024-123-A3B9C)

        Args:
            user_id: User ID

        Returns:
            Certificate ID string
        """
        year = datetime.now().year
        random_part = secrets.token_hex(3).upper()
        return f"MNAIR-{year}-{user_id}-{random_part}"

    def _draw_certificate_border(self, c: canvas.Canvas, width: float, height: float) -> None:
        """
        Draw decorative border around certificate

        Args:
            c: ReportLab canvas
            width: Page width
            height: Page height
        """
        # Outer border - Nigerian green
        c.setStrokeColor(self.NIGERIAN_GREEN)
        c.setLineWidth(8)
        c.rect(0.3 * inch, 0.3 * inch, width - 0.6 * inch, height - 0.6 * inch)

        # Inner border - Accent color
        c.setStrokeColor(self.ACCENT_COLOR)
        c.setLineWidth(2)
        c.rect(0.5 * inch, 0.5 * inch, width - 1.0 * inch, height - 1.0 * inch)

        # Corner decorations
        c.setFillColor(self.NIGERIAN_GREEN)
        corner_size = 0.2 * inch
        corners = [
            (0.3 * inch, height - 0.3 * inch),  # Top left
            (width - 0.3 * inch, height - 0.3 * inch),  # Top right
            (0.3 * inch, 0.3 * inch),  # Bottom left
            (width - 0.3 * inch, 0.3 * inch)  # Bottom right
        ]
        for x, y in corners:
            c.circle(x, y, corner_size, fill=1)

    def _draw_nigerian_flag(self, c: canvas.Canvas, x: float, y: float) -> None:
        """
        Draw small Nigerian flag

        Args:
            c: ReportLab canvas
            x: X position
            y: Y position
        """
        flag_width = 0.6 * inch
        flag_height = 0.4 * inch
        stripe_width = flag_width / 3

        # Green stripe
        c.setFillColor(self.NIGERIAN_GREEN)
        c.rect(x, y, stripe_width, flag_height, fill=1, stroke=0)

        # White stripe
        c.setFillColor(self.NIGERIAN_WHITE)
        c.rect(x + stripe_width, y, stripe_width, flag_height, fill=1, stroke=0)

        # Green stripe
        c.setFillColor(self.NIGERIAN_GREEN)
        c.rect(x + 2 * stripe_width, y, stripe_width, flag_height, fill=1, stroke=0)

        # Border
        c.setStrokeColor(self.TEXT_COLOR)
        c.setLineWidth(1)
        c.rect(x, y, flag_width, flag_height, fill=0, stroke=1)

    def create_certificate_pdf(
        self,
        user_name: str,
        completion_date: datetime,
        verification_code: str,
        language: str = "en"
    ) -> bytes:
        """
        Generate PDF certificate as bytes

        Args:
            user_name: Full name of certificate recipient
            completion_date: Date of course completion
            verification_code: Unique verification code
            language: Certificate language (en, pidgin, hausa, yoruba, igbo)

        Returns:
            PDF bytes
        """
        # Create PDF in memory
        buffer = io.BytesIO()

        # Use landscape A4
        page_width, page_height = landscape(A4)
        c = canvas.Canvas(buffer, pagesize=landscape(A4))

        # Draw border
        self._draw_certificate_border(c, page_width, page_height)

        # Draw Nigerian flags in corners
        self._draw_nigerian_flag(c, 0.7 * inch, page_height - 0.9 * inch)
        self._draw_nigerian_flag(c, page_width - 1.3 * inch, page_height - 0.9 * inch)

        # Title section
        c.setFillColor(self.TITLE_COLOR)
        c.setFont("Helvetica-Bold", 36)
        title_y = page_height - 1.5 * inch
        c.drawCentredString(page_width / 2, title_y, "CERTIFICATE OF COMPLETION")

        # Subtitle
        c.setFont("Helvetica", 16)
        c.setFillColor(self.TEXT_COLOR)
        c.drawCentredString(page_width / 2, title_y - 0.5 * inch, "Make Nigeria AI Ready Initiative")

        # Divider line
        c.setStrokeColor(self.ACCENT_COLOR)
        c.setLineWidth(2)
        line_y = title_y - 0.8 * inch
        c.line(2 * inch, line_y, page_width - 2 * inch, line_y)

        # "This is to certify that"
        c.setFont("Helvetica", 14)
        c.setFillColor(self.TEXT_COLOR)
        body_y = line_y - 0.6 * inch
        c.drawCentredString(page_width / 2, body_y, "This is to certify that")

        # Recipient name
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(self.TITLE_COLOR)
        name_y = body_y - 0.6 * inch
        c.drawCentredString(page_width / 2, name_y, user_name)

        # Name underline
        c.setStrokeColor(self.ACCENT_COLOR)
        c.setLineWidth(1)
        name_width = c.stringWidth(user_name, "Helvetica-Bold", 28)
        c.line(
            page_width / 2 - name_width / 2,
            name_y - 0.1 * inch,
            page_width / 2 + name_width / 2,
            name_y - 0.1 * inch
        )

        # Achievement text
        c.setFont("Helvetica", 14)
        c.setFillColor(self.TEXT_COLOR)
        achievement_y = name_y - 0.7 * inch
        c.drawCentredString(
            page_width / 2,
            achievement_y,
            "has successfully completed the 7-day"
        )
        c.drawCentredString(
            page_width / 2,
            achievement_y - 0.3 * inch,
            "Artificial Intelligence Fundamentals Course"
        )

        # Completion date
        c.setFont("Helvetica-Oblique", 12)
        date_str = completion_date.strftime("%B %d, %Y")
        date_y = achievement_y - 0.9 * inch
        c.drawCentredString(page_width / 2, date_y, f"Completed on {date_str}")

        # Verification section
        c.setFont("Helvetica", 10)
        c.setFillColor(self.TEXT_COLOR)
        verify_y = 1.2 * inch
        verify_host = self.settings.FRONTEND_URL.replace("https://", "").replace("http://", "")
        c.drawCentredString(
            page_width / 2,
            verify_y,
            f"Verify this certificate at: {verify_host}/verify"
        )

        # Verification code
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(self.TITLE_COLOR)
        c.drawCentredString(
            page_width / 2,
            verify_y - 0.25 * inch,
            f"Verification Code: {verification_code}"
        )

        # Save PDF
        c.save()

        # Get PDF bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

    async def upload_to_minio(
        self,
        pdf_bytes: bytes,
        certificate_code: str
    ) -> str:
        """
        Upload PDF to MinIO storage

        Args:
            pdf_bytes: PDF file bytes
            certificate_code: Unique certificate code

        Returns:
            Object name in MinIO
        """
        # Generate object name: certificates/MNAIR-2024-A3B9C.pdf
        object_name = f"certificates/{certificate_code}.pdf"

        try:
            # Upload to MinIO
            buffer = io.BytesIO(pdf_bytes)
            self.minio_client.put_object(
                bucket_name=self.settings.MINIO_BUCKET,
                object_name=object_name,
                data=buffer,
                length=len(pdf_bytes),
                content_type="application/pdf"
            )

            return object_name

        except S3Error as e:
            print(f"[ERROR] MinIO upload failed: {e}")
            raise

    async def get_certificate_url(self, certificate_code: str) -> Optional[str]:
        """
        Get pre-signed URL for certificate download

        Args:
            certificate_code: Unique certificate code

        Returns:
            Pre-signed URL (valid for 7 days) or None if not found
        """
        object_name = f"certificates/{certificate_code}.pdf"

        try:
            # Generate pre-signed URL (valid for 7 days)
            url = self.minio_client.presigned_get_object(
                bucket_name=self.settings.MINIO_BUCKET,
                object_name=object_name,
                expires=7 * 24 * 60 * 60  # 7 days in seconds
            )
            return url

        except S3Error as e:
            print(f"[ERROR] Failed to generate URL: {e}")
            return None

    async def generate_and_store_certificate(
        self,
        user_id: int,
        language: str = "en"
    ) -> Certificate:
        """
        Generate certificate for user and store in database + MinIO

        Args:
            user_id: User ID
            language: Certificate language

        Returns:
            Certificate model instance

        Raises:
            ValueError: If user not found or hasn't completed course
        """
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        if user.current_day < 7:
            raise ValueError(
                f"User {user_id} hasn't completed course (day {user.current_day}/7)"
            )

        # Check if certificate already exists
        existing = await self.db.execute(
            select(Certificate).where(Certificate.user_id == user_id)
        )
        existing_cert = existing.scalar_one_or_none()

        if existing_cert:
            return existing_cert

        # Generate certificate ID
        certificate_id = self.generate_certificate_id(user_id)
        issued_at = datetime.now()

        # Generate PDF
        pdf_bytes = self.create_certificate_pdf(
            user_name=user.name,
            completion_date=issued_at,
            verification_code=certificate_id,
            language=language
        )

        # Upload to MinIO
        object_name = await self.upload_to_minio(pdf_bytes, certificate_id)
        pdf_filename = f"{certificate_id}.pdf"

        # Generate verification hash
        verification_hash = Certificate.generate_verification_hash(
            certificate_id=certificate_id,
            user_id=user_id,
            learner_name=user.name,
            issued_at=issued_at
        )

        # Generate verification URL. The /verify page is a manual code-entry
        # form (no path-param route), so the certificate ID goes in a query
        # string the frontend prefills — see VerifyCertificate.tsx.
        verification_url = f"{self.settings.FRONTEND_URL}/verify?code={certificate_id}"

        # Create certificate record
        certificate = Certificate(
            certificate_id=certificate_id,
            user_id=user_id,
            learner_name=user.name,
            learner_phone=user.phone_number,
            language=language,
            total_lessons_completed=35,
            average_quiz_score=75.0,  # Default, should be calculated from actual quiz attempts
            days_to_complete=user.current_day,
            pdf_url=object_name,
            pdf_filename=pdf_filename,
            file_size_bytes=len(pdf_bytes),
            verification_hash=verification_hash,
            verification_url=verification_url,
            issued_at=issued_at
        )

        self.db.add(certificate)
        await self.db.commit()
        await self.db.refresh(certificate)

        return certificate

    async def verify_certificate(self, certificate_id: str) -> Optional[Dict[str, Any]]:
        """
        Verify certificate authenticity

        Args:
            certificate_id: Certificate ID to verify

        Returns:
            Dict with certificate details or None if invalid
        """
        result = await self.db.execute(
            select(Certificate).where(
                Certificate.certificate_id == certificate_id
            )
        )
        certificate = result.scalar_one_or_none()

        if not certificate:
            return None

        # Get user details
        user_result = await self.db.execute(
            select(User).where(User.id == certificate.user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return None

        return {
            "valid": True,
            "user_name": certificate.learner_name,
            "user_phone": certificate.learner_phone,
            "issued_date": certificate.issued_at,
            "language": certificate.language,
            "certificate_id": certificate_id,
            "average_score": certificate.average_quiz_score
        }

    async def get_user_certificate(self, user_id: int) -> Optional[Certificate]:
        """
        Get certificate for user

        Args:
            user_id: User ID

        Returns:
            Certificate or None if not found
        """
        result = await self.db.execute(
            select(Certificate).where(Certificate.user_id == user_id)
        )
        return result.scalar_one_or_none()
