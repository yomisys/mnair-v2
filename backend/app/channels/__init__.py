"""
Communication Channels for MNAIR Platform

Free learner channels (drive app.engine.ConversationEngine):
  telegram  — Telegram Bot API (webhook or long-polling)
  web       — browser learner app + Web Push reminders (webpush.py)

Paid / legacy channels:
  ussd      — Africa's Talking USSD (*384*8080#)
  sms       — Termii SMS (reminder fallback, opt-in via SMS_REMINDERS_ENABLED)
  kingschat — browser-automation channel (feature-flagged)

notify.py routes outbound reminders/certificate notices free-first.
"""
