"""Exa webset create/find blocks."""

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

class SearchEntityType(str, Enum):
    COMPANY = "company"
    PERSON = "person"
    ARTICLE = "article"
    RESEARCH_PAPER = "research_paper"
    CUSTOM = "custom"
    AUTO = "auto"


class SearchType(str, Enum):
    IMPORT = "import"
    WEBSET = "webset"


class EnrichmentFormat(str, Enum):
    TEXT = "text"
    DATE = "date"
    NUMBER = "number"
    OPTIONS = "options"
    EMAIL = "email"
    PHONE = "phone"


class Webset(BaseModel):
    id: str
    status: WebsetStatus | None = Field(..., title="WebsetStatus")
    """
    The status of the webset
    """
    external_id: Annotated[Optional[str], Field(alias="externalId")] = None
    """
    The external identifier for the webset
    NOTE: Returning dict to avoid ui crashing due to nested objects
    """
    searches: List[dict[str, Any]] | None = None
    """
    The searches that have been performed on the webset.
    NOTE: Returning dict to avoid ui crashing due to nested objects
    """
    enrichments: List[dict[str, Any]] | None = None
    """
    The Enrichments to apply to the Webset Items.
    NOTE: Returning dict to avoid ui crashing due to nested objects
    """
    monitors: List[dict[str, Any]] | None = None
    """
    The Monitors for the Webset.
    NOTE: Returning dict to avoid ui crashing due to nested objects
    """
    metadata: Optional[Dict[str, Any]] = {}
    """
    Set of key-value pairs you want to associate with this object.
    """
    created_at: Annotated[datetime | None, Field(alias="createdAt")] = None
    """
    The date and time the webset was created
    """
    updated_at: Annotated[datetime | None, Field(alias="updatedAt")] = None
    """
    The date and time the webset was last updated
    """


class ExaCreateWebsetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )

        # Search parameters (flattened)
        search_query: str = SchemaField(
            description="Your search query. Use this to describe what you are looking for. Any URL provided will be crawled and used as context for the search.",
            placeholder="Marketing agencies based in the US, that focus on consumer products",
        )
        search_count: Optional[int] = SchemaField(
            default=10,
            description="Number of items the search will attempt to find. The actual number of items found may be less than this number depending on the search complexity.",
            ge=1,
            le=1000,
        )
        search_entity_type: SearchEntityType = SchemaField(
            default=SearchEntityType.AUTO,
            description="Entity type: 'company', 'person', 'article', 'research_paper', or 'custom'. If not provided, we automatically detect the entity from the query.",
            advanced=True,
        )
        search_entity_description: Optional[str] = SchemaField(
            default=None,
            description="Description for custom entity type (required when search_entity_type is 'custom')",
            advanced=True,
        )

        # Search criteria (flattened)
        search_criteria: list[str] = SchemaField(
            default_factory=list,
            description="List of criteria descriptions that every item will be evaluated against. If not provided, we automatically detect the criteria from the query.",
            advanced=True,
        )

        # Search exclude sources (flattened)
        search_exclude_sources: list[str] = SchemaField(
            default_factory=list,
            description="List of source IDs (imports or websets) to exclude from search results",
            advanced=True,
        )
        search_exclude_types: list[SearchType] = SchemaField(
            default_factory=list,
            description="List of source types corresponding to exclude sources ('import' or 'webset')",
            advanced=True,
        )

        # Search scope sources (flattened)
        search_scope_sources: list[str] = SchemaField(
            default_factory=list,
            description="List of source IDs (imports or websets) to limit search scope to",
            advanced=True,
        )
        search_scope_types: list[SearchType] = SchemaField(
            default_factory=list,
            description="List of source types corresponding to scope sources ('import' or 'webset')",
            advanced=True,
        )
        search_scope_relationships: list[str] = SchemaField(
            default_factory=list,
            description="List of relationship definitions for hop searches (optional, one per scope source)",
            advanced=True,
        )
        search_scope_relationship_limits: list[int] = SchemaField(
            default_factory=list,
            description="List of limits on the number of related entities to find (optional, one per scope relationship)",
            advanced=True,
        )

        # Import parameters (flattened)
        import_sources: list[str] = SchemaField(
            default_factory=list,
            description="List of source IDs to import from",
            advanced=True,
        )
        import_types: list[SearchType] = SchemaField(
            default_factory=list,
            description="List of source types corresponding to import sources ('import' or 'webset')",
            advanced=True,
        )

        # Enrichment parameters (flattened)
        enrichment_descriptions: list[str] = SchemaField(
            default_factory=list,
            description="List of enrichment task descriptions to perform on each webset item",
            advanced=True,
        )
        enrichment_formats: list[EnrichmentFormat] = SchemaField(
            default_factory=list,
            description="List of formats for enrichment responses ('text', 'date', 'number', 'options', 'email', 'phone'). If not specified, we automatically select the best format.",
            advanced=True,
        )
        enrichment_options: list[list[str]] = SchemaField(
            default_factory=list,
            description="List of option lists for enrichments with 'options' format. Each inner list contains the option labels.",
            advanced=True,
        )
        enrichment_metadata: list[dict] = SchemaField(
            default_factory=list,
            description="List of metadata dictionaries for enrichments",
            advanced=True,
        )

        # Webset metadata
        external_id: Optional[str] = SchemaField(
            default=None,
            description="External identifier for the webset. You can use this to reference the webset by your own internal identifiers.",
            placeholder="my-webset-123",
            advanced=True,
        )
        metadata: Optional[dict] = SchemaField(
            default_factory=dict,
            description="Key-value pairs to associate with this webset",
            advanced=True,
        )

        # Polling parameters
        wait_for_initial_results: bool = SchemaField(
            default=True,
            description="Wait for the initial search to complete before returning. This ensures you get results immediately.",
        )
        polling_timeout: int = SchemaField(
            default=300,
            description="Maximum time to wait for completion in seconds (only used if wait_for_initial_results is True)",
            advanced=True,
            ge=1,
            le=600,
        )

    class Output(BlockSchemaOutput):
        webset: Webset = SchemaField(description="The created webset with full details")
        initial_item_count: Optional[int] = SchemaField(
            description="Number of items found in the initial search (only if wait_for_initial_results was True)"
        )
        completion_time: Optional[float] = SchemaField(
            description="Time taken to complete the initial search in seconds (only if wait_for_initial_results was True)"
        )

    def __init__(self):
        super().__init__(
            id="0cda29ff-c549-4a19-8805-c982b7d4ec34",
            description="Create a new Exa Webset for persistent web search collections with optional waiting for initial results",
            categories={BlockCategory.SEARCH},
            input_schema=ExaCreateWebsetBlock.Input,
            output_schema=ExaCreateWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:

        exa = Exa(credentials.api_key.get_secret_value())

        entity = None
        if input_data.search_entity_type == SearchEntityType.COMPANY:
            entity = WebsetCompanyEntity(type="company")
        elif input_data.search_entity_type == SearchEntityType.PERSON:
            entity = WebsetPersonEntity(type="person")
        elif input_data.search_entity_type == SearchEntityType.ARTICLE:
            entity = WebsetArticleEntity(type="article")
        elif input_data.search_entity_type == SearchEntityType.RESEARCH_PAPER:
            entity = WebsetResearchPaperEntity(type="research_paper")
        elif (
            input_data.search_entity_type == SearchEntityType.CUSTOM
            and input_data.search_entity_description
        ):
            entity = WebsetCustomEntity(
                type="custom", description=input_data.search_entity_description
            )

        criteria = None
        if input_data.search_criteria:
            criteria = [
                CreateCriterionParameters(description=item)
                for item in input_data.search_criteria
            ]

        exclude_items = None
        if input_data.search_exclude_sources:
            exclude_items = []
            for idx, src_id in enumerate(input_data.search_exclude_sources):
                src_type = None
                if input_data.search_exclude_types and idx < len(
                    input_data.search_exclude_types
                ):
                    src_type = input_data.search_exclude_types[idx]
                # Default to IMPORT if type missing
                if src_type == SearchType.WEBSET:
                    source_enum = ImportSource.webset
                else:
                    source_enum = ImportSource.import_
                exclude_items.append(ExcludeItem(source=source_enum, id=src_id))

        scope_items = None
        if input_data.search_scope_sources:
            scope_items = []
            for idx, src_id in enumerate(input_data.search_scope_sources):
                src_type = None
                if input_data.search_scope_types and idx < len(
                    input_data.search_scope_types
                ):
                    src_type = input_data.search_scope_types[idx]
                relationship = None
                if input_data.search_scope_relationships and idx < len(
                    input_data.search_scope_relationships
                ):
                    rel_def = input_data.search_scope_relationships[idx]
                    lim = None
                    if input_data.search_scope_relationship_limits and idx < len(
                        input_data.search_scope_relationship_limits
                    ):
                        lim = input_data.search_scope_relationship_limits[idx]
                    relationship = ScopeRelationship(definition=rel_def, limit=lim)
                if src_type == SearchType.WEBSET:
                    src_enum = ScopeSourceType.webset
                else:
                    src_enum = ScopeSourceType.import_
                scope_items.append(
                    ScopeItem(source=src_enum, id=src_id, relationship=relationship)
                )

        search_params = None
        if input_data.search_query:
            search_params = CreateWebsetParametersSearch(
                query=input_data.search_query,
                count=input_data.search_count,
                entity=entity,
                criteria=criteria,
                exclude=exclude_items,
                scope=scope_items,
            )

        imports_params = None
        if input_data.import_sources:
            imports_params = []
            for idx, src_id in enumerate(input_data.import_sources):
                src_type = None
                if input_data.import_types and idx < len(input_data.import_types):
                    src_type = input_data.import_types[idx]
                if src_type == SearchType.WEBSET:
                    source_enum = ImportSource.webset
                else:
                    source_enum = ImportSource.import_
                imports_params.append(ImportItem(source=source_enum, id=src_id))

        enrichments_params = None
        if input_data.enrichment_descriptions:
            enrichments_params = []
            for idx, desc in enumerate(input_data.enrichment_descriptions):
                fmt = None
                if input_data.enrichment_formats and idx < len(
                    input_data.enrichment_formats
                ):
                    fmt_enum = input_data.enrichment_formats[idx]
                    if fmt_enum is not None:
                        fmt = Format(
                            fmt_enum.value if isinstance(fmt_enum, Enum) else fmt_enum
                        )
                options_list = None
                if input_data.enrichment_options and idx < len(
                    input_data.enrichment_options
                ):
                    raw_opts = input_data.enrichment_options[idx]
                    if raw_opts:
                        options_list = [Option(label=o) for o in raw_opts]
                metadata_obj = None
                if input_data.enrichment_metadata and idx < len(
                    input_data.enrichment_metadata
                ):
                    metadata_obj = input_data.enrichment_metadata[idx]
                enrichments_params.append(
                    CreateEnrichmentParameters(
                        description=desc,
                        format=fmt,
                        options=options_list,
                        metadata=metadata_obj,
                    )
                )

        try:
            start_time = time.time()
            webset = exa.websets.create(
                params=CreateWebsetParameters(
                    search=search_params,
                    imports=imports_params,
                    enrichments=enrichments_params,
                    external_id=input_data.external_id,
                    metadata=input_data.metadata,
                )
            )

            webset_result = Webset.model_validate(webset.model_dump(by_alias=True))

            # If wait_for_initial_results is True, poll for completion
            if input_data.wait_for_initial_results and search_params:
                final_webset = exa.websets.wait_until_idle(
                    id=webset_result.id,
                    timeout=input_data.polling_timeout,
                    poll_interval=5,
                )
                completion_time = time.time() - start_time

                item_count = 0
                if final_webset.searches:
                    for search in final_webset.searches:
                        if search.progress:
                            item_count += search.progress.found

                yield "webset", webset_result
                yield "initial_item_count", item_count
                yield "completion_time", completion_time
            else:
                yield "webset", webset_result

        except ValueError as e:
            raise ValueError(f"Invalid webset configuration: {e}") from e


class ExaCreateOrFindWebsetBlock(Block):
    """Create a new webset or return existing one if external_id already exists (idempotent)."""

    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )

        external_id: str = SchemaField(
            description="External identifier for this webset - used to find existing or create new",
            placeholder="my-unique-webset-id",
        )

        search_query: Optional[str] = SchemaField(
            default=None,
            description="Search query (optional - only needed if creating new webset)",
            placeholder="Marketing agencies based in the US",
        )
        search_count: int = SchemaField(
            default=10,
            description="Number of items to find in initial search",
            ge=1,
            le=1000,
        )

        metadata: Optional[dict] = SchemaField(
            default=None,
            description="Key-value pairs to associate with the webset",
            advanced=True,
        )

    class Output(BlockSchemaOutput):
        webset: Webset = SchemaField(
            description="The webset (existing or newly created)"
        )
        was_created: bool = SchemaField(
            description="True if webset was newly created, False if it already existed"
        )

    def __init__(self):
        super().__init__(
            id="214542b6-3603-4bea-bc07-f51c2871cbd9",
            description="Create a new webset or return existing one by external_id (idempotent operation)",
            categories={BlockCategory.SEARCH},
            input_schema=ExaCreateOrFindWebsetBlock.Input,
            output_schema=ExaCreateOrFindWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        import httpx

        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        try:
            webset = aexa.websets.get(id=input_data.external_id)
            webset_result = Webset.model_validate(webset.model_dump(by_alias=True))

            yield "webset", webset_result
            yield "was_created", False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Not found - create new webset
                search_params = None
                if input_data.search_query:
                    search_params = CreateWebsetParametersSearch(
                        query=input_data.search_query,
                        count=input_data.search_count,
                    )

                webset = aexa.websets.create(
                    params=CreateWebsetParameters(
                        search=search_params,
                        external_id=input_data.external_id,
                        metadata=input_data.metadata,
                    )
                )

                webset_result = Webset.model_validate(webset.model_dump(by_alias=True))

                yield "webset", webset_result
                yield "was_created", True
            else:
                # Other HTTP errors should propagate
                raise


class ExaUpdateWebsetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset to update",
            placeholder="webset-id-or-external-id",
        )
        metadata: Optional[dict] = SchemaField(
            default=None,
            description="Key-value pairs to associate with this webset (set to null to clear)",
        )

    class Output(BlockSchemaOutput):
        webset_id: str = SchemaField(description="The unique identifier for the webset")
        status: str = SchemaField(description="The status of the webset")
        external_id: Optional[str] = SchemaField(
            description="The external identifier for the webset"
        )
        metadata: dict = SchemaField(description="Updated metadata for the webset")
        updated_at: str = SchemaField(
            description="The date and time the webset was updated"
        )

    def __init__(self):
        super().__init__(
            id="89ccd99a-3c2b-4fbf-9e25-0ffa398d0314",
            description="Update metadata for an existing Webset",
            categories={BlockCategory.SEARCH},
            input_schema=ExaUpdateWebsetBlock.Input,
            output_schema=ExaUpdateWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        payload = {}
        if input_data.metadata is not None:
            payload["metadata"] = input_data.metadata

        sdk_webset = aexa.websets.update(id=input_data.webset_id, params=payload)

        status_str = (
            sdk_webset.status.value
            if hasattr(sdk_webset.status, "value")
            else str(sdk_webset.status)
        )

        yield "webset_id", sdk_webset.id
        yield "status", status_str
        yield "external_id", sdk_webset.external_id
        yield "metadata", sdk_webset.metadata or {}
        yield "updated_at", (
            sdk_webset.updated_at.isoformat() if sdk_webset.updated_at else ""
        )


