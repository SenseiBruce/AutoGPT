"""Gmail read/send/draft/label blocks."""

import asyncio
from email.utils import getaddresses, parseaddr
from typing import Literal, Optional

from backend.blocks.google.gmail_base import GmailBase
from backend.blocks.google.gmail_mime import create_mime_message
from backend.blocks.google.gmail_models import (
    Email,
    GmailDraftResult,
    GmailLabelResult,
    GmailSendResult,
)
from backend.data.block import BlockCategory, BlockOutput, BlockSchemaInput, BlockSchemaOutput
from backend.data.model import SchemaField
from backend.util.file import MediaFileType

from ._auth import (
    GOOGLE_OAUTH_IS_CONFIGURED,
    TEST_CREDENTIALS,
    TEST_CREDENTIALS_INPUT,
    GoogleCredentials,
    GoogleCredentialsField,
    GoogleCredentialsInput,
)

class GmailReadBlock(GmailBase):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.readonly"]
        )
        query: str = SchemaField(
            description="Search query for reading emails",
            default="is:unread",
        )
        max_results: int = SchemaField(
            description="Maximum number of emails to retrieve",
            default=10,
        )

    class Output(BlockSchemaOutput):
        email: Email = SchemaField(
            description="Email data",
        )
        emails: list[Email] = SchemaField(
            description="List of email data",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="25310c70-b89b-43ba-b25c-4dfa7e2a481c",
            description="This block reads emails from Gmail.",
            categories={BlockCategory.COMMUNICATION},
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            input_schema=GmailReadBlock.Input,
            output_schema=GmailReadBlock.Output,
            test_input={
                "query": "is:unread",
                "max_results": 5,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "email",
                    {
                        "threadId": "t1",
                        "labelIds": ["INBOX"],
                        "id": "1",
                        "subject": "Test Email",
                        "snippet": "This is a test email",
                        "from_": "test@example.com",
                        "to": ["recipient@example.com"],
                        "cc": [],
                        "bcc": [],
                        "date": "2024-01-01",
                        "body": "This is a test email",
                        "sizeEstimate": 100,
                        "attachments": [],
                    },
                ),
                (
                    "emails",
                    [
                        {
                            "threadId": "t1",
                            "labelIds": ["INBOX"],
                            "id": "1",
                            "subject": "Test Email",
                            "snippet": "This is a test email",
                            "from_": "test@example.com",
                            "to": ["recipient@example.com"],
                            "cc": [],
                            "bcc": [],
                            "date": "2024-01-01",
                            "body": "This is a test email",
                            "sizeEstimate": 100,
                            "attachments": [],
                        }
                    ],
                ),
            ],
            test_mock={
                "_read_emails": lambda *args, **kwargs: [
                    {
                        "threadId": "t1",
                        "labelIds": ["INBOX"],
                        "id": "1",
                        "subject": "Test Email",
                        "snippet": "This is a test email",
                        "from_": "test@example.com",
                        "to": ["recipient@example.com"],
                        "cc": [],
                        "bcc": [],
                        "date": "2024-01-01",
                        "body": "This is a test email",
                        "sizeEstimate": 100,
                        "attachments": [],
                    }
                ],
                "_send_email": lambda *args, **kwargs: {"id": "1", "status": "sent"},
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        messages = await self._read_emails(
            service,
            input_data.query,
            input_data.max_results,
            credentials.scopes,
        )
        for email in messages:
            yield "email", email
        yield "emails", messages

    async def _read_emails(
        self,
        service,
        query: str | None,
        max_results: int | None,
        scopes: list[str] | None,
    ) -> list[Email]:
        scopes = [s.lower() for s in (scopes or [])]
        list_kwargs = {"userId": "me", "maxResults": max_results or 10}
        if query and "https://www.googleapis.com/auth/gmail.metadata" not in scopes:
            list_kwargs["q"] = query

        results = await asyncio.to_thread(
            lambda: service.users().messages().list(**list_kwargs).execute()
        )

        messages = results.get("messages", [])

        email_data = []
        for message in messages:
            format_type = (
                "metadata"
                if "https://www.googleapis.com/auth/gmail.metadata" in scopes
                else "full"
            )
            msg = await asyncio.to_thread(
                lambda: service.users()
                .messages()
                .get(userId="me", id=message["id"], format=format_type)
                .execute()
            )

            headers = {
                header["name"].lower(): header["value"]
                for header in msg["payload"]["headers"]
            }

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
                threadId=msg.get("threadId", None),
                labelIds=msg.get("labelIds", []),
                id=msg["id"],
                subject=headers.get("subject", "No Subject"),
                snippet=msg.get("snippet", ""),
                from_=parseaddr(headers.get("from", ""))[1],
                to=to_recipients if to_recipients else [],
                cc=cc_recipients,
                bcc=bcc_recipients,
                date=headers.get("date", ""),
                body=await self._get_email_body(msg, service),
                sizeEstimate=msg.get("sizeEstimate", 0),
                attachments=attachments,
            )
            email_data.append(email)

        return email_data


