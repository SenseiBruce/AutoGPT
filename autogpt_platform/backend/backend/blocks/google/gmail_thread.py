"""Gmail thread, reply, profile, and forward blocks."""

import asyncio
import base64
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Literal, Optional

from backend.blocks.google.gmail_base import GmailBase
from backend.blocks.google.gmail_mime import _build_reply_message, _make_mime_text
from backend.blocks.google.gmail_models import (
    Email,
    Profile,
    Thread,
)
from backend.data.block import BlockCategory, BlockOutput, BlockSchemaInput, BlockSchemaOutput
from backend.data.model import SchemaField
from backend.util.file import MediaFileType, get_exec_file_path, store_media_file

from ._auth import (
    GOOGLE_OAUTH_IS_CONFIGURED,
    TEST_CREDENTIALS,
    TEST_CREDENTIALS_INPUT,
    GoogleCredentials,
    GoogleCredentialsField,
    GoogleCredentialsInput,
)

class GmailGetThreadBlock(GmailBase):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.readonly"]
        )
        threadId: str = SchemaField(description="Gmail thread ID")

    class Output(BlockSchemaOutput):
        thread: Thread = SchemaField(
            description="Gmail thread with decoded message bodies"
        )

    def __init__(self):
        super().__init__(
            id="21a79166-9df7-4b5f-9f36-96f639d86112",
            description="Get a full Gmail thread by ID",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailGetThreadBlock.Input,
            output_schema=GmailGetThreadBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={"threadId": "t1", "credentials": TEST_CREDENTIALS_INPUT},
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "thread",
                    {
                        "id": "188199feff9dc907",
                        "messages": [
                            {
                                "id": "188199feff9dc907",
                                "to": ["nick@example.co"],
                                "cc": [],
                                "bcc": [],
                                "body": "This email does not contain a text body.",
                                "date": "Thu, 17 Jul 2025 19:22:36 +0100",
                                "from_": "bent@example.co",
                                "snippet": "have a funny looking car -- Bently, Community Administrator For AutoGPT",
                                "subject": "car",
                                "threadId": "188199feff9dc907",
                                "labelIds": ["INBOX"],
                                "attachments": [
                                    {
                                        "size": 5694,
                                        "filename": "frog.jpg",
                                        "content_type": "image/jpeg",
                                        "attachment_id": "ANGjdJ_f777CvJ37TdHYSPIPPqJ0HVNgze1uM8alw5iiqTqAVXjsmBWxOWXrY3Z4W4rEJHfAcHVx54_TbtcZIVJJEqJfAD5LoUOK9_zKCRwwcTJ5TGgjsXcZNSnOJNazM-m4E6buo2-p0WNcA_hqQvuA36nzS31Olx3m2x7BaG1ILOkBcjlKJl4KCcR0AvnfK0S02k8i-bZVqII7XXrNp21f1BDolxH7tiEhkz3d5p-5Lbro24olgOWQwQk0SCJsTWWBMCVgbxU7oLt1QmPcjANxfpvh69Qfap3htvQxFa9P08NDI2YqQkry9yPxVR7ZBJQWrqO35EWmhNySEiX5pfG8SDRmfP9O_BqxTH35nEXmSOvZH9zb214iM-zfSoPSU1F5Fo71",
                                    }
                                ],
                                "sizeEstimate": 14099,
                            }
                        ],
                        "historyId": "645006",
                    },
                )
            ],
            test_mock={
                "_get_thread": lambda *args, **kwargs: {
                    "id": "188199feff9dc907",
                    "messages": [
                        {
                            "id": "188199feff9dc907",
                            "to": ["nick@example.co"],
                            "cc": [],
                            "bcc": [],
                            "body": "This email does not contain a text body.",
                            "date": "Thu, 17 Jul 2025 19:22:36 +0100",
                            "from_": "bent@example.co",
                            "snippet": "have a funny looking car -- Bently, Community Administrator For AutoGPT",
                            "subject": "car",
                            "threadId": "188199feff9dc907",
                            "labelIds": ["INBOX"],
                            "attachments": [
                                {
                                    "size": 5694,
                                    "filename": "frog.jpg",
                                    "content_type": "image/jpeg",
                                    "attachment_id": "ANGjdJ_f777CvJ37TdHYSPIPPqJ0HVNgze1uM8alw5iiqTqAVXjsmBWxOWXrY3Z4W4rEJHfAcHVx54_TbtcZIVJJEqJfAD5LoUOK9_zKCRwwcTJ5TGgjsXcZNSnOJNazM-m4E6buo2-p0WNcA_hqQvuA36nzS31Olx3m2x7BaG1ILOkBcjlKJl4KCcR0AvnfK0S02k8i-bZVqII7XXrNp21f1BDolxH7tiEhkz3d5p-5Lbro24olgOWQwQk0SCJsTWWBMCVgbxU7oLt1QmPcjANxfpvh69Qfap3htvQxFa9P08NDI2YqQkry9yPxVR7ZBJQWrqO35EWmhNySEiX5pfG8SDRmfP9O_BqxTH35nEXmSOvZH9zb214iM-zfSoPSU1F5Fo71",
                                }
                            ],
                            "sizeEstimate": 14099,
                        }
                    ],
                    "historyId": "645006",
                }
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        thread = await self._get_thread(
            service, input_data.threadId, credentials.scopes
        )
        yield "thread", thread

    async def _get_thread(
        self, service, thread_id: str, scopes: list[str] | None
    ) -> Thread:
        scopes = [s.lower() for s in (scopes or [])]
        format_type = (
            "metadata"
            if "https://www.googleapis.com/auth/gmail.metadata" in scopes
            else "full"
        )
        thread = await asyncio.to_thread(
            lambda: service.users()
            .threads()
            .get(userId="me", id=thread_id, format=format_type)
            .execute()
        )

        parsed_messages = []
        for msg in thread.get("messages", []):
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            body = await self._get_email_body(msg, service)
            attachments = await self._get_attachments(service, msg)

            # Parse all recipients
            to_recipients = [
                addr.strip() for _, addr in getaddresses([headers.get("to", "")])
            ]
            cc_recipients = [
                addr.strip() for _, addr in getaddresses([headers.get("cc", "")])
            ]
            bcc_recipients = [
                addr.strip() for _, addr in getaddresses([headers.get("bcc", "")])
            ]

            email = Email(
                threadId=msg.get("threadId", thread_id),
                labelIds=msg.get("labelIds", []),
                id=msg.get("id"),
                subject=headers.get("subject", "No Subject"),
                snippet=msg.get("snippet", ""),
                from_=parseaddr(headers.get("from", ""))[1],
                to=to_recipients if to_recipients else [],
                cc=cc_recipients,
                bcc=bcc_recipients,
                date=headers.get("date", ""),
                body=body,
                sizeEstimate=msg.get("sizeEstimate", 0),
                attachments=attachments,
            )
            parsed_messages.append(email.model_dump())

        thread["messages"] = parsed_messages
        return thread


class GmailReplyBlock(GmailBase):
    """
    Replies to Gmail threads with intelligent content type detection.

    Features:
    - Automatic HTML detection: Replies containing HTML tags are sent as text/html
    - No hard-wrap for plain text: Plain text replies preserve natural line flow
    - Manual content type override: Use content_type parameter to force specific format
    - Reply-all functionality: Option to reply to all original recipients
    - Thread preservation: Maintains proper email threading with headers
    - Full Unicode/emoji support with UTF-8 encoding
    """

    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            [
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.readonly",
            ]
        )
        threadId: str = SchemaField(description="Thread ID to reply in")
        parentMessageId: str = SchemaField(
            description="ID of the message being replied to"
        )
        to: list[str] = SchemaField(description="To recipients", default_factory=list)
        cc: list[str] = SchemaField(description="CC recipients", default_factory=list)
        bcc: list[str] = SchemaField(description="BCC recipients", default_factory=list)
        replyAll: bool = SchemaField(
            description="Reply to all original recipients", default=False
        )
        subject: str = SchemaField(description="Email subject", default="")
        body: str = SchemaField(description="Email body (plain text or HTML)")
        content_type: Optional[Literal["auto", "plain", "html"]] = SchemaField(
            description="Content type: 'auto' (default - detects HTML), 'plain', or 'html'",
            default=None,
            advanced=True,
        )
        attachments: list[MediaFileType] = SchemaField(
            description="Files to attach", default_factory=list, advanced=True
        )

    class Output(BlockSchemaOutput):
        messageId: str = SchemaField(description="Sent message ID")
        threadId: str = SchemaField(description="Thread ID")
        message: dict = SchemaField(description="Raw Gmail message object")
        email: Email = SchemaField(
            description="Parsed email object with decoded body and attachments"
        )

    def __init__(self):
        super().__init__(
            id="12bf5a24-9b90-4f40-9090-4e86e6995e60",
            description="Reply to Gmail threads with automatic HTML detection and proper text formatting. Plain text replies maintain natural paragraph flow without 78-character line wrapping. HTML content is automatically detected and sent with correct MIME type.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailReplyBlock.Input,
            output_schema=GmailReplyBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "threadId": "t1",
                "parentMessageId": "m1",
                "body": "Thanks",
                "replyAll": False,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("messageId", "m2"),
                ("threadId", "t1"),
                ("message", {"id": "m2", "threadId": "t1"}),
                (
                    "email",
                    Email(
                        threadId="t1",
                        labelIds=[],
                        id="m2",
                        subject="",
                        snippet="",
                        from_="",
                        to=[],
                        cc=[],
                        bcc=[],
                        date="",
                        body="Thanks",
                        sizeEstimate=0,
                        attachments=[],
                    ),
                ),
            ],
            test_mock={
                "_reply": lambda *args, **kwargs: {
                    "id": "m2",
                    "threadId": "t1",
                }
            },
        )

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GoogleCredentials,
        graph_exec_id: str,
        user_id: str,
        **kwargs,
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        message = await self._reply(
            service,
            input_data,
            graph_exec_id,
            user_id,
        )
        yield "messageId", message["id"]
        yield "threadId", message.get("threadId", input_data.threadId)
        yield "message", message
        email = Email(
            threadId=message.get("threadId", input_data.threadId),
            labelIds=message.get("labelIds", []),
            id=message["id"],
            subject=input_data.subject or "",
            snippet=message.get("snippet", ""),
            from_="",  # From address would need to be retrieved from the message headers
            to=input_data.to if input_data.to else [],
            cc=input_data.cc if input_data.cc else [],
            bcc=input_data.bcc if input_data.bcc else [],
            date="",  # Date would need to be retrieved from the message headers
            body=input_data.body,
            sizeEstimate=message.get("sizeEstimate", 0),
            attachments=[],  # Attachments info not available from send response
        )
        yield "email", email

    async def _reply(
        self, service, input_data: Input, graph_exec_id: str, user_id: str
    ) -> dict:
        # Build the reply message using the shared helper
        raw, thread_id = await _build_reply_message(
            service, input_data, graph_exec_id, user_id
        )

        # Send the message
        return await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .send(userId="me", body={"threadId": thread_id, "raw": raw})
            .execute()
        )


