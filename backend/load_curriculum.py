"""
Load Curriculum from YAML files into Database
"""
import asyncio
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from app.database import AsyncSessionLocal
from app.models.lesson import Lesson

# Point to the correct curriculum directory
CURRICULUM_DIR = Path("C:/Users/yomis/mnair/curriculum")

async def load_lessons():
    """Load all YAML lesson files into the database"""
    print("Loading curriculum from YAML files...")
    print(f"Looking in: {CURRICULUM_DIR}")

    if not CURRICULUM_DIR.exists():
        print(f"[ERROR] Curriculum directory not found: {CURRICULUM_DIR}")
        return 0

    # Find all YAML files
    yaml_files = list(CURRICULUM_DIR.glob("**/*.yaml"))
    print(f"Found {len(yaml_files)} YAML files")

    if not yaml_files:
        print("[ERROR] No YAML files found!")
        return 0

    loaded_count = 0
    skipped_count = 0

    async with AsyncSessionLocal() as db:
        for yaml_file in yaml_files:
            try:
                # Read YAML file
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)

                # Check if lesson already exists
                from sqlalchemy import select
                result = await db.execute(
                    select(Lesson).where(Lesson.lesson_id == data['id'])
                )
                existing = result.scalar_one_or_none()

                if existing:
                    skipped_count += 1
                    continue

                # Build quiz list (normalize correct_answer → correct)
                quiz_data = []
                if 'quiz' in data and data['quiz']:
                    for q in data['quiz']:
                        quiz_data.append({
                            'question': q['question'],
                            'options': q['options'],
                            'correct': q.get('correct', q.get('correct_answer', 0)),
                        })

                content = data['content']
                word_count = len(content.split())

                # Create lesson
                lesson = Lesson(
                    lesson_id=data['id'],
                    day=data['day'],
                    topic=data['topic'],
                    language=data['language'],
                    title=data['title'],
                    content=content,
                    quiz=quiz_data,
                    word_count=word_count,
                )

                db.add(lesson)
                loaded_count += 1

                # Commit every 10 lessons to avoid huge transactions
                if loaded_count % 10 == 0:
                    await db.commit()
                    print(f"  Loaded {loaded_count} lessons...")

            except Exception as e:
                print(f"[ERROR] Failed to load {yaml_file.name}: {e}")
                continue

        # Final commit
        await db.commit()

    print("")
    print(f"[OK] Successfully loaded {loaded_count} lessons")
    if skipped_count > 0:
        print(f"[INFO] Skipped {skipped_count} existing lessons")

    return loaded_count

async def main():
    try:
        count = await load_lessons()
        return 0 if count > 0 else 1
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
