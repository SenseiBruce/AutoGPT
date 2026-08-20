"""GitHub repository file and branch blocks."""

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

class GithubReadFileBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        file_path: str = SchemaField(
            description="Path to the file in the repository",
            placeholder="path/to/file",
        )
        branch: str = SchemaField(
            description="Branch to read from",
            placeholder="branch_name",
            default="master",
        )

    class Output(BlockSchemaOutput):
        text_content: str = SchemaField(
            description="Content of the file (decoded as UTF-8 text)"
        )
        raw_content: str = SchemaField(
            description="Raw base64-encoded content of the file"
        )
        size: int = SchemaField(description="The size of the file (in bytes)")

    def __init__(self):
        super().__init__(
            id="87ce6c27-5752-4bbc-8e26-6da40a3dcfd3",
            description="This block reads the content of a specified file from a GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubReadFileBlock.Input,
            output_schema=GithubReadFileBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "file_path": "path/to/file",
                "branch": "master",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("raw_content", "RmlsZSBjb250ZW50"),
                ("text_content", "File content"),
                ("size", 13),
            ],
            test_mock={"read_file": lambda *args, **kwargs: ("RmlsZSBjb250ZW50", 13)},
        )

    @staticmethod
    async def read_file(
        credentials: GithubCredentials, repo_url: str, file_path: str, branch: str
    ) -> tuple[str, int]:
        api = get_api(credentials)
        content_url = repo_url + f"/contents/{file_path}?ref={branch}"
        response = await api.get(content_url)
        data = response.json()

        if isinstance(data, list):
            # Multiple entries of different types exist at this path
            if not (file := next((f for f in data if f["type"] == "file"), None)):
                raise TypeError("Not a file")
            data = file

        if data["type"] != "file":
            raise TypeError("Not a file")

        return data["content"], data["size"]

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        content, size = await self.read_file(
            credentials,
            input_data.repo_url,
            input_data.file_path,
            input_data.branch,
        )
        yield "raw_content", content
        yield "text_content", base64.b64decode(content).decode("utf-8")
        yield "size", size


class GithubReadFolderBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        folder_path: str = SchemaField(
            description="Path to the folder in the repository",
            placeholder="path/to/folder",
        )
        branch: str = SchemaField(
            description="Branch name to read from (defaults to master)",
            placeholder="branch_name",
            default="master",
        )

    class Output(BlockSchemaOutput):
        class DirEntry(TypedDict):
            name: str
            path: str

        class FileEntry(TypedDict):
            name: str
            path: str
            size: int

        file: FileEntry = SchemaField(description="Files in the folder")
        dir: DirEntry = SchemaField(description="Directories in the folder")
        error: str = SchemaField(
            description="Error message if reading the folder failed"
        )

    def __init__(self):
        super().__init__(
            id="1355f863-2db3-4d75-9fba-f91e8a8ca400",
            description="This block reads the content of a specified folder from a GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubReadFolderBlock.Input,
            output_schema=GithubReadFolderBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "folder_path": "path/to/folder",
                "branch": "master",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "file",
                    {
                        "name": "file1.txt",
                        "path": "path/to/folder/file1.txt",
                        "size": 1337,
                    },
                ),
                ("dir", {"name": "dir2", "path": "path/to/folder/dir2"}),
            ],
            test_mock={
                "read_folder": lambda *args, **kwargs: (
                    [
                        {
                            "name": "file1.txt",
                            "path": "path/to/folder/file1.txt",
                            "size": 1337,
                        }
                    ],
                    [{"name": "dir2", "path": "path/to/folder/dir2"}],
                )
            },
        )

    @staticmethod
    async def read_folder(
        credentials: GithubCredentials, repo_url: str, folder_path: str, branch: str
    ) -> tuple[list[Output.FileEntry], list[Output.DirEntry]]:
        api = get_api(credentials)
        contents_url = repo_url + f"/contents/{folder_path}?ref={branch}"
        response = await api.get(contents_url)
        data = response.json()

        if not isinstance(data, list):
            raise TypeError("Not a folder")

        files: list[GithubReadFolderBlock.Output.FileEntry] = [
            GithubReadFolderBlock.Output.FileEntry(
                name=entry["name"],
                path=entry["path"],
                size=entry["size"],
            )
            for entry in data
            if entry["type"] == "file"
        ]

        dirs: list[GithubReadFolderBlock.Output.DirEntry] = [
            GithubReadFolderBlock.Output.DirEntry(
                name=entry["name"],
                path=entry["path"],
            )
            for entry in data
            if entry["type"] == "dir"
        ]

        return files, dirs

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        files, dirs = await self.read_folder(
            credentials,
            input_data.repo_url,
            input_data.folder_path.lstrip("/"),
            input_data.branch,
        )
        for file in files:
            yield "file", file
        for dir in dirs:
            yield "dir", dir


class GithubMakeBranchBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        new_branch: str = SchemaField(
            description="Name of the new branch",
            placeholder="new_branch_name",
        )
        source_branch: str = SchemaField(
            description="Name of the source branch",
            placeholder="source_branch_name",
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(description="Status of the branch creation operation")
        error: str = SchemaField(
            description="Error message if the branch creation failed"
        )

    def __init__(self):
        super().__init__(
            id="944cc076-95e7-4d1b-b6b6-b15d8ee5448d",
            description="This block creates a new branch from a specified source branch.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubMakeBranchBlock.Input,
            output_schema=GithubMakeBranchBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "new_branch": "new_branch_name",
                "source_branch": "source_branch_name",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[("status", "Branch created successfully")],
            test_mock={
                "create_branch": lambda *args, **kwargs: "Branch created successfully"
            },
        )

    @staticmethod
    async def create_branch(
        credentials: GithubCredentials,
        repo_url: str,
        new_branch: str,
        source_branch: str,
    ) -> str:
        api = get_api(credentials)
        ref_url = repo_url + f"/git/refs/heads/{source_branch}"
        response = await api.get(ref_url)
        data = response.json()
        sha = data["object"]["sha"]

        # Create the new branch
        new_ref_url = repo_url + "/git/refs"
        data = {
            "ref": f"refs/heads/{new_branch}",
            "sha": sha,
        }
        response = await api.post(new_ref_url, json=data)
        return "Branch created successfully"

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        status = await self.create_branch(
            credentials,
            input_data.repo_url,
            input_data.new_branch,
            input_data.source_branch,
        )
        yield "status", status


class GithubDeleteBranchBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        branch: str = SchemaField(
            description="Name of the branch to delete",
            placeholder="branch_name",
        )

    class Output(BlockSchemaOutput):
        status: str = SchemaField(description="Status of the branch deletion operation")
        error: str = SchemaField(
            description="Error message if the branch deletion failed"
        )

    def __init__(self):
        super().__init__(
            id="0d4130f7-e0ab-4d55-adc3-0a40225e80f4",
            description="This block deletes a specified branch.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubDeleteBranchBlock.Input,
            output_schema=GithubDeleteBranchBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "branch": "branch_name",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[("status", "Branch deleted successfully")],
            test_mock={
                "delete_branch": lambda *args, **kwargs: "Branch deleted successfully"
            },
        )

    @staticmethod
    async def delete_branch(
        credentials: GithubCredentials, repo_url: str, branch: str
    ) -> str:
        api = get_api(credentials)
        ref_url = repo_url + f"/git/refs/heads/{branch}"
        await api.delete(ref_url)
        return "Branch deleted successfully"

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        status = await self.delete_branch(
            credentials,
            input_data.repo_url,
            input_data.branch,
        )
        yield "status", status


class GithubCreateFileBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        file_path: str = SchemaField(
            description="Path where the file should be created",
            placeholder="path/to/file.txt",
        )
        content: str = SchemaField(
            description="Content to write to the file",
            placeholder="File content here",
        )
        branch: str = SchemaField(
            description="Branch where the file should be created",
            default="main",
        )
        commit_message: str = SchemaField(
            description="Message for the commit",
            default="Create new file",
        )

    class Output(BlockSchemaOutput):
        url: str = SchemaField(description="URL of the created file")
        sha: str = SchemaField(description="SHA of the commit")
        error: str = SchemaField(
            description="Error message if the file creation failed"
        )

    def __init__(self):
        super().__init__(
            id="8fd132ac-b917-428a-8159-d62893e8a3fe",
            description="This block creates a new file in a GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubCreateFileBlock.Input,
            output_schema=GithubCreateFileBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "file_path": "test/file.txt",
                "content": "Test content",
                "branch": "main",
                "commit_message": "Create test file",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("url", "https://github.com/owner/repo/blob/main/test/file.txt"),
                ("sha", "abc123"),
            ],
            test_mock={
                "create_file": lambda *args, **kwargs: (
                    "https://github.com/owner/repo/blob/main/test/file.txt",
                    "abc123",
                )
            },
        )

    @staticmethod
    async def create_file(
        credentials: GithubCredentials,
        repo_url: str,
        file_path: str,
        content: str,
        branch: str,
        commit_message: str,
    ) -> tuple[str, str]:
        api = get_api(credentials)
        contents_url = repo_url + f"/contents/{file_path}"
        content_base64 = base64.b64encode(content.encode()).decode()
        data = {
            "message": commit_message,
            "content": content_base64,
            "branch": branch,
        }
        response = await api.put(contents_url, json=data)
        data = response.json()
        return data["content"]["html_url"], data["commit"]["sha"]

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        try:
            url, sha = await self.create_file(
                credentials,
                input_data.repo_url,
                input_data.file_path,
                input_data.content,
                input_data.branch,
                input_data.commit_message,
            )
            yield "url", url
            yield "sha", sha
        except Exception as e:
            yield "error", str(e)


class GithubUpdateFileBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GithubCredentialsInput = GithubCredentialsField("repo")
        repo_url: str = SchemaField(
            description="URL of the GitHub repository",
            placeholder="https://github.com/owner/repo",
        )
        file_path: str = SchemaField(
            description="Path to the file to update",
            placeholder="path/to/file.txt",
        )
        content: str = SchemaField(
            description="New content for the file",
            placeholder="Updated content here",
        )
        branch: str = SchemaField(
            description="Branch containing the file",
            default="main",
        )
        commit_message: str = SchemaField(
            description="Message for the commit",
            default="Update file",
        )

    class Output(BlockSchemaOutput):
        url: str = SchemaField(description="URL of the updated file")
        sha: str = SchemaField(description="SHA of the commit")

    def __init__(self):
        super().__init__(
            id="30be12a4-57cb-4aa4-baf5-fcc68d136076",
            description="This block updates an existing file in a GitHub repository.",
            categories={BlockCategory.DEVELOPER_TOOLS},
            input_schema=GithubUpdateFileBlock.Input,
            output_schema=GithubUpdateFileBlock.Output,
            test_input={
                "repo_url": "https://github.com/owner/repo",
                "file_path": "test/file.txt",
                "content": "Updated content",
                "branch": "main",
                "commit_message": "Update test file",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("url", "https://github.com/owner/repo/blob/main/test/file.txt"),
                ("sha", "def456"),
            ],
            test_mock={
                "update_file": lambda *args, **kwargs: (
                    "https://github.com/owner/repo/blob/main/test/file.txt",
                    "def456",
                )
            },
        )

    @staticmethod
    async def update_file(
        credentials: GithubCredentials,
        repo_url: str,
        file_path: str,
        content: str,
        branch: str,
        commit_message: str,
    ) -> tuple[str, str]:
        api = get_api(credentials)
        contents_url = repo_url + f"/contents/{file_path}"
        params = {"ref": branch}
        response = await api.get(contents_url, params=params)
        data = response.json()

        # Convert new content to base64
        content_base64 = base64.b64encode(content.encode()).decode()
        data = {
            "message": commit_message,
            "content": content_base64,
            "sha": data["sha"],
            "branch": branch,
        }
        response = await api.put(contents_url, json=data)
        data = response.json()
        return data["content"]["html_url"], data["commit"]["sha"]

    async def run(
        self,
        input_data: Input,
        *,
        credentials: GithubCredentials,
        **kwargs,
    ) -> BlockOutput:
        try:
            url, sha = await self.update_file(
                credentials,
                input_data.repo_url,
                input_data.file_path,
                input_data.content,
                input_data.branch,
                input_data.commit_message,
            )
            yield "url", url
            yield "sha", sha
        except Exception as e:
            yield "error", str(e)