class GmailDraftReplyBlock(GmailBase):
    """
    Creates draft replies to Gmail threads with intelligent content type detection.

    Features:
    - Automatic HTML detection: Draft replies containing HTML tags are formatted as text/html
    - No hard-wrap for plain text: Plain text draft replies preserve natural line flow
    - Manual content type override: Use content_type parameter to force specific format
    - Reply-all functionality: Option to reply to all original recipients
    - Thread preservation: Maintains proper email threading with headers
    - Full Unicode/emoji support with UTF-8 encoding
    """

    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            [
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.readonly",
            ]
        )
        threadId: str = SchemaField(description="Thread ID to reply in")
        parentMessageId: str = SchemaField(
            description="ID of the message being replied to"
        )
        to: list[str] = SchemaField(description="To recipients", default_factory=list)
        cc: list[str] = SchemaField(description="CC recipients", default_factory=list)
        bcc: list[str] = SchemaField(description="BCC recipients", default_factory=list)
        replyAll: bool = SchemaField(
            description="Reply to all original recipients", default=False
        )
        subject: str = SchemaField(description="Email subject", default="")
        body: str = SchemaField(description="Email body (plain text or HTML)")
        content_type: Optional[Literal["auto", "plain", "html"]] = SchemaField(
            description="Content type: 'auto' (default - detects HTML), 'plain', or 'html'",
            default=None,
            advanced=True,
        )
        attachments: list[MediaFileType] = SchemaField(
            description="Files to attach", default_factory=list, advanced=True
        )

    class Output(BlockSchemaOutput):
        draftId: str = SchemaField(description="Created draft ID")
        messageId: str = SchemaField(description="Draft message ID")
        threadId: str = SchemaField(description="Thread ID")
        status: str = SchemaField(description="Draft creation status")

    def __init__(self):
        super().__init__(
            id="d7a9f3e2-8b4c-4d6f-9e1a-3c5b7f8d2a6e",
            description="Create draft replies to Gmail threads with automatic HTML detection and proper text formatting. Plain text draft replies maintain natural paragraph flow without 78-character line wrapping. HTML content is automatically detected and formatted correctly.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailDraftReplyBlock.Input,
            output_schema=GmailDraftReplyBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "threadId": "t1",
                "parentMessageId": "m1",
                "body": "Thanks for your message. I'll review and get back to you.",
                "replyAll": False,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("draftId", "draft1"),
                ("messageId", "m2"),
                ("threadId", "t1"),
                ("status", "draft_created"),
            ],
            test_mock={
                "_create_draft_reply": lambda *args, **kwargs: {
                    "id": "draft1",
                    "message": {"id": "m2", "threadId": "t1"},
                }
            },
        )

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GoogleCredentials,
        graph_exec_id: str,
        user_id: str,
        **kwargs,
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        draft = await self._create_draft_reply(
            service,
            input_data,
            graph_exec_id,
            user_id,
        )
        yield "draftId", draft["id"]
        yield "messageId", draft["message"]["id"]
        yield "threadId", draft["message"].get("threadId", input_data.threadId)
        yield "status", "draft_created"

    async def _create_draft_reply(
        self, service, input_data: Input, graph_exec_id: str, user_id: str
    ) -> dict:
        # Build the reply message using the shared helper
        raw, thread_id = await _build_reply_message(
            service, input_data, graph_exec_id, user_id
        )

        # Create draft with proper thread association
        draft = await asyncio.to_thread(
            lambda: service.users()
            .drafts()
            .create(
                userId="me",
                body={
                    "message": {
                        "threadId": thread_id,
                        "raw": raw,
                    }
                },
            )
            .execute()
        )

        return draft


