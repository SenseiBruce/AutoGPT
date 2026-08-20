"""Discord read/send message and embed blocks."""

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

class ReadDiscordMessagesBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()

    class Output(BlockSchemaOutput):
        message_content: str = SchemaField(
            description="The content of the message received"
        )
        message_id: str = SchemaField(description="The ID of the message")
        channel_id: str = SchemaField(description="The ID of the channel")
        channel_name: str = SchemaField(
            description="The name of the channel the message was received from"
        )
        user_id: str = SchemaField(
            description="The ID of the user who sent the message"
        )
        username: str = SchemaField(
            description="The username of the user who sent the message"
        )

    def __init__(self):
        super().__init__(
            id="df06086a-d5ac-4abb-9996-2ad0acb2eff7",
            input_schema=ReadDiscordMessagesBlock.Input,  # Assign input schema
            output_schema=ReadDiscordMessagesBlock.Output,  # Assign output schema
            description="Reads messages from a Discord channel using a bot token.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "continuous_read": False,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "message_content",
                    "Hello!\n\nFile from user: example.txt\nContent: This is the content of the file.",
                ),
                ("message_id", "123456789012345678"),
                ("channel_id", "987654321098765432"),
                ("channel_name", "general"),
                ("user_id", "111222333444555666"),
                ("username", "test_user"),
            ],
            test_mock={
                "run_bot": lambda token: {
                    "output_data": "Hello!\n\nFile from user: example.txt\nContent: This is the content of the file.",
                    "message_id": "123456789012345678",
                    "channel_id": "987654321098765432",
                    "channel_name": "general",
                    "user_id": "111222333444555666",
                    "username": "test_user",
                }
            },
        )

    async def run_bot(self, token: SecretStr):
        intents = discord.Intents.default()
        intents.message_content = True

        client = discord.Client(intents=intents)

        self.output_data = None
        self.message_id = None
        self.channel_id = None
        self.channel_name = None
        self.user_id = None
        self.username = None

        @client.event
        async def on_ready():
            print(f"Logged in as {client.user}")

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return

            self.output_data = message.content
            self.message_id = str(message.id)
            self.channel_id = str(message.channel.id)
            self.channel_name = message.channel.name
            self.user_id = str(message.author.id)
            self.username = message.author.name

            if message.attachments:
                attachment = message.attachments[0]  # Process the first attachment
                if attachment.filename.endswith((".txt", ".py")):
                    response = await Requests().get(attachment.url)
                    file_content = response.text()
                    self.output_data += f"\n\nFile from user: {attachment.filename}\nContent: {file_content}"

            await client.close()

        await client.start(token.get_secret_value())

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        async for output_name, output_value in self.__run(input_data, credentials):
            yield output_name, output_value

    async def __run(
        self, input_data: Input, credentials: APIKeyCredentials
    ) -> BlockOutput:
        try:
            result = await self.run_bot(credentials.api_key)

            # For testing purposes, use the mocked result
            if isinstance(result, dict):
                self.output_data = result.get("output_data")
                self.message_id = result.get("message_id")
                self.channel_id = result.get("channel_id")
                self.channel_name = result.get("channel_name")
                self.user_id = result.get("user_id")
                self.username = result.get("username")

            if (
                self.output_data is None
                or self.channel_name is None
                or self.username is None
            ):
                raise ValueError("No message, channel name, or username received.")

            yield "message_content", self.output_data
            yield "message_id", self.message_id
            yield "channel_id", self.channel_id
            yield "channel_name", self.channel_name
            yield "user_id", self.user_id
            yield "username", self.username

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


class SendDiscordMessageBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        message_content: str = SchemaField(
            description="The content of the message to send"
        )
        channel_name: str = SchemaField(
            description="Channel ID or channel name to send the message to"
        )
        server_name: str = SchemaField(
            description="Server name (only needed if using channel name)",
            advanced=True,
            default="",
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(
            description="The status of the operation (e.g., 'Message sent', 'Error')"
        )
        message_id: str = SchemaField(description="The ID of the sent message")
        channel_id: str = SchemaField(
            description="The ID of the channel where the message was sent"
        )

    def __init__(self):
        super().__init__(
            id="d0822ab5-9f8a-44a3-8971-531dd0178b6b",
            input_schema=SendDiscordMessageBlock.Input,  # Assign input schema
            output_schema=SendDiscordMessageBlock.Output,  # Assign output schema
            description="Sends a message to a Discord channel using a bot token.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "channel_name": "general",
                "message_content": "Hello, Discord!",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("status", "Message sent"),
                ("message_id", "123456789012345678"),
                ("channel_id", "987654321098765432"),
            ],
            test_mock={
                "send_message": lambda token, channel_name, server_name, message_content: {
                    "status": "Message sent",
                    "message_id": "123456789012345678",
                    "channel_id": "987654321098765432",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def send_message(
        self,
        token: str,
        channel_name: str,
        server_name: str | None,
        message_content: str,
    ) -> dict:
        intents = discord.Intents.default()
        intents.guilds = True  # Required for fetching guild/channel information
        client = discord.Client(intents=intents)

        result = {}

        @client.event
        async def on_ready():
            print(f"Logged in as {client.user}")
            channel = None

            # Try to parse as channel ID first
            try:
                channel_id = int(channel_name)
                channel = client.get_channel(channel_id)
            except ValueError:
                # Not a valid ID, will try name lookup
                pass

            # If not found by ID (or not an ID), try name lookup
            if not channel:
                for guild in client.guilds:
                    if server_name and guild.name != server_name:
                        continue
                    for ch in guild.text_channels:
                        if ch.name == channel_name:
                            channel = ch
                            break
                    if channel:
                        break

            if not channel:
                result["status"] = f"Channel not found: {channel_name}"
                await client.close()
                return

            # Type check - ensure it's a text channel that can send messages
            if not hasattr(channel, "send"):
                result["status"] = (
                    f"Channel {channel_name} cannot receive messages (not a text channel)"
                )
                await client.close()
                return

            # Split message into chunks if it exceeds 2000 characters
            chunks = self.chunk_message(message_content)
            last_message = None
            for chunk in chunks:
                last_message = await channel.send(chunk)  # type: ignore
            result["status"] = "Message sent"
            result["message_id"] = str(last_message.id) if last_message else ""
            result["channel_id"] = str(channel.id)
            await client.close()

        await client.start(token)
        return result

    def chunk_message(self, message: str, limit: int = 2000) -> list:
        """Splits a message into chunks not exceeding the Discord limit."""
        return [message[i : i + limit] for i in range(0, len(message), limit)]

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        try:
            result = await self.send_message(
                token=credentials.api_key.get_secret_value(),
                channel_name=input_data.channel_name,
                server_name=input_data.server_name,
                message_content=input_data.message_content,
            )

            # For testing purposes, use the mocked result
            if isinstance(result, str):
                result = {"status": result}

            yield "status", result.get("status", "Unknown error")
            if "message_id" in result:
                yield "message_id", result["message_id"]
            if "channel_id" in result:
                yield "channel_id", result["channel_id"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


class SendDiscordDMBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        user_id: str = SchemaField(
            description="The Discord user ID to send the DM to (e.g., '123456789012345678')"
        )
        message_content: str = SchemaField(
            description="The content of the direct message to send"
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(description="The status of the operation")
        message_id: str = SchemaField(description="The ID of the sent message")

    def __init__(self):
        super().__init__(
            id="40d71a5a-e268-4060-9ee0-38ae6f225682",
            input_schema=SendDiscordDMBlock.Input,
            output_schema=SendDiscordDMBlock.Output,
            description="Sends a direct message to a Discord user using their user ID.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "user_id": "123456789012345678",
                "message_content": "Hello! This is a test DM.",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("status", "DM sent successfully"),
                ("message_id", "987654321098765432"),
            ],
            test_mock={
                "send_dm": lambda token, user_id, message_content: {
                    "status": "DM sent successfully",
                    "message_id": "987654321098765432",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def send_dm(self, token: str, user_id: str, message_content: str) -> dict:
        intents = discord.Intents.default()
        intents.dm_messages = True
        client = discord.Client(intents=intents)

        result = {}

        @client.event
        async def on_ready():
            try:
                user = await client.fetch_user(int(user_id))
                message = await user.send(message_content)
                result["status"] = "DM sent successfully"
                result["message_id"] = str(message.id)
            except discord.errors.Forbidden:
                result["status"] = (
                    "Cannot send DM - user has DMs disabled or bot is blocked"
                )
            except discord.errors.NotFound:
                result["status"] = f"User with ID {user_id} not found"
            except ValueError:
                result["status"] = f"Invalid user ID format: {user_id}"
            except Exception as e:
                result["status"] = f"Error sending DM: {str(e)}"
            finally:
                await client.close()

        await client.start(token)
        return result

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        try:
            result = await self.send_dm(
                token=credentials.api_key.get_secret_value(),
                user_id=input_data.user_id,
                message_content=input_data.message_content,
            )

            yield "status", result.get("status", "Unknown error")
            if "message_id" in result:
                yield "message_id", result["message_id"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


class SendDiscordEmbedBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        channel_identifier: str = SchemaField(
            description="Channel ID or channel name to send the embed to"
        )
        server_name: str = SchemaField(
            description="Server name (only needed if using channel name)",
            advanced=True,
            default="",
        )
        title: str = SchemaField(description="The title of the embed", default="")
        description: str = SchemaField(
            description="The main content/description of the embed", default=""
        )
        color: int = SchemaField(
            description="Embed color as integer (e.g., 0x00ff00 for green)",
            advanced=True,
            default=0x5865F2,  # Discord blurple
        )
        thumbnail_url: str = SchemaField(
            description="URL for the thumbnail image", advanced=True, default=""
        )
        image_url: str = SchemaField(
            description="URL for the main embed image", advanced=True, default=""
        )
        author_name: str = SchemaField(
            description="Author name to display", advanced=True, default=""
        )
        footer_text: str = SchemaField(
            description="Footer text", advanced=True, default=""
        )
        fields: list[dict[str, Any]] = SchemaField(
            description="List of field dictionaries with 'name', 'value', and optional 'inline' keys",
            advanced=True,
            default=[],
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(description="Operation status")
        message_id: str = SchemaField(description="ID of the sent embed message")

    def __init__(self):
        super().__init__(
            id="c76293f4-9ae8-454d-a029-0a3f8c5bc499",
            input_schema=SendDiscordEmbedBlock.Input,
            output_schema=SendDiscordEmbedBlock.Output,
            description="Sends a rich embed message to a Discord channel.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "channel_identifier": "general",
                "title": "Test Embed",
                "description": "This is a test embed message",
                "color": 0x00FF00,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("status", "Embed sent successfully"),
                ("message_id", "123456789012345678"),
            ],
            test_mock={
                "send_embed": lambda *args, **kwargs: {
                    "status": "Embed sent successfully",
                    "message_id": "123456789012345678",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def send_embed(
        self,
        token: str,
        channel_identifier: str,
        server_name: str | None,
        embed_data: dict,
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

            # Build the embed
            embed = discord.Embed(
                title=embed_data.get("title") or None,
                description=embed_data.get("description") or None,
                color=embed_data.get("color", 0x5865F2),
            )

            if embed_data.get("thumbnail_url"):
                embed.set_thumbnail(url=embed_data["thumbnail_url"])

            if embed_data.get("image_url"):
                embed.set_image(url=embed_data["image_url"])

            if embed_data.get("author_name"):
                embed.set_author(name=embed_data["author_name"])

            if embed_data.get("footer_text"):
                embed.set_footer(text=embed_data["footer_text"])

            # Add fields
            for field in embed_data.get("fields", []):
                if isinstance(field, dict) and "name" in field and "value" in field:
                    embed.add_field(
                        name=field["name"],
                        value=field["value"],
                        inline=field.get("inline", True),
                    )

            try:
                # Type check - ensure it's a text channel that can send messages
                if not hasattr(channel, "send"):
                    result["status"] = (
                        f"Channel {channel_identifier} cannot receive messages (not a text channel)"
                    )
                    await client.close()
                    return

                message = await channel.send(embed=embed)  # type: ignore
                result["status"] = "Embed sent successfully"
                result["message_id"] = str(message.id)
            except Exception as e:
                result["status"] = f"Error sending embed: {str(e)}"
            finally:
                await client.close()

        await client.start(token)
        return result

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        try:
            embed_data = {
                "title": input_data.title,
                "description": input_data.description,
                "color": input_data.color,
                "thumbnail_url": input_data.thumbnail_url,
                "image_url": input_data.image_url,
                "author_name": input_data.author_name,
                "footer_text": input_data.footer_text,
                "fields": input_data.fields,
            }

            result = await self.send_embed(
                token=credentials.api_key.get_secret_value(),
                channel_identifier=input_data.channel_identifier,
                server_name=input_data.server_name or None,
                embed_data=embed_data,
            )

            yield "status", result.get("status", "Unknown error")
            if "message_id" in result:
                yield "message_id", result["message_id"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


