"""GitHub repository create and stargazer blocks."""

import base64

from typing_extensions import TypedDict

from backend.data.block import (
    Block,
    BlockCategory,
    BlockOutput,
    BlockSchemaInput,
    BlockSchemaOutput,
)
from backend.data.model import SchemaField

from ._api import get_api
from ._auth import (
    TEST_CREDENTIALS,
    TEST_CREDENTIALS_INPUT,
    GithubCredentials,
    GithubCredentialsField,
    GithubCredentialsInput,
)

class GithubCreateRepositoryBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        name: str = SchemaField(
            description="Name of the repository to create",
            placeholder="my-new-repo",
        )
        description: str = SchemaField(
            description="Description of the repository",
            placeholder="A description of the repository",
            default="",
        )
        private: bool = SchemaField(
            description="Whether the repository should be private",
            default=False,
        )
        auto_init: bool = SchemaField(
            description="Whether to initialize the repository with a README",
            default=True,
        )
        gitignore_template: str = SchemaField(
            description="Git ignore template to use (e.g., Python, Node, Java)",
            default="",
        )

    class Output(BlockSchemaOutput):
        url: str = SchemaField(description="URL of the created repository")
        clone_url: str = SchemaField(description="Git clone URL of the repository")
        error: str = SchemaField(
            description="Error message if the repository creation failed"
        )

    def __init__(self):
        super().__init__(
            id="029ec3b8-1cfd-46d3-b6aa-28e4a706efd1",
            description="This block creates a new GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubCreateRepositoryBlock.Input,
            output_schema=GithubCreateRepositoryBlock.Output,
            test_input={
                "name": "test-repo",
                "description": "A test repository",
                "private": False,
                "auto_init": True,
                "gitignore_template": "Python",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("url", "https://github.com/owner/test-repo"),
                ("clone_url", "https://github.com/owner/test-repo.git"),
            ],
            test_mock={
                "create_repository": lambda *args, **kwargs: (
                    "https://github.com/owner/test-repo",
                    "https://github.com/owner/test-repo.git",
                )
            },
        )

    @staticmethod
    async def create_repository(
        credentials: GithubCredentials,
        name: str,
        description: str,
        private: bool,
        auto_init: bool,
        gitignore_template: str,
    ) -> tuple[str, str]:
        api = get_api(credentials)
        data = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "gitignore_template": gitignore_template,
        }
        response = await api.post("https://api.github.com/user/repos", json=data)
        data = response.json()
        return data["html_url"], data["clone_url"]

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        try:
            url, clone_url = await self.create_repository(
                credentials,
                input_data.name,
                input_data.description,
                input_data.private,
                input_data.auto_init,
                input_data.gitignore_template,
            )
            yield "url", url
            yield "clone_url", clone_url
        except Exception as e:
            yield "error", str(e)


class GithubListStargazersBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )

    class Output(BlockSchemaOutput):
        class StargazerItem(TypedDict):
            username: str
            url: str

        stargazer: StargazerItem = SchemaField(
            title="Stargazer",
            description="Stargazers with their username and profile URL",
        )
        stargazers: list[StargazerItem] = SchemaField(
            description="List of stargazers with their username and profile URL"
        )
        error: str = SchemaField(
            description="Error message if listing stargazers failed"
        )

    def __init__(self):
        super().__init__(
            id="a4b9c2d1-e5f6-4g7h-8i9j-0k1l2m3n4o5p",  # Generated unique UUID
            description="This block lists all users who have starred a specified GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubListStargazersBlock.Input,
            output_schema=GithubListStargazersBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "stargazers",
                    [
                        {
                            "username": "octocat",
                            "url": "https://github.com/octocat",
                        }
                    ],
                ),
                (
                    "stargazer",
                    {
                        "username": "octocat",
                        "url": "https://github.com/octocat",
                    },
                ),
            ],
            test_mock={
                "list_stargazers": lambda *args, **kwargs: [
                    {
                        "username": "octocat",
                        "url": "https://github.com/octocat",
                    }
                ]
            },
        )

    @staticmethod
    async def list_stargazers(
        credentials: GithubCredentials, repo_url: str
    ) -> list[Output.StargazerItem]:
        api = get_api(credentials)
        stargazers_url = repo_url + "/stargazers"
        response = await api.get(stargazers_url)
        data = response.json()
        stargazers: list[GithubListStargazersBlock.Output.StargazerItem] = [
            {
                "username": stargazer["login"],
                "url": stargazer["html_url"],
            }
            for stargazer in data
        ]
        return stargazers

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        stargazers = await self.list_stargazers(
            credentials,
            input_data.repo_url,
        )
        yield "stargazers", stargazers
        for stargazer in stargazers:
            yield "stargazer", stargazer
