"""
Test WhatsApp Simulator
Allows testing the WhatsApp lesson flow without actual WhatsApp Business API
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.channels.whatsapp import WhatsAppWebhookHandler
from app.config import Settings, get_settings


router = APIRouter(prefix="/api/v1/test", tags=["Testing"])


class SimulateMessageRequest(BaseModel):
    """Request to simulate a WhatsApp message"""
    phone_number: str
    message: str


class SimulateMessageResponse(BaseModel):
    """Response showing what would be sent"""
    status: str
    user_id: int
    conversation_state: str
    messages_sent: List[dict]


@router.post("/whatsapp/simulate", response_model=dict)
async def simulate_whatsapp_message(
    request: SimulateMessageRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Simulate sending a WhatsApp message to the bot

    This endpoint allows you to test the WhatsApp flow without actual WhatsApp.
    It will show you what messages would be sent back to the user.

    Example usage:
    1. Start conversation: {"phone_number": "+2348012345678", "message": "START"}
    2. Select language: {"phone_number": "+2348012345678", "message": "lang_en"}
    3. Request lesson: {"phone_number": "+2348012345678", "message": "NEXT"}
    4. Start quiz: {"phone_number": "+2348012345678", "message": "QUIZ"}
    """
    # Create handler
    handler = WhatsAppWebhookHandler(settings, db)

    # Store messages that would be sent
    sent_messages = []

    # Override send_whatsapp_message to capture instead of sending
    original_send = handler.send_whatsapp_message
    async def capture_send(phone: str, message: dict):
        sent_messages.append({
            "to": phone,
            "message": message
        })
        return True

    handler.send_whatsapp_message = capture_send

    # Handle the message
    try:
        # Check if message is an interactive button ID
        if request.message.startswith("lang_") or request.message.startswith("ans_"):
            await handler.handle_message(
                request.phone_number,
                "",
                "interactive",
                request.message
            )
        else:
            await handler.handle_message(
                request.phone_number,
                request.message,
                "text"
            )

        # Get updated user and conversation state
        user = await handler.get_or_create_user(request.phone_number)
        conversation = await handler.get_or_create_conversation(user.id, request.phone_number)

        return {
            "status": "success",
            "user_id": user.id,
            "user_name": user.name,
            "current_day": user.current_day,
            "language": user.language.value,
            "conversation_state": conversation.current_state.value,
            "messages_sent": sent_messages,
            "next_actions": _get_next_actions(conversation.current_state.value, sent_messages)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error simulating message: {str(e)}")


def _get_next_actions(state: str, messages: list) -> List[str]:
    """Suggest next actions based on conversation state"""
    if state == "awaiting_language":
        return [
            "Send: lang_en (for English)",
            "Send: lang_pid (for Pidgin)",
            "Send: lang_ha (for Hausa)",
            "Send: lang_yo (for Yoruba)",
            "Send: lang_ig (for Igbo)"
        ]
    elif state == "in_lesson":
        # Check if lesson was just delivered
        if any("Lesson" in str(m) for m in messages):
            return [
                "Send: QUIZ (to start the quiz)",
                "Send: NEXT (to skip to next lesson - testing only)"
            ]
        else:
            return ["Send: NEXT (to get next lesson)"]
    elif state == "awaiting_quiz":
        # Extract question number from messages
        return [
            "Send: ans_0_0 (select option A)",
            "Send: ans_0_1 (select option B)",
            "Send: ans_0_2 (select option C)",
            "Send: ans_0_3 (select option D)"
        ]
    elif state == "day_complete":
        return ["Send: NEXT (to advance to next day)"]
    else:
        return ["Send: START (to begin learning)"]


@router.get("/whatsapp/user/{phone_number}")
async def get_user_state(
    phone_number: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Get current state of a user in the WhatsApp flow
    """
    handler = WhatsAppWebhookHandler(settings, db)

    try:
        user = await handler.get_or_create_user(phone_number)
        conversation = await handler.get_or_create_conversation(user.id, phone_number)

        return {
            "user_id": user.id,
            "name": user.name,
            "phone_number": user.phone_number,
            "language": user.language.value,
            "current_day": user.current_day,
            "conversation_state": conversation.current_state.value,
            "context": conversation.context,
            "is_active": conversation.is_active
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user state: {str(e)}")