class GmailSendBlock(GmailBase):
    """
    Sends emails through Gmail with intelligent content type detection.

    Features:
    - Automatic HTML detection: Emails containing HTML tags are sent as text/html
    - No hard-wrap for plain text: Plain text emails preserve natural line flow
    - Manual content type override: Use content_type parameter to force specific format
    - Full Unicode/emoji support with UTF-8 encoding
    - Attachment support for multiple files
    """

    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.send"]
        )
        to: list[str] = SchemaField(
            description="Recipient email addresses",
        )
        subject: str = SchemaField(
            description="Email subject",
        )
        body: str = SchemaField(
            description="Email body (plain text or HTML)",
        )
        cc: list[str] = SchemaField(description="CC recipients", default_factory=list)
        bcc: list[str] = SchemaField(description="BCC recipients", default_factory=list)
        content_type: Optional[Literal["auto", "plain", "html"]] = SchemaField(
            description="Content type: 'auto' (default - detects HTML), 'plain', or 'html'",
            default=None,
            advanced=True,
        )
        attachments: list[MediaFileType] = SchemaField(
            description="Files to attach", default_factory=list, advanced=True
        )

    class Output(BlockSchemaOutput):
        result: GmailSendResult = SchemaField(
            description="Send confirmation",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="6c27abc2-e51d-499e-a85f-5a0041ba94f0",
            description="Send emails via Gmail with automatic HTML detection and proper text formatting. Plain text emails are sent without 78-character line wrapping, preserving natural paragraph flow. HTML emails are automatically detected and sent with correct MIME type.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailSendBlock.Input,
            output_schema=GmailSendBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "to": ["recipient@example.com"],
                "subject": "Test Email",
                "body": "This is a test email sent from GmailSendBlock.",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("result", {"id": "1", "status": "sent"}),
            ],
            test_mock={
                "_send_email": lambda *args, **kwargs: {"id": "1", "status": "sent"},
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
        result = await self._send_email(
            service,
            input_data,
            graph_exec_id,
            user_id,
        )
        yield "result", result

    async def _send_email(
        self, service, input_data: Input, graph_exec_id: str, user_id: str
    ) -> dict:
        if not input_data.to or not input_data.subject or not input_data.body:
            raise ValueError(
                "At least one recipient, subject, and body are required for sending an email"
            )
        raw_message = await create_mime_message(input_data, graph_exec_id, user_id)
        sent_message = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )
        return {"id": sent_message["id"], "status": "sent"}


class GmailCreateDraftBlock(GmailBase):
    """
    Creates draft emails in Gmail with intelligent content type detection.

    Features:
    - Automatic HTML detection: Drafts containing HTML tags are formatted as text/html
    - No hard-wrap for plain text: Plain text drafts preserve natural line flow
    - Manual content type override: Use content_type parameter to force specific format
    - Full Unicode/emoji support with UTF-8 encoding
    - Attachment support for multiple files
    """

    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.modify"]
        )
        to: list[str] = SchemaField(
            description="Recipient email addresses",
        )
        subject: str = SchemaField(
            description="Email subject",
        )
        body: str = SchemaField(
            description="Email body (plain text or HTML)",
        )
        cc: list[str] = SchemaField(description="CC recipients", default_factory=list)
        bcc: list[str] = SchemaField(description="BCC recipients", default_factory=list)
        content_type: Optional[Literal["auto", "plain", "html"]] = SchemaField(
            description="Content type: 'auto' (default - detects HTML), 'plain', or 'html'",
            default=None,
            advanced=True,
        )
        attachments: list[MediaFileType] = SchemaField(
            description="Files to attach", default_factory=list, advanced=True
        )

    class Output(BlockSchemaOutput):
        result: GmailDraftResult = SchemaField(
            description="Draft creation result",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="e1eeead4-46cb-491e-8281-17b6b9c44a55",
            description="Create draft emails in Gmail with automatic HTML detection and proper text formatting. Plain text drafts preserve natural paragraph flow without 78-character line wrapping. HTML content is automatically detected and formatted correctly.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailCreateDraftBlock.Input,
            output_schema=GmailCreateDraftBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "to": ["recipient@example.com"],
                "subject": "Draft Test Email",
                "body": "This is a test draft email.",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    GmailDraftResult(
                        id="draft1", message_id="msg1", status="draft_created"
                    ),
                ),
            ],
            test_mock={
                "_create_draft": lambda *args, **kwargs: {
                    "id": "draft1",
                    "message": {"id": "msg1"},
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
        result = await self._create_draft(
            service,
            input_data,
            graph_exec_id,
            user_id,
        )
        yield "result", GmailDraftResult(
            id=result["id"], message_id=result["message"]["id"], status="draft_created"
        )

    async def _create_draft(
        self, service, input_data: Input, graph_exec_id: str, user_id: str
    ) -> dict:
        if not input_data.to or not input_data.subject:
            raise ValueError(
                "At least one recipient and subject are required for creating a draft"
            )

        raw_message = await create_mime_message(input_data, graph_exec_id, user_id)
        draft = await asyncio.to_thread(
            lambda: service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw_message}})
            .execute()
        )

        return draft


