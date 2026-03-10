"""Pydantic models for Telegram webhook payloads (lightweight subset)."""

from pydantic import BaseModel


class TelegramChat(BaseModel):
    id: int


class TelegramPhotoSize(BaseModel):
    file_id: str
    file_unique_id: str
    width: int
    height: int


class TelegramMessage(BaseModel):
    message_id: int
    chat: TelegramChat
    text: str | None = None
    photo: list[TelegramPhotoSize] | None = None


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
