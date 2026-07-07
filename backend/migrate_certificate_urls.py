"""
Migration Script: Fix existing certificates pointing at the wrong domain
(Windows Compatible)

Certificates generated before the domain fix have "mnair.gov.ng" (never the
real deployed site) baked into two places:
  1. The verification_url column in the database
  2. The rendered PDF itself -- the "Verify this certificate at:" line is
     drawn directly onto the PDF image, so fixing the database column alone
     leaves the actual downloadable file showing a dead link.

This script re-renders the PDF (same certificate_id, learner name, and issue
date -- the certificate content itself doesn't change, only the printed
verify-link text) and re-uploads it to the same MinIO object path, then
updates verification_url to match. Safe to re-run -- rows already on the
correct domain are skipped.

Usage (from inside the backend container or a matching venv):
    python migrate_certificate_urls.py            # apply
    python migrate_certificate_urls.py --dry-run  # preview only, no writes
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.certificate import Certificate
from app.models.user import User
from app.certificates.generator import CertificateGenerator
from app.config import settings


async def migrate(dry_run: bool = False):
    print(f"Starting certificate URL migration{' (DRY RUN)' if dry_run else ''}...")
    print(f"Target domain: {settings.FRONTEND_URL}")

    async with AsyncSessionLocal() as db:
        generator = CertificateGenerator(db, settings)

        result = await db.execute(select(Certificate))
        certificates = result.scalars().all()

        checked = 0
        updated = 0
        skipped_ok = 0
        failed = 0

        for cert in certificates:
            checked += 1

            correct_url = f"{settings.FRONTEND_URL}/verify?code={cert.certificate_id}"

            if cert.verification_url == correct_url:
                skipped_ok += 1
                continue

            print(f"  Certificate {cert.certificate_id} (user {cert.user_id}):")
            print(f"    old: {cert.verification_url}")
            print(f"    new: {correct_url}")

            if dry_run:
                updated += 1
                continue

            try:
                user_result = await db.execute(select(User).where(User.id == cert.user_id))
                user = user_result.scalar_one_or_none()
                learner_name = user.name if user else cert.learner_name

                # Re-render the PDF with the corrected verify-link text and
                # overwrite the existing object at the same path
                pdf_bytes = generator.create_certificate_pdf(
                    user_name=learner_name,
                    completion_date=cert.issued_at,
                    verification_code=cert.certificate_id,
                    language=cert.language,
                )
                await generator.upload_to_minio(pdf_bytes, cert.certificate_id)

                cert.verification_url = correct_url
                cert.file_size_bytes = len(pdf_bytes)
                updated += 1

            except Exception as e:
                print(f"    [ERROR] failed to migrate: {e}")
                failed += 1

        if not dry_run and updated > 0:
            await db.commit()

        print("")
        print(f"Checked {checked} certificate(s).")
        print(f"Already correct: {skipped_ok}")
        print(f"{'Would fix' if dry_run else 'Fixed'}: {updated}")
        if failed:
            print(f"Failed: {failed} (see errors above)")

        if dry_run and updated > 0:
            print("\nRe-run without --dry-run to apply these changes.")


async def main():
    dry_run = "--dry-run" in sys.argv
    try:
        await migrate(dry_run=dry_run)
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
