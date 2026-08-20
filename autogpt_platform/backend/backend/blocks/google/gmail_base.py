"""Shared Gmail block base class."""

import asyncio
import base64
from abc import ABC

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend.blocks.google.gmail_models import Attachment
from backend.data.block import Block
from backend.util.settings import Settings

from ._auth import GoogleCredentials

settings = Settings()


class GmailBase(Block, ABC):
    """Base class for Gmail blocks with common functionality."""

    def _build_service(self, credentials: GoogleCredentials, **kwargs):
        creds = Credentials(
            token=(
                credentials.access_token.get_secret_value()
                if credentials.access_token
                else None
            ),
            refresh_token=(
                credentials.refresh_token.get_secret_value()
                if credentials.refresh_token
                else None
            ),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.secrets.google_client_id,
            client_secret=settings.secrets.google_client_secret,
            scopes=credentials.scopes,
        )
        return build("gmail", "v1", credentials=creds)

    async def _get_email_body(self, msg, service):
        """Extract email body content with support for multipart messages and HTML conversion."""
        text = await self._walk_for_body(msg["payload"], msg["id"], service)
        return text or "This email does not contain a readable body."

    async def _walk_for_body(self, part, msg_id, service, depth=0):
        """Recursively walk through email parts to find readable body content."""
        # Prevent infinite recursion by limiting depth
        if depth > 10:
            return None

        mime_type = part.get("mimeType", "")
        body = part.get("body", {})

        # Handle text/plain content
        if mime_type == "text/plain" and body.get("data"):
            return self._decode_base64(body["data"])

        # Handle text/html content (convert to plain text)
        if mime_type == "text/html" and body.get("data"):
            html_content = self._decode_base64(body["data"])
            if html_content:
                try:
                    import html2text

                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = True
                    return h.handle(html_content)
                except ImportError:
                    # Fallback: return raw HTML if html2text is not available
                    return html_content

        # Handle content stored as attachment
        if body.get("attachmentId"):
            attachment_data = await self._download_attachment_body(
                body["attachmentId"], msg_id, service
            )
            if attachment_data:
                return self._decode_base64(attachment_data)

        # Recursively search in parts
        for sub_part in part.get("parts", []):
            text = await self._walk_for_body(sub_part, msg_id, service, depth + 1)
            if text:
                return text

        return None

    def _decode_base64(self, data):
        """Safely decode base64 URL-safe data with proper padding."""
        if not data:
            return None
        try:
            # Add padding if necessary
            missing_padding = len(data) % 4
            if missing_padding:
                data += "=" * (4 - missing_padding)
            return base64.urlsafe_b64decode(data).decode("utf-8")
        except Exception:
            return None

    async def _download_attachment_body(self, attachment_id, msg_id, service):
        """Download attachment content when email body is stored as attachment."""
        try:
            attachment = await asyncio.to_thread(
                lambda: service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=attachment_id)
                .execute()
            )
            return attachment.get("data")
        except Exception:
            return None

    async def _get_attachments(self, service, message):
        attachments = []
        if "parts" in message["payload"]:
            for part in message["payload"]["parts"]:
                if part.get("filename"):
                    attachment = Attachment(
                        filename=part["filename"],
                        content_type=part["mimeType"],
                        size=int(part["body"].get("size", 0)),
                        attachment_id=part["body"]["attachmentId"],
                    )
                    attachments.append(attachment)
        return attachments

    async def download_attachment(self, service, message_id: str, attachment_id: str):
        attachment = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        file_data = base64.urlsafe_b64decode(attachment["data"].encode("UTF-8"))
        return file_data

    async def _get_label_id(self, service, label_name: str) -> str | None:
        """Get label ID by name from Gmail."""
        results = await asyncio.to_thread(
            lambda: service.users().labels().list(userId="me").execute()
        )
        labels = results.get("labels", [])
        for label in labels:
            if label["name"] == label_name:
                return label["id"]
        return None