class GmailListLabelsBlock(GmailBase):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.labels"]
        )

    class Output(BlockSchemaOutput):
        result: list[dict] = SchemaField(
            description="List of labels",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="3e1c2c1c-c689-4520-b956-1f3bf4e02bb7",
            description="This block lists all labels in Gmail.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailListLabelsBlock.Input,
            output_schema=GmailListLabelsBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    [
                        {"id": "Label_1", "name": "Important"},
                        {"id": "Label_2", "name": "Work"},
                    ],
                ),
            ],
            test_mock={
                "_list_labels": lambda *args, **kwargs: [
                    {"id": "Label_1", "name": "Important"},
                    {"id": "Label_2", "name": "Work"},
                ],
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        result = await self._list_labels(service)
        yield "result", result

    async def _list_labels(self, service) -> list[dict]:
        results = await asyncio.to_thread(
            lambda: service.users().labels().list(userId="me").execute()
        )
        labels = results.get("labels", [])
        return [{"id": label["id"], "name": label["name"]} for label in labels]


class GmailAddLabelBlock(GmailBase):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.modify"]
        )
        message_id: str = SchemaField(
            description="Message ID to add label to",
        )
        label_name: str = SchemaField(
            description="Label name to add",
        )

    class Output(BlockSchemaOutput):
        result: GmailLabelResult = SchemaField(
            description="Label addition result",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="f884b2fb-04f4-4265-9658-14f433926ac9",
            description="This block adds a label to a Gmail message.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailAddLabelBlock.Input,
            output_schema=GmailAddLabelBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "message_id": "12345",
                "label_name": "Important",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    {"status": "Label added successfully", "label_id": "Label_1"},
                ),
            ],
            test_mock={
                "_add_label": lambda *args, **kwargs: {
                    "status": "Label added successfully",
                    "label_id": "Label_1",
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        result = await self._add_label(
            service, input_data.message_id, input_data.label_name
        )
        yield "result", result

    async def _add_label(self, service, message_id: str, label_name: str) -> dict:
        label_id = await self._get_or_create_label(service, label_name)
        result = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .modify(userId="me", id=message_id, body={"addLabelIds": [label_id]})
            .execute()
        )
        if not result.get("labelIds"):
            return {
                "status": "Label already applied or not found",
                "label_id": label_id,
            }

        return {"status": "Label added successfully", "label_id": label_id}

    async def _get_or_create_label(self, service, label_name: str) -> str:
        label_id = await self._get_label_id(service, label_name)
        if not label_id:
            label = await asyncio.to_thread(
                lambda: service.users()
                .labels()
                .create(userId="me", body={"name": label_name})
                .execute()
            )
            label_id = label["id"]
        return label_id


class GmailRemoveLabelBlock(GmailBase):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/gmail.modify"]
        )
        message_id: str = SchemaField(
            description="Message ID to remove label from",
        )
        label_name: str = SchemaField(
            description="Label name to remove",
        )

    class Output(BlockSchemaOutput):
        result: GmailLabelResult = SchemaField(
            description="Label removal result",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="0afc0526-aba1-4b2b-888e-a22b7c3f359d",
            description="This block removes a label from a Gmail message.",
            categories={BlockCategory.COMMUNICATION},
            input_schema=GmailRemoveLabelBlock.Input,
            output_schema=GmailRemoveLabelBlock.Output,
            disabled=not GOOGLE_OAUTH_IS_CONFIGURED,
            test_input={
                "message_id": "12345",
                "label_name": "Important",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    {"status": "Label removed successfully", "label_id": "Label_1"},
                ),
            ],
            test_mock={
                "_remove_label": lambda *args, **kwargs: {
                    "status": "Label removed successfully",
                    "label_id": "Label_1",
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = self._build_service(credentials, **kwargs)
        result = await self._remove_label(
            service, input_data.message_id, input_data.label_name
        )
        yield "result", result

    async def _remove_label(self, service, message_id: str, label_name: str) -> dict:
        label_id = await self._get_label_id(service, label_name)
        if label_id:
            result = await asyncio.to_thread(
                lambda: service.users()
                .messages()
                .modify(userId="me", id=message_id, body={"removeLabelIds": [label_id]})
                .execute()
            )
            if not result.get("labelIds"):
                return {
                    "status": "Label already removed or not applied",
                    "label_id": label_id,
                }
            return {"status": "Label removed successfully", "label_id": label_id}
        else:
            return {"status": "Label not found", "label_name": label_name}


