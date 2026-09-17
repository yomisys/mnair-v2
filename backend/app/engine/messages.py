"""
Outbound message model shared by every channel.

Text uses a tiny markup: *bold*. Each channel renderer converts it (Telegram
-> <b>, web -> <strong>). Buttons carry a stable id that the learner's tap
sends back as `interactive_id`; the engine treats those ids exactly like the
typed keyword equivalents (QUIZ, NEXT, CERTIFICATE, ...).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Button:
    id: str
    title: str
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "title": self.title, "description": self.description}


@dataclass
class OutboundMessage:
    text: str
    buttons: List[Button] = field(default_factory=list)
    kind: str = "text"  # text | lesson | quiz | choice | result | certificate
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "buttons": [b.to_dict() for b in self.buttons],
            "meta": self.meta,
        }

    @staticmethod
    def text_only(text: str, kind: str = "text", **meta: Any) -> "OutboundMessage":
        return OutboundMessage(text=text, kind=kind, meta=meta)


def button_ids(message: OutboundMessage) -> List[str]:
    return [b.id for b in message.buttons]


def find_button(message: OutboundMessage, button_id: str) -> Optional[Button]:
    for b in message.buttons:
        if b.id == button_id:
            return b
    return None
