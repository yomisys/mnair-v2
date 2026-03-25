"""
Curriculum Loader Service
Loads YAML lesson files and seeds database
"""

from __future__ import annotations
import yaml
from pathlib import Path
from typing import List, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.lesson import Lesson
from app.database import AsyncSessionLocal


class CurriculumLoader:
    """Service to load curriculum YAML files into database"""

    def __init__(self, curriculum_dir: str | Path):
        """
        Initialize loader with curriculum directory path

        Args:
            curriculum_dir: Path to directory containing day1/, day2/, etc.
        """
        self.curriculum_dir = Path(curriculum_dir)
        if not self.curriculum_dir.exists():
            raise ValueError(f"Curriculum directory not found: {self.curriculum_dir}")

    def load_yaml_file(self, filepath: Path) -> Optional[Dict]:
        """
        Load and parse a single YAML lesson file

        Args:
            filepath: Path to YAML file

        Returns:
            Parsed lesson data or None if invalid
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # Validate required fields
            required_fields = ['id', 'day', 'topic', 'language', 'title', 'content', 'quiz']
            missing = [field for field in required_fields if field not in data]

            if missing:
                print(f"[WARN] {filepath.name}: Missing fields {missing}")
                return None

            # Validate quiz structure
            if not isinstance(data['quiz'], list) or len(data['quiz']) != 5:
                print(f"[WARN] {filepath.name}: Quiz must have exactly 5 questions")
                return None

            for i, q in enumerate(data['quiz']):
                if not all(k in q for k in ['question', 'options', 'correct']):
                    print(f"[WARN] {filepath.name}: Quiz question {i+1} invalid structure")
                    return None

                if len(q['options']) != 4:
                    print(f"[WARN] {filepath.name}: Quiz question {i+1} must have 4 options")
                    return None

            return data

        except yaml.YAMLError as e:
            print(f"[ERROR] {filepath.name}: YAML parse error: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] {filepath.name}: {e}")
            return None

    def discover_lessons(self) -> List[Dict]:
        """
        Discover and load all YAML lesson files

        Returns:
            List of validated lesson data dictionaries
        """
        lessons = []

        # Iterate through day directories
        for day in range(1, 8):
            day_dir = self.curriculum_dir / f"day{day}"

            if not day_dir.exists():
                print(f"[WARN] Missing directory: {day_dir}")
                continue

            # Load all YAML files in day directory
            yaml_files = list(day_dir.glob("*.yaml")) + list(day_dir.glob("*.yml"))

            for filepath in yaml_files:
                lesson_data = self.load_yaml_file(filepath)
                if lesson_data:
                    lessons.append(lesson_data)

        return lessons

    def prepare_lesson_record(self, lesson_data: Dict) -> Dict:
        """
        Convert YAML data to database record format

        Args:
            lesson_data: Parsed YAML lesson data

        Returns:
            Dictionary ready for database insertion
        """
        # Calculate word count
        content = lesson_data['content']
        word_count = len(content.split())

        record = {
            'lesson_id': lesson_data['id'],
            'day': lesson_data['day'],
            'topic': lesson_data['topic'],
            'language': lesson_data['language'],
            'title': lesson_data['title'],
            'content': content,
            'quiz': lesson_data['quiz'],
            'estimated_duration_minutes': lesson_data.get('estimated_duration_minutes', 5),
            'word_count': word_count,
            'image_url': lesson_data.get('image_url'),
            'audio_url': lesson_data.get('audio_url'),
        }

        return record

    async def seed_database(self, db: AsyncSession) -> Dict[str, int]:
        """
        Load lessons into database using upsert

        Args:
            db: Database session

        Returns:
            Statistics: {inserted, updated, errors}
        """
        stats = {'inserted': 0, 'updated': 0, 'errors': 0, 'total': 0}

        # Discover all lessons
        lessons_data = self.discover_lessons()
        stats['total'] = len(lessons_data)

        print(f"\n[INFO] Found {len(lessons_data)} lesson files")
        print(f"[INFO] Starting database seed...\n")

        for lesson_data in lessons_data:
            try:
                record = self.prepare_lesson_record(lesson_data)

                # Use PostgreSQL INSERT ... ON CONFLICT DO UPDATE (upsert)
                stmt = insert(Lesson).values(**record)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['lesson_id'],
                    set_={
                        'title': stmt.excluded.title,
                        'content': stmt.excluded.content,
                        'quiz': stmt.excluded.quiz,
                        'word_count': stmt.excluded.word_count,
                    }
                )

                await db.execute(stmt)
                stats['inserted'] += 1

                if stats['inserted'] % 25 == 0:
                    print(f"[PROGRESS] Loaded {stats['inserted']}/{stats['total']} lessons...")

            except Exception as e:
                print(f"[ERROR] Failed to insert {lesson_data['id']}: {e}")
                stats['errors'] += 1
                continue

        # Commit transaction
        await db.commit()

        return stats

    async def verify_database(self, db: AsyncSession) -> Dict:
        """
        Verify lessons in database

        Args:
            db: Database session

        Returns:
            Verification statistics
        """
        # Count total lessons
        result = await db.execute(select(Lesson))
        all_lessons = result.scalars().all()

        # Group by language
        by_language = {}
        by_day = {}

        for lesson in all_lessons:
            lang = lesson.language
            day = lesson.day

            by_language[lang] = by_language.get(lang, 0) + 1
            by_day[day] = by_day.get(day, 0) + 1

        return {
            'total': len(all_lessons),
            'by_language': by_language,
            'by_day': by_day,
        }


async def load_curriculum(curriculum_dir: str | Path = None):
    """
    Standalone function to load curriculum into database

    Args:
        curriculum_dir: Path to curriculum directory (defaults to ../../../curriculum)
    """
    if curriculum_dir is None:
        # Default to curriculum directory relative to this file
        backend_dir = Path(__file__).parent.parent.parent
        curriculum_dir = backend_dir.parent / "curriculum"

    loader = CurriculumLoader(curriculum_dir)

    async with AsyncSessionLocal() as db:
        print("=" * 60)
        print("MNAIR Curriculum Loader")
        print("=" * 60)

        # Seed database
        stats = await loader.seed_database(db)

        print("\n" + "=" * 60)
        print("Seed Results:")
        print(f"  Total files: {stats['total']}")
        print(f"  Inserted: {stats['inserted']}")
        print(f"  Errors: {stats['errors']}")
        print("=" * 60)

        # Verify
        print("\nVerifying database...")
        verification = await loader.verify_database(db)

        print("\nDatabase Statistics:")
        print(f"  Total lessons: {verification['total']}")
        print(f"\n  By Language:")
        for lang, count in sorted(verification['by_language'].items()):
            print(f"    {lang}: {count}")
        print(f"\n  By Day:")
        for day, count in sorted(verification['by_day'].items()):
            print(f"    Day {day}: {count}")

        print("\n" + "=" * 60)

        if verification['total'] == 175:
            print("[SUCCESS] All 175 lessons loaded successfully!")
        else:
            print(f"[WARN] Expected 175 lessons, found {verification['total']}")

        print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(load_curriculum())
