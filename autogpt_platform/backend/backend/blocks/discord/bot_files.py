"""Discord file send and reply blocks."""

import base64
import io
import mimetypes
from pathlib import Path
from typing import Any

import discord
from pydantic import SecretStr

from backend.data.block import (
    Block,
    BlockCategory,
    BlockOutput,
    BlockSchemaInput,
    BlockSchemaOutput,
)
from backend.data.model import APIKeyCredentials, SchemaField
from backend.util.file import store_media_file
from backend.util.request import Requests
from backend.util.type import MediaFileType

from ._auth import (
    TEST_BOT_CREDENTIALS,
    TEST_BOT_CREDENTIALS_INPUT,
    DiscordBotCredentialsField,
    DiscordBotCredentialsInput,
)

# Keep backward compatibility alias
DiscordCredentials = DiscordBotCredentialsInput
DiscordCredentialsField = DiscordBotCredentialsField
TEST_CREDENTIALS = TEST_BOT_CREDENTIALS
TEST_CREDENTIALS_INPUT = TEST_BOT_CREDENTIALS_INPUT

class SendDiscordFileBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        channel_identifier: str = SchemaField(
            description="Channel ID or channel name to send the file to"
        )
        server_name: str = SchemaField(
            description="Server name (only needed if using channel name)",
            advanced=True,
            default="",
        )
        file: MediaFileType = SchemaField(
            description="The file to send (URL, data URI, or local path). Supports images, videos, documents, etc."
        )
        filename: str = SchemaField(
            description="Name of the file when sent (e.g., 'report.pdf', 'image.png')",
            default="",
        )
        message_content: str = SchemaField(
            description="Optional message to send with the file", default=""
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(description="Operation status")
        message_id: str = SchemaField(description="ID of the sent message")

    def __init__(self):
        super().__init__(
            id="b1628cf2-4622-49bf-80cf-10e55826e247",
            input_schema=SendDiscordFileBlock.Input,
            output_schema=SendDiscordFileBlock.Output,
            description="Sends a file attachment to a Discord channel.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "channel_identifier": "general",
                "file": "data:text/plain;base64,VGVzdCBmaWxlIGNvbnRlbnQ=",
                "filename": "test.txt",
                "message_content": "Here's the file!",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("status", "File sent successfully"),
                ("message_id", "123456789012345678"),
            ],
            test_mock={
                "send_file": lambda *args, **kwargs: {
                    "status": "File sent successfully",
                    "message_id": "123456789012345678",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def send_file(
        self,
        token: str,
        channel_identifier: str,
        server_name: str | None,
        file: MediaFileType,
        filename: str,
        message_content: str,
        graph_exec_id: str,
        user_id: str,
    ) -> dict:
        intents = discord.Intents.default()
        intents.guilds = True
        client = discord.Client(intents=intents)

        result = {}

        @client.event
        async def on_ready():
            channel = None

            # Try to parse as channel ID first
            try:
                channel_id = int(channel_identifier)
                channel = client.get_channel(channel_id)
            except ValueError:
                # Not an ID, treat as channel name
                for guild in client.guilds:
                    if server_name and guild.name != server_name:
                        continue
                    for ch in guild.text_channels:
                        if ch.name == channel_identifier:
                            channel = ch
                            break
                    if channel:
                        break

            if not channel:
                result["status"] = f"Channel not found: {channel_identifier}"
                await client.close()
                return

            try:
                # Handle MediaFileType - could be data URI, URL, or local path
                file_bytes = None
                detected_filename = filename

                if file.startswith("data:"):
                    # Data URI - extract the base64 content
                    header, encoded = file.split(",", 1)
                    file_bytes = base64.b64decode(encoded)

                    # Try to get MIME type and suggest filename if not provided
                    if not filename and ";" in header:
                        mime_match = header.split(":")[1].split(";")[0]
                        ext = mimetypes.guess_extension(mime_match) or ".bin"
                        detected_filename = f"file{ext}"

                elif file.startswith(("http://", "https://")):
                    # URL - download the file
                    response = await Requests().get(file)
                    file_bytes = response.content

                    # Try to get filename from URL if not provided
                    if not filename:
                        from urllib.parse import urlparse

                        path = urlparse(file).path
                        detected_filename = Path(path).name or "download"
                else:
                    # Local file path - read from stored media file
                    # This would be a path from a previous block's output
                    stored_file = await store_media_file(
                        graph_exec_id=graph_exec_id,
                        file=file,
                        user_id=user_id,
                        return_content=True,  # Get as data URI
                    )
                    # Now process as data URI
                    header, encoded = stored_file.split(",", 1)
                    file_bytes = base64.b64decode(encoded)

                    if not filename:
                        detected_filename = Path(file).name or "file"

                if not file_bytes:
                    result["status"] = "Error: Could not read file content"
                    await client.close()
                    return

                # Create Discord file object
                discord_file = discord.File(
                    io.BytesIO(file_bytes), filename=detected_filename or "file"
                )

                # Type check - ensure it's a text channel that can send messages
                if not hasattr(channel, "send"):
                    result["status"] = (
                        f"Channel {channel_identifier} cannot receive messages (not a text channel)"
                    )
                    await client.close()
                    return

                # Send the file
                message = await channel.send(  # type: ignore
                    content=message_content if message_content else None,
                    file=discord_file,
                )
                result["status"] = "File sent successfully"
                result["message_id"] = str(message.id)
            except Exception as e:
                result["status"] = f"Error sending file: {str(e)}"
            finally:
                await client.close()

        await client.start(token)
        return result

    async def run(
        self,
        input_data: Input,
        *,
        credentials: APIKeyCredentials,
        graph_exec_id: str,
        user_id: str,
        **kwargs,
    ) -> BlockOutput:
        try:
            result = await self.send_file(
                token=credentials.api_key.get_secret_value(),
                channel_identifier=input_data.channel_identifier,
                server_name=input_data.server_name or None,
                file=input_data.file,
                filename=input_data.filename,
                message_content=input_data.message_content,
                graph_exec_id=graph_exec_id,
                user_id=user_id,
            )

            yield "status", result.get("status", "Unknown error")
            if "message_id" in result:
                yield "message_id", result["message_id"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


class ReplyToDiscordMessageBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        channel_id: str = SchemaField(
            description="The channel ID where the message to reply to is located"
        )
        message_id: str = SchemaField(description="The ID of the message to reply to")
        reply_content: str = SchemaField(description="The content of the reply")
        mention_author: bool = SchemaField(
            description="Whether to mention the original message author", default=True
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(description="Operation status")
        reply_id: str = SchemaField(description="ID of the reply message")

    def __init__(self):
        super().__init__(
            id="7226cb99-6e7b-4672-b6b2-acec95336eec",
            input_schema=ReplyToDiscordMessageBlock.Input,
            output_schema=ReplyToDiscordMessageBlock.Output,
            description="Replies to a specific Discord message.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "channel_id": "123456789012345678",
                "message_id": "987654321098765432",
                "reply_content": "This is a reply!",
                "mention_author": True,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("status", "Reply sent successfully"),
                ("reply_id", "111222333444555666"),
            ],
            test_mock={
                "send_reply": lambda *args, **kwargs: {
                    "status": "Reply sent successfully",
                    "reply_id": "111222333444555666",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def send_reply(
        self,
        token: str,
        channel_id: str,
        message_id: str,
        reply_content: str,
        mention_author: bool,
    ) -> dict:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        client = discord.Client(intents=intents)

        result = {}

        @client.event
        async def on_ready():
            try:
                channel = client.get_channel(int(channel_id))
                if not channel:
                    channel = await client.fetch_channel(int(channel_id))

                if not channel:
                    result["status"] = f"Channel with ID {channel_id} not found"
                    await client.close()
                    return

                # Type check - ensure it's a text channel that can fetch messages
                if not hasattr(channel, "fetch_message"):
                    result["status"] = (
                        f"Channel {channel_id} cannot fetch messages (not a text channel)"
                    )
                    await client.close()
                    return

                # Fetch the message to reply to
                try:
                    message = await channel.fetch_message(int(message_id))  # type: ignore
                except discord.errors.NotFound:
                    result["status"] = f"Message with ID {message_id} not found"
                    await client.close()
                    return

                # Send the reply
                reply = await message.reply(
                    content=reply_content, mention_author=mention_author
                )
                result["status"] = "Reply sent successfully"
                result["reply_id"] = str(reply.id)

            except ValueError as e:
                result["status"] = f"Invalid ID format: {str(e)}"
            except Exception as e:
                result["status"] = f"Error sending reply: {str(e)}"
            finally:
                await client.close()

        await client.start(token)
        return result

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        try:
            result = await self.send_reply(
                token=credentials.api_key.get_secret_value(),
                channel_id=input_data.channel_id,
                message_id=input_data.message_id,
                reply_content=input_data.reply_content,
                mention_author=input_data.mention_author,
            )

            yield "status", result.get("status", "Unknown error")
            if "reply_id" in result:
                yield "reply_id", result["reply_id"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


