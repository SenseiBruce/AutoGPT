"""GitHub repository list blocks (tags/branches/discussions/releases)."""

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

class GithubListTagsBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )

    class Output(BlockSchemaOutput):
        class TagItem(TypedDict):
            name: str
            url: str

        tag: TagItem = SchemaField(
            title="Tag", description="Tags with their name and file tree browser URL"
        )
        tags: list[TagItem] = SchemaField(
            description="List of tags with their name and file tree browser URL"
        )

    def __init__(self):
        super().__init__(
            id="358924e7-9a11-4d1a-a0f2-13c67fe59e2e",
            description="This block lists all tags for a specified GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubListTagsBlock.Input,
            output_schema=GithubListTagsBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "tags",
                    [
                        {
                            "name": "v1.0.0",
                            "url": "https://github.com/owner/repo/tree/v1.0.0",
                        }
                    ],
                ),
                (
                    "tag",
                    {
                        "name": "v1.0.0",
                        "url": "https://github.com/owner/repo/tree/v1.0.0",
                    },
                ),
            ],
            test_mock={
                "list_tags": lambda *args, **kwargs: [
                    {
                        "name": "v1.0.0",
                        "url": "https://github.com/owner/repo/tree/v1.0.0",
                    }
                ]
            },
        )

    @staticmethod
    async def list_tags(
        credentials: GithubCredentials, repo_url: str
    ) -> list[Output.TagItem]:
        api = get_api(credentials)
        tags_url = repo_url + "/tags"
        response = await api.get(tags_url)
        data = response.json()
        repo_path = repo_url.replace("https://github.com/", "")
        tags: list[GithubListTagsBlock.Output.TagItem] = [
            {
                "name": tag["name"],
                "url": f"https://github.com/{repo_path}/tree/{tag['name']}",
            }
            for tag in data
        ]
        return tags

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        tags = await self.list_tags(
            credentials,
            input_data.repo_url,
        )
        yield "tags", tags
        for tag in tags:
            yield "tag", tag


class GithubListBranchesBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )

    class Output(BlockSchemaOutput):
        class BranchItem(TypedDict):
            name: str
            url: str

        branch: BranchItem = SchemaField(
            title="Branch",
            description="Branches with their name and file tree browser URL",
        )
        branches: list[BranchItem] = SchemaField(
            description="List of branches with their name and file tree browser URL"
        )

    def __init__(self):
        super().__init__(
            id="74243e49-2bec-4916-8bf4-db43d44aead5",
            description="This block lists all branches for a specified GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubListBranchesBlock.Input,
            output_schema=GithubListBranchesBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "branches",
                    [
                        {
                            "name": "main",
                            "url": "https://github.com/owner/repo/tree/main",
                        }
                    ],
                ),
                (
                    "branch",
                    {
                        "name": "main",
                        "url": "https://github.com/owner/repo/tree/main",
                    },
                ),
            ],
            test_mock={
                "list_branches": lambda *args, **kwargs: [
                    {
                        "name": "main",
                        "url": "https://github.com/owner/repo/tree/main",
                    }
                ]
            },
        )

    @staticmethod
    async def list_branches(
        credentials: GithubCredentials, repo_url: str
    ) -> list[Output.BranchItem]:
        api = get_api(credentials)
        branches_url = repo_url + "/branches"
        response = await api.get(branches_url)
        data = response.json()
        repo_path = repo_url.replace("https://github.com/", "")
        branches: list[GithubListBranchesBlock.Output.BranchItem] = [
            {
                "name": branch["name"],
                "url": f"https://github.com/{repo_path}/tree/{branch['name']}",
            }
            for branch in data
        ]
        return branches

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        branches = await self.list_branches(
            credentials,
            input_data.repo_url,
        )
        yield "branches", branches
        for branch in branches:
            yield "branch", branch


class GithubListDiscussionsBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        num_discussions: int = SchemaField(
            description="Number of discussions to fetch", default=5
        )

    class Output(BlockSchemaOutput):
        class DiscussionItem(TypedDict):
            title: str
            url: str

        discussion: DiscussionItem = SchemaField(
            title="Discussion", description="Discussions with their title and URL"
        )
        discussions: list[DiscussionItem] = SchemaField(
            description="List of discussions with their title and URL"
        )
        error: str = SchemaField(
            description="Error message if listing discussions failed"
        )

    def __init__(self):
        super().__init__(
            id="3ef1a419-3d76-4e07-b761-de9dad4d51d7",
            description="This block lists recent discussions for a specified GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubListDiscussionsBlock.Input,
            output_schema=GithubListDiscussionsBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "num_discussions": 3,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "discussions",
                    [
                        {
                            "title": "Discussion 1",
                            "url": "https://github.com/owner/repo/discussions/1",
                        }
                    ],
                ),
                (
                    "discussion",
                    {
                        "title": "Discussion 1",
                        "url": "https://github.com/owner/repo/discussions/1",
                    },
                ),
            ],
            test_mock={
                "list_discussions": lambda *args, **kwargs: [
                    {
                        "title": "Discussion 1",
                        "url": "https://github.com/owner/repo/discussions/1",
                    }
                ]
            },
        )

    @staticmethod
    async def list_discussions(
        credentials: GithubCredentials, repo_url: str, num_discussions: int
    ) -> list[Output.DiscussionItem]:
        api = get_api(credentials)
        # GitHub GraphQL API endpoint is different; we'll use api.post with custom URL
        repo_path = repo_url.replace("https://github.com/", "")
        owner, repo = repo_path.split("/")
        query = """
        query($owner: String!, $repo: String!, $num: Int!) {
            repository(owner: $owner, name: $repo) {
                discussions(first: $num) {
                    nodes {
                        title
                        url
                    }
                }
            }
        }
        """
        variables = {"owner": owner, "repo": repo, "num": num_discussions}
        response = await api.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
        )
        data = response.json()
        discussions: list[GithubListDiscussionsBlock.Output.DiscussionItem] = [
            {"title": discussion["title"], "url": discussion["url"]}
            for discussion in data["data"]["repository"]["discussions"]["nodes"]
        ]
        return discussions

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        discussions = await self.list_discussions(
            credentials,
            input_data.repo_url,
            input_data.num_discussions,
        )
        yield "discussions", discussions
        for discussion in discussions:
            yield "discussion", discussion


class GithubListReleasesBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )

    class Output(BlockSchemaOutput):
        class ReleaseItem(TypedDict):
            name: str
            url: str

        release: ReleaseItem = SchemaField(
            title="Release",
            description="Releases with their name and file tree browser URL",
        )
        releases: list[ReleaseItem] = SchemaField(
            description="List of releases with their name and file tree browser URL"
        )

    def __init__(self):
        super().__init__(
            id="3460367a-6ba7-4645-8ce6-47b05d040b92",
            description="This block lists all releases for a specified GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubListReleasesBlock.Input,
            output_schema=GithubListReleasesBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "releases",
                    [
                        {
                            "name": "v1.0.0",
                            "url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                        }
                    ],
                ),
                (
                    "release",
                    {
                        "name": "v1.0.0",
                        "url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    },
                ),
            ],
            test_mock={
                "list_releases": lambda *args, **kwargs: [
                    {
                        "name": "v1.0.0",
                        "url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    }
                ]
            },
        )

    @staticmethod
    async def list_releases(
        credentials: GithubCredentials, repo_url: str
    ) -> list[Output.ReleaseItem]:
        api = get_api(credentials)
        releases_url = repo_url + "/releases"
        response = await api.get(releases_url)
        data = response.json()
        releases: list[GithubListReleasesBlock.Output.ReleaseItem] = [
            {"name": release["name"], "url": release["html_url"]} for release in data
        ]
        return releases

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        releases = await self.list_releases(
            credentials,
            input_data.repo_url,
        )
        yield "releases", releases
        for release in releases:
            yield "release", release


