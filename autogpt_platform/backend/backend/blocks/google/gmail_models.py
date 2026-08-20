"""Gmail block data models."""

from typing import List

from pydantic import BaseModel, Field


class Attachment(BaseModel):
    filename: str
    content_type: str
    size: int
    attachment_id: str


class Email(BaseModel):
    threadId: str
    labelIds: list[str]
    id: str
    subject: str
    snippet: str
    from_: str
    to: list[str]  # List of recipient email addresses
    cc: list[str] = Field(default_factory=list)  # CC recipients
    bcc: list[str] = Field(
        default_factory=list
    )  # BCC recipients (rarely available in received emails)
    date: str
    body: str = ""  # Default to an empty string
    sizeEstimate: int
    attachments: List[Attachment]


class Thread(BaseModel):
    id: str
    messages: list[Email]
    historyId: str


class GmailSendResult(BaseModel):
    id: str
    status: str


class GmailDraftResult(BaseModel):
    id: str
    message_id: str
    status: str


class GmailLabelResult(BaseModel):
    label_id: str
    status: str


class Profile(BaseModel):
    emailAddress: str
    messagesTotal: int
    threadsTotal: int
    historyId: str


