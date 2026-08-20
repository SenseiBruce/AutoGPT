"""Exa webset list/get/delete/cancel blocks."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from exa_py import AsyncExa, Exa
from exa_py.websets.types import (
    CreateCriterionParameters,
    CreateEnrichmentParameters,
    CreateWebsetParameters,
    CreateWebsetParametersSearch,
    ExcludeItem,
    Format,
    ImportItem,
    ImportSource,
    Option,
    ScopeItem,
    ScopeRelationship,
    ScopeSourceType,
    WebsetArticleEntity,
    WebsetCompanyEntity,
    WebsetCustomEntity,
    WebsetPersonEntity,
    WebsetResearchPaperEntity,
    WebsetStatus,
)
from pydantic import Field

from backend.sdk import (
    APIKeyCredentials,
    BaseModel,
    Block,
    BlockCategory,
    BlockOutput,
    BlockSchemaInput,
    BlockSchemaOutput,
    CredentialsMetaInput,
    SchemaField,
)

from ._config import exa

class ExaListWebsetsBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        trigger: Any | None = SchemaField(
            default=None,
            description="Trigger for the webset, value is ignored!",
            advanced=False,
        )
        cursor: Optional[str] = SchemaField(
            default=None,
            description="Cursor for pagination through results",
            advanced=True,
        )
        limit: int = SchemaField(
            default=25,
            description="Number of websets to return (1-100)",
            ge=1,
            le=100,
            advanced=True,
        )

    class Output(BlockSchemaOutput):
        websets: list[Webset] = SchemaField(description="List of websets")
        has_more: bool = SchemaField(
            description="Whether there are more results to paginate through"
        )
        next_cursor: Optional[str] = SchemaField(
            description="Cursor for the next page of results"
        )

    def __init__(self):
        super().__init__(
            id="1dcd8fd6-c13f-4e6f-bd4c-654428fa4757",
            description="List all Websets with pagination support",
            categories={BlockCategory.SEARCH},
            input_schema=ExaListWebsetsBlock.Input,
            output_schema=ExaListWebsetsBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        response = aexa.websets.list(
            cursor=input_data.cursor,
            limit=input_data.limit,
        )

        websets_data = [
            w.model_dump(by_alias=True, exclude_none=True) for w in response.data
        ]

        yield "websets", websets_data
        yield "has_more", response.has_more
        yield "next_cursor", response.next_cursor


class ExaGetWebsetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset to retrieve",
            placeholder="webset-id-or-external-id",
        )

    class Output(BlockSchemaOutput):
        webset_id: str = SchemaField(description="The unique identifier for the webset")
        status: str = SchemaField(description="The status of the webset")
        external_id: Optional[str] = SchemaField(
            description="The external identifier for the webset"
        )
        searches: list[dict] = SchemaField(
            description="The searches performed on the webset"
        )
        enrichments: list[dict] = SchemaField(
            description="The enrichments applied to the webset"
        )
        monitors: list[dict] = SchemaField(description="The monitors for the webset")
        metadata: dict = SchemaField(
            description="Key-value pairs associated with the webset"
        )
        created_at: str = SchemaField(
            description="The date and time the webset was created"
        )
        updated_at: str = SchemaField(
            description="The date and time the webset was last updated"
        )

    def __init__(self):
        super().__init__(
            id="6ab8e12a-132c-41bf-b5f3-d662620fa832",
            description="Retrieve a Webset by ID or external ID",
            categories={BlockCategory.SEARCH},
            input_schema=ExaGetWebsetBlock.Input,
            output_schema=ExaGetWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        sdk_webset = aexa.websets.get(id=input_data.webset_id)

        status_str = (
            sdk_webset.status.value
            if hasattr(sdk_webset.status, "value")
            else str(sdk_webset.status)
        )

        searches_data = [
            s.model_dump(by_alias=True, exclude_none=True)
            for s in sdk_webset.searches or []
        ]
        enrichments_data = [
            e.model_dump(by_alias=True, exclude_none=True)
            for e in sdk_webset.enrichments or []
        ]
        monitors_data = [
            m.model_dump(by_alias=True, exclude_none=True)
            for m in sdk_webset.monitors or []
        ]

        yield "webset_id", sdk_webset.id
        yield "status", status_str
        yield "external_id", sdk_webset.external_id
        yield "searches", searches_data
        yield "enrichments", enrichments_data
        yield "monitors", monitors_data
        yield "metadata", sdk_webset.metadata or {}
        yield "created_at", (
            sdk_webset.created_at.isoformat() if sdk_webset.created_at else ""
        )
        yield "updated_at", (
            sdk_webset.updated_at.isoformat() if sdk_webset.updated_at else ""
        )


class ExaDeleteWebsetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset to delete",
            placeholder="webset-id-or-external-id",
        )

    class Output(BlockSchemaOutput):
        webset_id: str = SchemaField(
            description="The unique identifier for the deleted webset"
        )
        external_id: Optional[str] = SchemaField(
            description="The external identifier for the deleted webset"
        )
        status: str = SchemaField(description="The status of the deleted webset")
        success: str = SchemaField(description="Whether the deletion was successful")

    def __init__(self):
        super().__init__(
            id="aa6994a2-e986-421f-8d4c-7671d3be7b7e",
            description="Delete a Webset and all its items",
            categories={BlockCategory.SEARCH},
            input_schema=ExaDeleteWebsetBlock.Input,
            output_schema=ExaDeleteWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        deleted_webset = aexa.websets.delete(id=input_data.webset_id)

        status_str = (
            deleted_webset.status.value
            if hasattr(deleted_webset.status, "value")
            else str(deleted_webset.status)
        )

        yield "webset_id", deleted_webset.id
        yield "external_id", deleted_webset.external_id
        yield "status", status_str
        yield "success", "true"


class ExaCancelWebsetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset to cancel",
            placeholder="webset-id-or-external-id",
        )

    class Output(BlockSchemaOutput):
        webset_id: str = SchemaField(description="The unique identifier for the webset")
        status: str = SchemaField(
            description="The status of the webset after cancellation"
        )
        external_id: Optional[str] = SchemaField(
            description="The external identifier for the webset"
        )
        success: str = SchemaField(
            description="Whether the cancellation was successful"
        )

    def __init__(self):
        super().__init__(
            id="e40a6420-1db8-47bb-b00a-0e6aecd74176",
            description="Cancel all operations being performed on a Webset",
            categories={BlockCategory.SEARCH},
            input_schema=ExaCancelWebsetBlock.Input,
            output_schema=ExaCancelWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        canceled_webset = aexa.websets.cancel(id=input_data.webset_id)

        status_str = (
            canceled_webset.status.value
            if hasattr(canceled_webset.status, "value")
            else str(canceled_webset.status)
        )

        yield "webset_id", canceled_webset.id
        yield "status", status_str
        yield "external_id", canceled_webset.external_id
        yield "success", "true"


# Mirrored models for Preview response stability
