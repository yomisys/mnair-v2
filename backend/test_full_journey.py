#!/usr/bin/env python
"""
WhatsApp Learning Journey Simulator
Automates testing the complete 7-day MNAIR learning experience
"""

import requests
import json
import time
from typing import Dict, List

BASE_URL = "http://localhost:8000/api/v1/test/whatsapp"
PHONE = "+2349876543210"  # Test phone number

class WhatsAppSimulator:
    def __init__(self, phone: str):
        self.phone = phone
        self.session = requests.Session()

    def send_message(self, message: str, description: str = "") -> Dict:
        """Send a message and return the response"""
        print(f"\n{'='*60}")
        print(f"📱 {description}")
        print(f"   Sending: {message}")

        response = self.session.post(
            f"{BASE_URL}/simulate",
            json={"phone_number": self.phone, "message": message}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Status: {data['status']}")
            print(f"   State: {data['conversation_state']}")
            print(f"   Current Day: {data['current_day']}")

            # Show messages sent
            for msg in data.get('messages_sent', []):
                msg_body = msg['message']
                if 'text' in msg_body:
                    text = msg_body['text']['body'][:200]
                    print(f"\n   📨 Message Preview:")
                    print(f"   {text}...")
                elif 'interactive' in msg_body:
                    print(f"   📨 Interactive message sent")

            # Show next actions
            if data.get('next_actions'):
                print(f"\n   Next actions:")
                for action in data['next_actions'][:3]:
                    print(f"      • {action}")

            return data
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"   {response.text}")
            return {}

    def get_user_state(self) -> Dict:
        """Get current user state"""
        response = self.session.get(f"{BASE_URL}/user/{self.phone}")
        if response.status_code == 200:
            return response.json()
        return {}

    def complete_quiz(self, lesson_number: int) -> bool:
        """Complete a quiz by answering all 5 questions"""
        print(f"\n{'='*60}")
        print(f"📝 Starting Quiz for Lesson {lesson_number}")

        # Start quiz
        self.send_message("QUIZ", f"Starting quiz for lesson {lesson_number}")

        # Answer 5 questions (using correct answers)
        # In a real scenario, you'd parse the questions and select answers
        # For testing, we'll answer with option B for all (usually correct)
        correct_answers = [1, 2, 1, 2, 1]  # Mix of answers

        for q in range(5):
            answer = f"ans_{q}_{correct_answers[q]}"
            self.send_message(
                answer,
                f"Answering question {q+1}/5 with option {chr(65+correct_answers[q])}"
            )
            time.sleep(0.5)  # Small delay to simulate user

        return True

    def complete_day(self, day: int) -> bool:
        """Complete all 5 lessons for a day"""
        print(f"\n{'#'*60}")
        print(f"📅 COMPLETING DAY {day}")
        print(f"{'#'*60}")

        for lesson in range(1, 6):
            print(f"\n🎓 Lesson {lesson}/5")

            # Get lesson
            if lesson == 1:
                # First lesson is delivered after language selection
                print("   (Lesson already delivered)")
            else:
                self.send_message("NEXT", f"Requesting Lesson {lesson}")

            time.sleep(1)

            # Complete quiz
            self.complete_quiz(lesson)

            time.sleep(1)

        print(f"\n✅ Day {day} completed!")
        return True

    def run_full_journey(self):
        """Run the complete 7-day learning journey"""
        print("\n" + "="*60)
        print("🚀 STARTING FULL 7-DAY MNAIR LEARNING JOURNEY")
        print("="*60)

        # Step 1: Start conversation
        self.send_message("START", "Step 1: Starting conversation")
        time.sleep(1)

        # Step 2: Select language
        self.send_message("lang_en", "Step 2: Selecting English language")
        time.sleep(1)

        # Step 3-9: Complete all 7 days
        for day in range(1, 8):
            self.complete_day(day)

            if day < 7:
                # Advance to next day
                print(f"\n⏭️  Advancing to Day {day+1}")
                self.send_message("NEXT", f"Advancing to Day {day+1}")
                time.sleep(2)

        # Final state
        print("\n" + "="*60)
        print("🎉 JOURNEY COMPLETE!")
        print("="*60)

        state = self.get_user_state()
        print(f"\n📊 Final User State:")
        print(f"   Name: {state.get('name')}")
        print(f"   Current Day: {state.get('current_day')}")
        print(f"   Language: {state.get('language')}")
        print(f"   State: {state.get('conversation_state')}")
        print(f"   Active: {state.get('is_active')}")

        print("\n✨ User should now be eligible for certificate!")


def main():
    """Main function"""
    print("\n" + "="*60)
    print("WhatsApp Learning Journey Simulator")
    print("Testing MNAIR Platform - 7-Day AI Literacy Program")
    print("="*60)

    # Create simulator
    sim = WhatsAppSimulator(PHONE)

    # Check if backend is running
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ Backend not running! Please start the backend first.")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend! Please ensure it's running on port 8000.")
        return

    print("\n✅ Backend is running!")
    print(f"📱 Test phone number: {PHONE}")

    # Ask user what to test
    print("\n" + "-"*60)
    print("What would you like to test?")
    print("  1. Full 7-day journey (automated)")
    print("  2. Single day only")
    print("  3. Quick test (Start + Language + 1 Lesson + Quiz)")
    print("  4. View current user state")
    print("-"*60)

    choice = input("\nEnter choice (1-4) or press Enter for option 3: ").strip() or "3"

    if choice == "1":
        print("\n⚠️  This will take several minutes...")
        confirm = input("Continue? (y/n): ").strip().lower()
        if confirm == 'y':
            sim.run_full_journey()

    elif choice == "2":
        day = input("Which day (1-7)? ").strip() or "1"
        sim.send_message("START", "Starting conversation")
        time.sleep(1)
        sim.send_message("lang_en", "Selecting English")
        time.sleep(1)
        sim.complete_day(int(day))

    elif choice == "3":
        print("\n🏃 Running quick test...")
        sim.send_message("START", "Starting conversation")
        time.sleep(1)
        sim.send_message("lang_en", "Selecting English language")
        time.sleep(1)
        sim.send_message("QUIZ", "Starting first quiz")
        time.sleep(1)
        # Answer first 2 questions
        sim.send_message("ans_0_1", "Answering Q1 (Option B)")
        time.sleep(1)
        sim.send_message("ans_1_2", "Answering Q2 (Option C)")

        print("\n✅ Quick test complete!")
        print("   You can continue manually or run full test.")

    elif choice == "4":
        state = sim.get_user_state()
        print(f"\n📊 Current User State:")
        print(json.dumps(state, indent=2))

    print("\n" + "="*60)
    print("✨ Test session complete!")
    print("="*60)


if __name__ == "__main__":
    main()
