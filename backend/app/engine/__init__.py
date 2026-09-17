"""
Channel-agnostic conversation engine.

Every free learner channel (Telegram, the web learner app) drives the same
7-day curriculum through ConversationEngine. Channels only translate inbound
events into (text, interactive_id) and outbound OutboundMessage objects into
their own wire format. No channel owns the state machine.
"""

from app.engine.messages import Button, OutboundMessage
from app.engine.builder import MessageBuilder
from app.engine.conversation import ConversationEngine
from app.engine.identity import get_or_create_learner, get_or_create_conversation

__all__ = [
    "Button",
    "OutboundMessage",
    "MessageBuilder",
    "ConversationEngine",
    "get_or_create_learner",
    "get_or_create_conversation",
]
