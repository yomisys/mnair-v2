"""
Backfill Script: Recompute completed_days for stuck learners (Windows Compatible)

Fixes the effect of the bug where completed_days was only incremented by
advance_to_next_day, which never fires for Day 7 (no Day 8 to advance to) and
which a learner also skips whenever they finish a day's lessons but never
reply "NEXT"/dial back in. This script recomputes completed_days for every
active learner from the real lesson-completion data (is_day_complete), the
same check the fixed code now uses going forward.

Only ever raises completed_days upward (never lowers it) and only touches
users where the recomputed value is higher than what's stored — safe to
re-run any number of times.

Usage (from inside the backend container or a matching venv):
    python backfill_completed_days.py            # apply
    python backfill_completed_days.py --dry-run  # preview only, no writes
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.services.lesson_state import LessonStateManager


async def backfill(dry_run: bool = False):
    print(f"Starting completed_days backfill{' (DRY RUN)' if dry_run else ''}...")

    async with AsyncSessionLocal() as db:
        manager = LessonStateManager(db)

        result = await db.execute(
            select(User).where(
                User.role == UserRole.LEARNER,
                User.is_active == True,
            )
        )
        users = result.scalars().all()

        checked = 0
        updated = 0
        stuck_on_day_7 = 0

        for user in users:
            checked += 1

            # Find the highest day (1..current_day) the learner has actually
            # finished all 5 lessons for -- this is the ground truth,
            # independent of whatever completed_days currently says.
            actual_completed = 0
            for day in range(1, user.current_day + 1):
                if await manager.is_day_complete(user.id, day):
                    actual_completed = day
                else:
                    break  # days are sequential; stop at the first gap

            if actual_completed > user.completed_days:
                print(
                    f"  User {user.id} ({user.phone_number}): "
                    f"completed_days {user.completed_days} -> {actual_completed} "
                    f"(current_day={user.current_day})"
                )
                if actual_completed == 7:
                    stuck_on_day_7 += 1

                if not dry_run:
                    user.completed_days = actual_completed

                updated += 1

        if not dry_run and updated > 0:
            await db.commit()

        print("")
        print(f"Checked {checked} learners.")
        print(f"{'Would update' if dry_run else 'Updated'} {updated} learner(s).")
        print(f"Of those, {stuck_on_day_7} reached completed_days=7 "
              f"(now eligible for certificate generation/USSD certificate menu).")

        if dry_run and updated > 0:
            print("\nRe-run without --dry-run to apply these changes.")


async def main():
    dry_run = "--dry-run" in sys.argv
    try:
        await backfill(dry_run=dry_run)
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
