"""
Channel-agnostic message builder.

Ported from the retired WhatsAppMessageBuilder: same copy, same flow, but the
output is an OutboundMessage (text + buttons) instead of a Meta Cloud API
payload. Telegram renders buttons as an inline keyboard; the web learner app
renders them as tappable chips. Typed keywords still work everywhere.
"""

from __future__ import annotations
import re
from typing import List, Optional

from app.engine.messages import Button, OutboundMessage
from app.models.lesson import Lesson
from app.models.user import Language


LANGUAGE_BUTTONS = [
    Button("lang_en", "English", "Learn in English"),
    Button("lang_pid", "Pidgin", "Learn for Naija Pidgin"),
    Button("lang_ha", "Hausa", "Koyi cikin Hausa"),
    Button("lang_yo", "Yoruba", "Kọ ẹkọ ni ede Yoruba"),
    Button("lang_ig", "Igbo", "Mụta n'asụsụ Igbo"),
]

LANGUAGE_NAMES = {
    Language.ENGLISH: "English",
    Language.PIDGIN: "Pidgin",
    Language.HAUSA: "Hausa",
    Language.YORUBA: "Yoruba",
    Language.IGBO: "Igbo",
}


class MessageBuilder:
    """Builds every learner-facing message in the 7-day flow."""

    # Curriculum option strings mostly embed their own letter prefix
    # ("A. Knowing HOW to work with AI"); options are displayed SHUFFLED,
    # so the embedded letter contradicts the assigned display letter.
    # Strip it before display; punctuation+space required after the letter
    # so a literal one-letter option is never stripped to nothing.
    _EMBEDDED_LETTER_PREFIX = re.compile(r"^[A-Da-d][.)]\s+")

    @staticmethod
    def build_welcome_message(name: Optional[str] = None) -> OutboundMessage:
        greeting = f"Hello {name}! " if name else "Hello! "
        return OutboundMessage(
            kind="text",
            text=(
                f"{greeting}🎓 Welcome to Make Nigeria AI Ready (MNAIR)!\n\n"
                "Learn Artificial Intelligence in 7 days - for FREE!\n\n"
                "📱 Study at your own pace\n"
                "🎯 5 topics per day\n"
                "📜 Get a certificate when you finish\n\n"
                "Ready to start your AI journey?"
            ),
        )

    @staticmethod
    def build_language_selector() -> OutboundMessage:
        return OutboundMessage(
            kind="choice",
            text=(
                "Choose your preferred language:\n\n"
                "Select the language you're most comfortable with for learning."
            ),
            buttons=list(LANGUAGE_BUTTONS),
            meta={"choice": "language"},
        )

    @staticmethod
    def build_lesson_message(lesson: Lesson, lesson_number: int, total: int = 5) -> OutboundMessage:
        # The longest lesson in the curriculum is ~1900 chars; Telegram's
        # limit is 4096 and the web has none, so the full lesson always fits.
        text = (
            f"📚 Day {lesson.day} - Lesson {lesson_number}/{total}\n"
            f"{'=' * 30}\n\n"
            f"*{lesson.title}*\n\n"
            f"{lesson.content}\n\n"
            f"{'=' * 30}\n"
            f"Ready for the quiz? Tap *Start quiz* or reply *QUIZ*!"
        )
        return OutboundMessage(
            kind="lesson",
            text=text,
            buttons=[Button("quiz", "📝 Start quiz")],
            meta={
                "lesson_id": lesson.id,
                "day": lesson.day,
                "lesson_number": lesson_number,
                "total": total,
                "title": lesson.title,
            },
        )

    @classmethod
    def build_quiz_message(cls, lesson: Lesson, question_num: int, order: List[int]) -> OutboundMessage:
        """Quiz question with one button per option.

        `order` is the display shuffle for this question (see
        app.services.quiz_shuffle) -- button ids are keyed by *display*
        position, not the option's original index, so the caller must
        unshuffle the selected id back to an original index before
        recording it as an answer.
        """
        from app.services.quiz_shuffle import shuffled_options

        if not lesson.quiz or question_num >= len(lesson.quiz):
            raise ValueError(f"Invalid question number {question_num}")

        quiz_item = lesson.quiz[question_num]
        options = shuffled_options(quiz_item["options"], order)
        cleaned = [cls._EMBEDDED_LETTER_PREFIX.sub("", opt) for opt in options]

        lines = [f"❓ Question {question_num + 1}/5", "", quiz_item["question"], ""]
        buttons = []
        for i, opt in enumerate(cleaned):
            letter = chr(65 + i)
            lines.append(f"{letter}. {opt}")
            buttons.append(Button(f"ans_{question_num}_{i}", letter, opt))
        lines.append("")
        lines.append("Tap an option or reply with the letter.")

        return OutboundMessage(
            kind="quiz",
            text="\n".join(lines),
            buttons=buttons,
            meta={"lesson_id": lesson.id, "question": question_num, "total": 5},
        )

    @staticmethod
    def build_quiz_result_message(score: float, passed: bool, attempt: int, can_retry: bool) -> OutboundMessage:
        if passed:
            return OutboundMessage(
                kind="result",
                text=(
                    "🎉 *Congratulations!*\n\n"
                    f"You scored {score:.0f}% on your quiz!\n"
                    f"Attempt: {attempt}/3\n\n"
                    "✅ Lesson completed! Moving to next lesson..."
                ),
                meta={"passed": True, "score": score, "attempt": attempt},
            )

        retry_msg = "\n\n📝 Tap *Retry* or reply *RETRY* to try again!" if can_retry else "\n\n❌ Maximum attempts reached."
        return OutboundMessage(
            kind="result",
            text=(
                "😔 *Not quite there yet*\n\n"
                f"You scored {score:.0f}%\n"
                "You need 60% to pass (3/5 correct)\n"
                f"Attempt: {attempt}/3"
                f"{retry_msg}"
            ),
            buttons=[Button("retry", "🔁 Retry quiz")] if can_retry else [],
            meta={"passed": False, "score": score, "attempt": attempt, "can_retry": can_retry},
        )

    @staticmethod
    def build_day_complete_message(day: int, lessons_completed: int, needs_name: bool = False) -> OutboundMessage:
        """
        Day completion celebration.

        needs_name: Day 7 only — True if the learner hasn't yet provided the
        name that goes on their certificate (never asked before this moment,
        to avoid collecting it from the ~94% of signups who never reach Day 7).
        """
        buttons: List[Button] = []
        if day < 7:
            cta = f"Tap *Next day* or reply *NEXT* to continue to Day {day + 1}!"
            buttons = [Button("next", f"➡️ Next: Day {day + 1}")]
        elif needs_name:
            cta = "What name should appear on your certificate? Reply with your full name."
        else:
            cta = "Tap *Get certificate* or reply *CERTIFICATE* to get your certificate!"
            buttons = [Button("certificate", "🎓 Get certificate")]

        return OutboundMessage(
            kind="text",
            text=(
                f"🎊 *DAY {day} COMPLETE!* 🎊\n\n"
                f"Congratulations! You've finished all {lessons_completed} lessons for Day {day}!\n\n"
                "📈 Your Progress:\n"
                f"✅ Day {day} - DONE\n"
                f"📚 {lessons_completed} lessons completed\n\n"
                f"{'🏆 Keep going! Only ' + str(7 - day) + ' days left!' if day < 7 else '🎓 COURSE COMPLETE!'}\n\n"
                f"{cta}"
            ),
            buttons=buttons,
            meta={"day": day, "needs_name": needs_name},
        )

    # Localized copy for the inactivity nudge (body + button title).
    REMINDER_COPY = {
        Language.ENGLISH: {
            "body": (
                "👋 You're doing great! Day {day} of your FREE AI course is waiting for you.\n\n"
                "🎓 Only {days_left} day{plural} left to earn your MNAIR certificate.\n\n"
                "Tap Continue to pick up where you stopped."
            ),
            "button": "Continue",
        },
        Language.PIDGIN: {
            "body": (
                "👋 You dey do well! Day {day} of your FREE AI course dey wait for you.\n\n"
                "🎓 Na only {days_left} day{plural} remain make you collect your MNAIR certificate.\n\n"
                "Press Continue make you carry on."
            ),
            "button": "Continue",
        },
        Language.HAUSA: {
            "body": (
                "👋 Kana kokari sosai! Rana ta {day} na kwas dinka na AI KYAUTA tana jiranka.\n\n"
                "🎓 Sauran rana {days_left} kacal ka samu takardar shaidar MNAIR.\n\n"
                "Danna Ci gaba don ci gaba da karatu."
            ),
            "button": "Ci gaba",
        },
        Language.YORUBA: {
            "body": (
                "👋 O ń ṣe dáadáa! Ọjọ́ {day} nínú ẹ̀kọ́ AI ỌFẸ́ rẹ ń dúró dè ọ́.\n\n"
                "🎓 Ọjọ́ {days_left} péré ló kù kí o gba ìwé ẹ̀rí MNAIR rẹ.\n\n"
                "Tẹ Tẹ̀síwájú láti bẹ̀rẹ̀ láti ibi tí o dúró sí."
            ),
            "button": "Tẹ̀síwájú",
        },
        Language.IGBO: {
            "body": (
                "👋 Ị na-eme nke ọma! Ụbọchị {day} nke ọzụzụ AI EFU gị na-echere gị.\n\n"
                "🎓 Ọ bụ naanị ụbọchị {days_left} fọdụrụ ka ị nweta asambodo MNAIR gị.\n\n"
                "Pịa Gaa n'ihu ka ị malite ebe ị kwụsịrị."
            ),
            "button": "Gaa n'ihu",
        },
    }

    @classmethod
    def build_reminder_message(cls, language: Language, current_day: int, days_left: int) -> OutboundMessage:
        """Inactivity nudge with a Continue button that re-enters the flow via continue_learning."""
        copy = cls.REMINDER_COPY.get(language, cls.REMINDER_COPY[Language.ENGLISH])
        body = copy["body"].format(
            day=current_day,
            days_left=days_left,
            plural="s" if days_left != 1 else "",
        )
        return OutboundMessage(
            kind="text",
            text=body,
            buttons=[Button("continue_learning", copy["button"])],
            meta={"reminder": True, "day": current_day},
        )

    @staticmethod
    def build_progress_message(current_day: int, lessons_completed: int, total_lessons: int, completion_pct: float) -> OutboundMessage:
        progress_bar = "█" * int(completion_pct / 10) + "░" * (10 - int(completion_pct / 10))
        return OutboundMessage(
            kind="text",
            text=(
                "📊 *Your Progress*\n\n"
                f"Current Day: *{current_day}/7*\n"
                f"Lessons Completed: *{lessons_completed}/{total_lessons}*\n\n"
                f"Progress: {progress_bar} {completion_pct:.1f}%\n\n"
                "Keep it up! 🚀"
            ),
            meta={"progress": completion_pct},
        )

    @staticmethod
    def build_certificate_message(name: str, certificate_id: str, verify_url: str) -> OutboundMessage:
        return OutboundMessage(
            kind="certificate",
            text=(
                f"🎓 Congratulations, {name}! Your MNAIR certificate is ready.\n\n"
                f"Code: {certificate_id}\n"
                f"Download: {verify_url}"
            ),
            buttons=[Button("open_certificate", "📜 Open certificate", verify_url)],
            meta={"certificate_id": certificate_id, "url": verify_url},
        )
