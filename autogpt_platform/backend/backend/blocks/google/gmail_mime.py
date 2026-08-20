"""MIME helpers for Gmail blocks."""

import asyncio
import base64
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.policy import SMTP
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Literal, Optional

from backend.util.file import get_exec_file_path, store_media_file


NO_WRAP_POLICY = SMTP.clone(max_line_length=0)


def serialize_email_recipients(recipients: list[str]) -> str:
    """Serialize recipients list to comma-separated string."""
    return ", ".join(recipients)


def _make_mime_text(
    body: str,
    content_type: Optional[Literal["auto", "plain", "html"]] = None,
) -> MIMEText:
    """Create a MIMEText object with proper content type and no hard-wrap for plain text.

    This function addresses the common Gmail issue where plain text emails are
    hard-wrapped at 78 characters, creating awkward narrow columns in modern
    email clients. It also ensures HTML emails are properly identified and sent
    with the correct MIME type.

    Args:
        body: The email body content (plain text or HTML)
        content_type: The content type - "auto" (default), "plain", or "html"
                     - "auto" or None: Auto-detects based on presence of HTML tags
                     - "plain": Forces plain text format without line wrapping
                     - "html": Forces HTML format with standard wrapping

    Returns:
        MIMEText object configured with:
        - Appropriate content subtype (plain or html)
        - UTF-8 charset for proper Unicode support
        - No-wrap policy for plain text (max_line_length=0)
        - Standard wrapping for HTML content

    Examples:
        >>> # Plain text email without wrapping
        >>> mime = _make_mime_text("Long paragraph...", "plain")
        >>> # HTML email with auto-detection
        >>> mime = _make_mime_text("<p>Hello</p>", "auto")
    """
    # Auto-detect content type if not specified or "auto"
    if content_type is None or content_type == "auto":
        # Simple heuristic: check for HTML tags in first 500 chars
        looks_html = "<" in body[:500] and ">" in body[:500]
        actual_type = "html" if looks_html else "plain"
    else:
        actual_type = content_type

    # Create MIMEText with appropriate settings
    if actual_type == "html":
        # HTML content - normal wrapping is OK
        return MIMEText(body, _subtype="html", _charset="utf-8")
    else:
        # Plain text - use no-wrap policy to prevent 78-char hard-wrap
        return MIMEText(body, _subtype="plain", _charset="utf-8", policy=NO_WRAP_POLICY)


async def create_mime_message(
    input_data,
    graph_exec_id: str,
    user_id: str,
) -> str:
    """Create a MIME message with attachments and return base64-encoded raw message."""

    message = MIMEMultipart()
    message["to"] = serialize_email_recipients(input_data.to)
    message["subject"] = input_data.subject

    if input_data.cc:
        message["cc"] = ", ".join(input_data.cc)
    if input_data.bcc:
        message["bcc"] = ", ".join(input_data.bcc)

    # Use the new helper function with content_type if available
    content_type = getattr(input_data, "content_type", None)
    message.attach(_make_mime_text(input_data.body, content_type))

    # Handle attachments if any
    if input_data.attachments:
        for attach in input_data.attachments:
            local_path = await store_media_file(
                user_id=user_id,
                graph_exec_id=graph_exec_id,
                file=attach,
                return_content=False,
            )
            abs_path = get_exec_file_path(graph_exec_id, local_path)
            part = MIMEBase("application", "octet-stream")
            with open(abs_path, "rb") as f:
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={Path(abs_path).name}",
            )
            message.attach(part)

    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


async def _build_reply_message(
    service, input_data, graph_exec_id: str, user_id: str
) -> tuple[str, str]:
    """
    Builds a reply MIME message for Gmail threads.

    Returns:
        tuple: (base64-encoded raw message, threadId)
    """
    # Get parent message for reply context
    parent = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .get(
            userId="me",
            id=input_data.parentMessageId,
            format="metadata",
            metadataHeaders=[
                "Subject",
                "References",
                "Message-ID",
                "From",
                "To",
                "Cc",
                "Reply-To",
            ],
        )
        .execute()
    )

    # Build headers dictionary, preserving all values for duplicate headers
    headers = {}
    for h in parent.get("payload", {}).get("headers", []):
        name = h["name"].lower()
        value = h["value"]
        if name in headers:
            # For duplicate headers, keep the first occurrence (most relevant for reply context)
            continue
        headers[name] = value

    # Determine recipients if not specified
    if not (input_data.to or input_data.cc or input_data.bcc):
        if input_data.replyAll:
            recipients = [parseaddr(headers.get("from", ""))[1]]
            recipients += [addr for _, addr in getaddresses([headers.get("to", "")])]
            recipients += [addr for _, addr in getaddresses([headers.get("cc", "")])]
            # Use dict.fromkeys() for O(n) deduplication while preserving order
            input_data.to = list(dict.fromkeys(filter(None, recipients)))
        else:
            # Check Reply-To header first, fall back to From header
            reply_to = headers.get("reply-to", "")
            from_addr = headers.get("from", "")
            sender = parseaddr(reply_to if reply_to else from_addr)[1]
            input_data.to = [sender] if sender else []

    # Set subject with Re: prefix if not already present
    if input_data.subject:
        subject = input_data.subject
    else:
        parent_subject = headers.get("subject", "").strip()
        # Only add "Re:" if not already present (case-insensitive check)
        if parent_subject.lower().startswith("re:"):
            subject = parent_subject
        else:
            subject = f"Re: {parent_subject}" if parent_subject else "Re:"

    # Build references header for proper threading
    references = headers.get("references", "").split()
    if headers.get("message-id"):
        references.append(headers["message-id"])

    # Create MIME message
    msg = MIMEMultipart()
    if input_data.to:
        msg["To"] = ", ".join(input_data.to)
    if input_data.cc:
        msg["Cc"] = ", ".join(input_data.cc)
    if input_data.bcc:
        msg["Bcc"] = ", ".join(input_data.bcc)
    msg["Subject"] = subject
    if headers.get("message-id"):
        msg["In-Reply-To"] = headers["message-id"]
    if references:
        msg["References"] = " ".join(references)

    # Use the helper function for consistent content type handling
    msg.attach(_make_mime_text(input_data.body, input_data.content_type))

    # Handle attachments
    for attach in input_data.attachments:
        local_path = await store_media_file(
            user_id=user_id,
            graph_exec_id=graph_exec_id,
            file=attach,
            return_content=False,
        )
        abs_path = get_exec_file_path(graph_exec_id, local_path)
        part = MIMEBase("application", "octet-stream")
        with open(abs_path, "rb") as f:
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", f"attachment; filename={Path(abs_path).name}"
        )
        msg.attach(part)

    # Encode message
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw, input_data.threadId