class GmailGetProfileBlock(GmailBase):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.readonly"]
        )

    class Output(BlockSchemaOutput):
        profile: Profile = SchemaField(description="Gmail user profile information")

    def __init__(self):
        super().__init__(
            id="04b0d996-0908-4a4b-89dd-b9697ff253d3",
            description="Get the authenticated user's Gmail profile details including email address and message statistics.",
            categories={BlockCategory.COMMUNICATION},
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            input_schema=GmailGetProfileBlock.Input,
            output_schema=GmailGetProfileBlock.Output,
            test_input={
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "profile",
                    {
                        "emailAddress": "test@example.com",
                        "messagesTotal": 1000,
                        "threadsTotal": 500,
                        "historyId": "12345",
                    },
                ),
            ],
            test_mock={
                "_get_profile": lambda *args, **kwargs: {
                    "emailAddress": "test@example.com",
                    "messagesTotal": 1000,
                    "threadsTotal": 500,
                    "historyId": "12345",
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        profile = await self._get_profile(service)
        yield "profile", profile

    async def _get_profile(self, service) -> Profile:
        result = await asyncio.to_thread(
            lambda: service.users().getProfile(userId="me").execute()
        )
        return Profile(
            emailAddress=result.get("emailAddress", ""),
            messagesTotal=result.get("messagesTotal", 0),
            threadsTotal=result.get("threadsTotal", 0),
            historyId=result.get("historyId", ""),
        )


class GmailForwardBlock(GmailBase):
    """
    Forwards Gmail messages with intelligent content type detection.

    Features:
    - Preserves original message headers and threading
    - Automatic HTML detection for forwarded content
    - Optional forward message customization
    - Full attachment support from original message
    - Manual content type override option
    """

    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            [
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.readonly",
            ]
        )
        messageId: str = SchemaField(description="ID of the message to forward")
        to: list[str] = SchemaField(description="Recipients to forward the message to")
        cc: list[str] = SchemaField(description="CC recipients", default_factory=list)
        bcc: list[str] = SchemaField(description="BCC recipients", default_factory=list)
        subject: str = SchemaField(
            description="Optional custom subject (defaults to 'Fwd: [original subject]')",
            default="",
        )
        forwardMessage: str = SchemaField(
            description="Optional message to include before the forwarded content",
            default="",
        )
        includeAttachments: bool = SchemaField(
            description="Include attachments from the original message",
            default=True,
        )
        content_type: Optional[Literal["auto", "plain", "html"]] = SchemaField(
            description="Content type: 'auto' (default - detects HTML), 'plain', or 'html'",
            default=None,
            advanced=True,
        )
        additionalAttachments: list[MediaFileType] = SchemaField(
            description="Additional files to attach",
            default_factory=list,
            advanced=True,
        )

    class Output(BlockSchemaOutput):
        messageId: str = SchemaField(description="Forwarded message ID")
        threadId: str = SchemaField(description="Thread ID")
        status: str = SchemaField(description="Forward status")

    def __init__(self):
        super().__init__(
            id="64d2301c-b3f5-4174-8ac0-111ca1e1a7c0",
            description="Forward Gmail messages to other recipients with automatic HTML detection and proper formatting. Preserves original message threading and attachments.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailForwardBlock.Input,
            output_schema=GmailForwardBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "messageId": "m1",
                "to": ["recipient@example.com"],
                "forwardMessage": "FYI - forwarding this to you.",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("messageId", "m2"),
                ("threadId", "t1"),
                ("status", "forwarded"),
            ],
            test_mock={
                "_forward_message": lambda *args, **kwargs: {
                    "id": "m2",
                    "threadId": "t1",
                },
            },
        )

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GoogleCredentials,
        graph_exec_id: str,
        user_id: str,
        **kwargs,
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        result = await self._forward_message(
            service,
            input_data,
            graph_exec_id,
            user_id,
        )
        yield "messageId", result["id"]
        yield "threadId", result.get("threadId", "")
        yield "status", "forwarded"

    async def _forward_message(
        self, service, input_data: Input, graph_exec_id: str, user_id: str
    ) -> dict:
        if not input_data.to:
            raise ValueError("At least one recipient is required for forwarding")

        # Get the original message
        original = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .get(userId="me", id=input_data.messageId, format="full")
            .execute()
        )

        headers = {
            h["name"].lower(): h["value"]
            for h in original.get("payload", {}).get("headers", [])
        }

        # Create subject with Fwd: prefix if not already present
        original_subject = headers.get("subject", "No Subject")
        if input_data.subject:
            subject = input_data.subject
        elif not original_subject.lower().startswith("fwd:"):
            subject = f"Fwd: {original_subject}"
        else:
            subject = original_subject

        # Build forwarded message body
        original_from = headers.get("from", "Unknown")
        original_date = headers.get("date", "Unknown")
        original_to = headers.get("to", "Unknown")

        # Get the original body
        original_body = await self._get_email_body(original, service)

        # Construct the forward header
        forward_header = f"""
---------- Forwarded message ---------
From: {original_from}
Date: {original_date}
Subject: {original_subject}
To: {original_to}
"""

        # Combine optional forward message with original content
        if input_data.forwardMessage:
            body = f"{input_data.forwardMessage}\n\n{forward_header}\n\n{original_body}"
        else:
            body = f"{forward_header}\n\n{original_body}"

        # Create MIME message
        msg = MIMEMultipart()
        msg["To"] = ", ".join(input_data.to)
        if input_data.cc:
            msg["Cc"] = ", ".join(input_data.cc)
        if input_data.bcc:
            msg["Bcc"] = ", ".join(input_data.bcc)
        msg["Subject"] = subject

        # Add body with proper content type
        msg.attach(_make_mime_text(body, input_data.content_type))

        # Include original attachments if requested
        if input_data.includeAttachments:
            attachments = await self._get_attachments(service, original)
            for attachment in attachments:
                # Download and attach each original attachment
                attachment_data = await self.download_attachment(
                    service, input_data.messageId, attachment.attachment_id
                )
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment_data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={attachment.filename}",
                )
                msg.attach(part)

        # Add any additional attachments
        for attach in input_data.additionalAttachments:
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

        # Send the forwarded message
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        return await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
