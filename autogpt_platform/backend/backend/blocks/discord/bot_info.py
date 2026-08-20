"""Discord user and channel info blocks."""

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

class DiscordUserInfoBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        user_id: str = SchemaField(
            description="The Discord user ID to get information about"
        )

    class Output(BlockSchemaOutput):
        user_id: str = SchemaField(
            description="The user's ID (passed through for chaining)"
        )
        username: str = SchemaField(description="The user's username")
        display_name: str = SchemaField(description="The user's display name")
        discriminator: str = SchemaField(
            description="The user's discriminator (if applicable)"
        )
        avatar_url: str = SchemaField(description="URL to the user's avatar")
        is_bot: bool = SchemaField(description="Whether the user is a bot")
        created_at: str = SchemaField(description="When the account was created")

    def __init__(self):
        super().__init__(
            id="9aeed32a-6ebf-49b8-a0a3-e2e509d86120",
            input_schema=DiscordUserInfoBlock.Input,
            output_schema=DiscordUserInfoBlock.Output,
            description="Gets information about a Discord user by their ID.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "user_id": "123456789012345678",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("user_id", "123456789012345678"),
                ("username", "testuser"),
                ("display_name", "Test User"),
                ("discriminator", "0"),
                (
                    "avatar_url",
                    "https://cdn.discordapp.com/avatars/123456789012345678/avatar.png",
                ),
                ("is_bot", False),
                ("created_at", "2020-01-01T00:00:00"),
            ],
            test_mock={
                "get_user_info": lambda token, user_id: {
                    "user_id": "123456789012345678",
                    "username": "testuser",
                    "display_name": "Test User",
                    "discriminator": "0",
                    "avatar_url": "https://cdn.discordapp.com/avatars/123456789012345678/avatar.png",
                    "is_bot": False,
                    "created_at": "2020-01-01T00:00:00",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def get_user_info(self, token: str, user_id: str) -> dict:
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)

        result = {}

        @client.event
        async def on_ready():
            try:
                user = await client.fetch_user(int(user_id))

                result["user_id"] = str(user.id)  # Pass through the user ID
                result["username"] = user.name
                result["display_name"] = user.display_name or user.name
                result["discriminator"] = user.discriminator
                result["avatar_url"] = (
                    str(user.avatar.url)
                    if user.avatar
                    else str(user.default_avatar.url)
                )
                result["is_bot"] = user.bot
                result["created_at"] = user.created_at.isoformat()

            except discord.errors.NotFound:
                result["error"] = f"User with ID {user_id} not found"
            except ValueError:
                result["error"] = f"Invalid user ID format: {user_id}"
            except Exception as e:
                result["error"] = f"Error fetching user info: {str(e)}"
            finally:
                await client.close()

        await client.start(token)
        return result

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        try:
            result = await self.get_user_info(
                token=credentials.api_key.get_secret_value(), user_id=input_data.user_id
            )

            if "error" in result:
                raise ValueError(result["error"])

            yield "user_id", result["user_id"]
            yield "username", result["username"]
            yield "display_name", result["display_name"]
            yield "discriminator", result["discriminator"]
            yield "avatar_url", result["avatar_url"]
            yield "is_bot", result["is_bot"]
            yield "created_at", result["created_at"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")


class DiscordChannelInfoBlock(Block):
    class Input(BlockSchemaInput):
        credentials: DiscordCredentials = DiscordCredentialsField()
        channel_identifier: str = SchemaField(
            description="Channel name or channel ID to look up"
        )
        server_name: str = SchemaField(
            description="Server name (optional, helps narrow down search)",
            advanced=True,
            default="",
        )

    class Output(BlockSchemaOutput):
        channel_id: str = SchemaField(description="The channel's ID")
        channel_name: str = SchemaField(description="The channel's name")
        server_id: str = SchemaField(description="The server's ID")
        server_name: str = SchemaField(description="The server's name")
        channel_type: str = SchemaField(
            description="Type of channel (text, voice, etc)"
        )

    def __init__(self):
        super().__init__(
            id="592f815e-35c3-4fed-96cd-a69966b45c8f",
            input_schema=DiscordChannelInfoBlock.Input,
            output_schema=DiscordChannelInfoBlock.Output,
            description="Resolves Discord channel names to IDs and vice versa.",
            categories={BlockCategory.SOCIAL},
            test_input={
                "channel_identifier": "general",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_output=[
                ("channel_id", "123456789012345678"),
                ("channel_name", "general"),
                ("server_id", "987654321098765432"),
                ("server_name", "Test Server"),
                ("channel_type", "text"),
            ],
            test_mock={
                "get_channel_info": lambda token, channel_identifier, server_name: {
                    "channel_id": "123456789012345678",
                    "channel_name": "general",
                    "server_id": "987654321098765432",
                    "server_name": "Test Server",
                    "channel_type": "text",
                }
            },
            test_credentials=TEST_CREDENTIALS,
        )

    async def get_channel_info(
        self, token: str, channel_identifier: str, server_name: str | None
    ) -> dict:
        intents = discord.Intents.default()
        intents.guilds = True
        client = discord.Client(intents=intents)

        result = {}

        @client.event
        async def on_ready():
            # Try to parse as channel ID first
            channel = None
            try:
                channel_id = int(channel_identifier)
                channel = client.get_channel(channel_id)
                if channel:
                    result["channel_id"] = str(channel.id)
                    # Private channels may not have a name attribute
                    result["channel_name"] = getattr(channel, "name", "Private Channel")
                    # Check if channel has guild (not private)
                    if hasattr(channel, "guild"):
                        guild = getattr(channel, "guild", None)
                        if guild:
                            result["server_id"] = str(guild.id)
                            result["server_name"] = guild.name
                        else:
                            result["server_id"] = ""
                            result["server_name"] = "Direct Message"
                    else:
                        result["server_id"] = ""
                        result["server_name"] = "Direct Message"
                    # Get channel type safely
                    result["channel_type"] = str(getattr(channel, "type", "unknown"))
                    await client.close()
                    return
            except ValueError:
                # Not an ID, treat as channel name
                for guild in client.guilds:
                    if server_name and guild.name != server_name:
                        continue
                    for ch in guild.channels:
                        if ch.name == channel_identifier:
                            result["channel_id"] = str(ch.id)
                            result["channel_name"] = ch.name
                            result["server_id"] = str(guild.id)
                            result["server_name"] = guild.name
                            result["channel_type"] = str(ch.type)
                            await client.close()
                            return

            result["error"] = f"Channel not found: {channel_identifier}"
            await client.close()

        await client.start(token)
        return result

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        try:
            result = await self.get_channel_info(
                token=credentials.api_key.get_secret_value(),
                channel_identifier=input_data.channel_identifier,
                server_name=input_data.server_name or None,
            )

            if "error" in result:
                raise ValueError(result["error"])

            yield "channel_id", result["channel_id"]
            yield "channel_name", result["channel_name"]
            yield "server_id", result["server_id"]
            yield "server_name", result["server_name"]
            yield "channel_type", result["channel_type"]

        except discord.errors.LoginFailure as login_err:
            raise ValueError(f"Login error occurred: {login_err}")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")
