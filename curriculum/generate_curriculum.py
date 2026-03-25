"""
Curriculum Generator for MNAIR
Generates 175 YAML lesson files (7 days × 5 topics × 5 languages)
"""

import os
import yaml
from pathlib import Path

# Base curriculum structure - simplified for MVP
# In production, you'd translate content properly with native speakers

TOPICS = ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]
LANGUAGES = {
    "en": "English",
    "pid": "Pidgin",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ig": "Igbo"
}

# Simplified day progression
DAY_FOCUS = {
    1: "Introduction to AI",
    2: "Machine Learning Basics",
    3: "Data and AI",
    4: "AI Applications",
    5: "Building with AI",
    6: "AI for Business",
    7: "Your AI Future"
}

def generate_lesson_yaml(day, topic, language):
    """Generate a lesson YAML file"""

    lesson_id = f"day{day}_{topic}_{language}"

    # For MVP, we'll create placeholder content for non-English
    # In production, translate with native speakers
    if language == "en":
        # Use existing Day 1 English content as template
        if day == 1:
            return None  # Already created manually

    # Generate content based on day and topic
    title = f"Day {day}: {topic.replace('_', ' ').title()} ({LANGUAGES[language]})"

    content = f"""This is Day {day} lesson on {topic.replace('_', ' ')}.

Focus: {DAY_FOCUS[day]}

[In production, this would be 250-300 words of properly translated content]

Key points:
- Understanding {topic.replace('_', ' ')}
- Nigerian context and examples
- Practical applications
- How this helps you

Remember: AI is a tool to solve problems. Learn, practice, and build!
"""

    quiz = [
        {
            "question": f"What is the main focus of Day {day}?",
            "options": [
                f"A. {DAY_FOCUS[day]}",
                "B. Something else",
                "C. Random topic",
                "D. Not related"
            ],
            "correct": 0
        },
        {
            "question": f"This lesson is about:",
            "options": [
                "A. Cooking",
                f"B. {topic.replace('_', ' ').title()}",
                "C. Sports",
                "D. Music"
            ],
            "correct": 1
        },
        {
            "question": "Can AI help solve Nigerian problems?",
            "options": [
                "A. Yes, definitely",
                "B. No, never",
                "C. Only in cities",
                "D. Maybe not"
            ],
            "correct": 0
        },
        {
            "question": "What should you do after this lesson?",
            "options": [
                "A. Forget everything",
                "B. Practice and apply what you learned",
                "C. Do nothing",
                "D. Give up"
            ],
            "correct": 1
        },
        {
            "question": f"Is {topic.replace('_', ' ')} important for Nigeria?",
            "options": [
                "A. Yes, very important",
                "B. No value",
                "C. Only for foreigners",
                "D. Not relevant"
            ],
            "correct": 0
        }
    ]

    lesson = {
        "id": lesson_id,
        "day": day,
        "topic": topic,
        "language": language,
        "title": title,
        "content": content.strip(),
        "quiz": quiz
    }

    return lesson


def main():
    """Generate all curriculum files"""

    base_dir = Path(__file__).parent
    created = 0
    skipped = 0

    for day in range(1, 8):  # Days 1-7
        day_dir = base_dir / f"day{day}"
        day_dir.mkdir(exist_ok=True)

        for topic in TOPICS:
            for lang in LANGUAGES.keys():
                filename = f"{topic}_{lang}.yaml"
                filepath = day_dir / filename

                # Skip if already exists (Day 1 English files)
                if filepath.exists():
                    print(f"**  Skipping {filepath.name} (already exists)")
                    skipped += 1
                    continue

                # Generate lesson
                lesson = generate_lesson_yaml(day, topic, lang)
                if lesson is None:
                    continue

                # Write YAML file
                with open(filepath, 'w', encoding='utf-8') as f:
                    yaml.dump(lesson, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

                print(f"[OK] Created {filepath.name}")
                created += 1

    print("\n" + "=" * 60)
    print(f"[OK] Created {created} new lesson files")
    print(f"**  Skipped {skipped} existing files")
    print(f"📚 Total expected: 175 files (7 days × 5 topics × 5 languages)")
    print("=" * 60)


if __name__ == "__main__":
    main()
