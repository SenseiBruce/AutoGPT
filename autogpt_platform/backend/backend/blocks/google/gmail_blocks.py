"""Gmail integration blocks public surface."""

from backend.blocks.google.gmail_base import GmailBase
from backend.blocks.google.gmail_mail import (
    GmailAddLabelBlock,
    GmailCreateDraftBlock,
    GmailListLabelsBlock,
    GmailReadBlock,
    GmailRemoveLabelBlock,
    GmailSendBlock,
)
from backend.blocks.google.gmail_thread import (
    GmailDraftReplyBlock,
    GmailForwardBlock,
    GmailGetProfileBlock,
    GmailGetThreadBlock,
    GmailReplyBlock,
)

__all__ = [
    "GmailAddLabelBlock",
    "GmailBase",
    "GmailCreateDraftBlock",
    "GmailDraftReplyBlock",
    "GmailForwardBlock",
    "GmailGetProfileBlock",
    "GmailGetThreadBlock",
    "GmailListLabelsBlock",
    "GmailReadBlock",
    "GmailRemoveLabelBlock",
    "GmailReplyBlock",
    "GmailSendBlock",
]
