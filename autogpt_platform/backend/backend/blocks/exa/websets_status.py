"""Exa webset preview/status/summary blocks."""

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

class PreviewCriterionModel(BaseModel):
    """Stable model for preview criteria."""

    description: str

    @classmethod
    def from_sdk(cls, sdk_criterion) -> "PreviewCriterionModel":
        """Convert SDK criterion to our model."""
        return cls(description=sdk_criterion.description)


class PreviewEnrichmentModel(BaseModel):
    """Stable model for preview enrichment."""

    description: str
    format: str
    options: List[str]

    @classmethod
    def from_sdk(cls, sdk_enrichment) -> "PreviewEnrichmentModel":
        """Convert SDK enrichment to our model."""
        format_str = (
            sdk_enrichment.format.value
            if hasattr(sdk_enrichment.format, "value")
            else str(sdk_enrichment.format)
        )

        options_list = []
        if sdk_enrichment.options:
            for opt in sdk_enrichment.options:
                opt_dict = opt.model_dump(by_alias=True)
                options_list.append(opt_dict.get("label", ""))

        return cls(
            description=sdk_enrichment.description,
            format=format_str,
            options=options_list,
        )


class PreviewSearchModel(BaseModel):
    """Stable model for preview search details."""

    entity_type: str
    entity_description: Optional[str]
    criteria: List[PreviewCriterionModel]

    @classmethod
    def from_sdk(cls, sdk_search) -> "PreviewSearchModel":
        """Convert SDK search preview to our model."""
        # Extract entity type from union
        entity_dict = sdk_search.entity.model_dump(by_alias=True)
        entity_type = entity_dict.get("type", "auto")
        entity_description = entity_dict.get("description")

        # Convert criteria
        criteria = [
            PreviewCriterionModel.from_sdk(c) for c in sdk_search.criteria or []
        ]

        return cls(
            entity_type=entity_type,
            entity_description=entity_description,
            criteria=criteria,
        )


class PreviewWebsetModel(BaseModel):
    """Stable model for preview response."""

    search: PreviewSearchModel
    enrichments: List[PreviewEnrichmentModel]

    @classmethod
    def from_sdk(cls, sdk_preview) -> "PreviewWebsetModel":
        """Convert SDK PreviewWebsetResponse to our model."""

        search = PreviewSearchModel.from_sdk(sdk_preview.search)
        enrichments = [
            PreviewEnrichmentModel.from_sdk(e) for e in sdk_preview.enrichments or []
        ]

        return cls(search=search, enrichments=enrichments)


class ExaPreviewWebsetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        query: str = SchemaField(
            description="Your search query to preview. Use this to see how Exa will interpret your search before creating a webset.",
            placeholder="Marketing agencies based in the US, with brands worked with and city",
        )
        entity_type: Optional[SearchEntityType] = SchemaField(
            default=None,
            description="Entity type to force: 'company', 'person', 'article', 'research_paper', or 'custom'. If not provided, Exa will auto-detect.",
            advanced=True,
        )
        entity_description: Optional[str] = SchemaField(
            default=None,
            description="Description for custom entity type (required when entity_type is 'custom')",
            advanced=True,
        )

    class Output(BlockSchemaOutput):
        preview: PreviewWebsetModel = SchemaField(
            description="Full preview response with search and enrichment details"
        )
        entity_type: str = SchemaField(
            description="The detected or specified entity type"
        )
        entity_description: Optional[str] = SchemaField(
            description="Description of the entity type"
        )
        criteria: list[PreviewCriterionModel] = SchemaField(
            description="Generated search criteria that will be used"
        )
        enrichment_columns: list[PreviewEnrichmentModel] = SchemaField(
            description="Available enrichment columns that can be extracted"
        )
        interpretation: str = SchemaField(
            description="Human-readable interpretation of how the query will be processed"
        )
        suggestions: list[str] = SchemaField(
            description="Suggestions for improving the query"
        )

    def __init__(self):
        super().__init__(
            id="f8c4e2a1-9b3d-4e5f-a6c7-d8e9f0a1b2c3",
            description="Preview how a search query will be interpreted before creating a webset. Helps understand entity detection, criteria generation, and available enrichments.",
            categories={BlockCategory.SEARCH},
            input_schema=ExaPreviewWebsetBlock.Input,
            output_schema=ExaPreviewWebsetBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        payload: dict[str, Any] = {
            "query": input_data.query,
        }

        if input_data.entity_type:
            entity: dict[str, Any] = {"type": input_data.entity_type.value}
            if (
                input_data.entity_type == SearchEntityType.CUSTOM
                and input_data.entity_description
            ):
                entity["description"] = input_data.entity_description
            payload["entity"] = entity

        sdk_preview = aexa.websets.preview(params=payload)

        preview = PreviewWebsetModel.from_sdk(sdk_preview)

        entity_type = preview.search.entity_type
        entity_description = preview.search.entity_description
        criteria = preview.search.criteria
        enrichments = preview.enrichments

        # Generate interpretation
        interpretation = f"Query will search for {entity_type}"
        if entity_description:
            interpretation += f" ({entity_description})"
        if criteria:
            interpretation += f" with {len(criteria)} criteria"
        if enrichments:
            interpretation += f" and {len(enrichments)} available enrichment columns"

        # Generate suggestions
        suggestions = []
        if not criteria:
            suggestions.append(
                "Consider adding specific criteria to narrow your search"
            )
        if not enrichments:
            suggestions.append(
                "Consider specifying what data points you want to extract"
            )

        # Yield full model first
        yield "preview", preview

        # Then yield individual fields for graph flexibility
        yield "entity_type", entity_type
        yield "entity_description", entity_description
        yield "criteria", criteria
        yield "enrichment_columns", enrichments
        yield "interpretation", interpretation
        yield "suggestions", suggestions


class ExaWebsetStatusBlock(Block):
    """Get a quick status overview of a webset without fetching all details."""

    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset",
            placeholder="webset-id-or-external-id",
        )

    class Output(BlockSchemaOutput):
        webset_id: str = SchemaField(description="The webset identifier")
        status: str = SchemaField(
            description="Current status (idle, running, paused, etc.)"
        )
        item_count: int = SchemaField(description="Total number of items in the webset")
        search_count: int = SchemaField(description="Number of searches performed")
        enrichment_count: int = SchemaField(
            description="Number of enrichments configured"
        )
        monitor_count: int = SchemaField(description="Number of monitors configured")
        last_updated: str = SchemaField(description="When the webset was last updated")
        is_processing: bool = SchemaField(
            description="Whether any operations are currently running"
        )

    def __init__(self):
        super().__init__(
            id="47cc3cd8-840f-4ec4-8d40-fcaba75fbe1a",
            description="Get a quick status overview of a webset",
            categories={BlockCategory.SEARCH},
            input_schema=ExaWebsetStatusBlock.Input,
            output_schema=ExaWebsetStatusBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        webset = aexa.websets.get(id=input_data.webset_id)

        status = (
            webset.status.value
            if hasattr(webset.status, "value")
            else str(webset.status)
        )
        is_processing = status in ["running", "pending"]

        # Estimate item count from search progress
        item_count = 0
        if webset.searches:
            for search in webset.searches:
                if search.progress:
                    item_count += search.progress.found

        # Count searches, enrichments, monitors
        search_count = len(webset.searches or [])
        enrichment_count = len(webset.enrichments or [])
        monitor_count = len(webset.monitors or [])

        yield "webset_id", webset.id
        yield "status", status
        yield "item_count", item_count
        yield "search_count", search_count
        yield "enrichment_count", enrichment_count
        yield "monitor_count", monitor_count
        yield "last_updated", webset.updated_at.isoformat() if webset.updated_at else ""
        yield "is_processing", is_processing


# Summary models for ExaWebsetSummaryBlock
class SearchSummaryModel(BaseModel):
    """Summary of searches in a webset."""

    total_searches: int
    completed_searches: int
    total_items_found: int
    queries: List[str]


class EnrichmentSummaryModel(BaseModel):
    """Summary of enrichments in a webset."""

    total_enrichments: int
    completed_enrichments: int
    enrichment_types: List[str]
    titles: List[str]


class MonitorSummaryModel(BaseModel):
    """Summary of monitors in a webset."""

    total_monitors: int
    active_monitors: int
    next_run: Optional[datetime] = None


class WebsetStatisticsModel(BaseModel):
    """Various statistics about a webset."""

    total_operations: int
    is_processing: bool
    has_monitors: bool
    avg_items_per_search: float


class ExaWebsetSummaryBlock(Block):
    """Get a comprehensive summary of a webset including samples and statistics."""

    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset",
            placeholder="webset-id-or-external-id",
        )
        include_sample_items: bool = SchemaField(
            default=True,
            description="Include sample items in the summary",
        )
        sample_size: int = SchemaField(
            default=3,
            description="Number of sample items to include",
            ge=0,
            le=10,
        )
        include_search_details: bool = SchemaField(
            default=True,
            description="Include details about searches",
        )
        include_enrichment_details: bool = SchemaField(
            default=True,
            description="Include details about enrichments",
        )

    class Output(BlockSchemaOutput):
        webset_id: str = SchemaField(description="The webset identifier")
        status: str = SchemaField(description="Current status")
        entity_type: str = SchemaField(description="Type of entities in the webset")
        total_items: int = SchemaField(description="Total number of items")
        sample_items: list[Dict[str, Any]] = SchemaField(
            description="Sample items from the webset"
        )
        search_summary: SearchSummaryModel = SchemaField(
            description="Summary of searches performed"
        )
        enrichment_summary: EnrichmentSummaryModel = SchemaField(
            description="Summary of enrichments applied"
        )
        monitor_summary: MonitorSummaryModel = SchemaField(
            description="Summary of monitors configured"
        )
        statistics: WebsetStatisticsModel = SchemaField(
            description="Various statistics about the webset"
        )
        created_at: str = SchemaField(description="When the webset was created")
        updated_at: str = SchemaField(description="When the webset was last updated")

    def __init__(self):
        super().__init__(
            id="9eff1710-a49b-490e-b486-197bf8b23c61",
            description="Get a comprehensive summary of a webset with samples and statistics",
            categories={BlockCategory.SEARCH},
            input_schema=ExaWebsetSummaryBlock.Input,
            output_schema=ExaWebsetSummaryBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        webset = aexa.websets.get(id=input_data.webset_id)

        # Extract basic info
        webset_id = webset.id
        status = (
            webset.status.value
            if hasattr(webset.status, "value")
            else str(webset.status)
        )

        # Determine entity type from searches
        entity_type = "unknown"
        searches = webset.searches or []
        if searches:
            first_search = searches[0]
            if first_search.entity:
                entity_dict = first_search.entity.model_dump(
                    by_alias=True, exclude_none=True
                )
                entity_type = entity_dict.get("type", "unknown")

        # Get sample items if requested
        sample_items_data = []
        total_items = 0

        if input_data.include_sample_items and input_data.sample_size > 0:
            items_response = aexa.websets.items.list(
                webset_id=input_data.webset_id, limit=input_data.sample_size
            )
            sample_items_data = [
                item.model_dump(by_alias=True, exclude_none=True)
                for item in items_response.data
            ]
            total_items = len(sample_items_data)

        # Build search summary using Pydantic model
        search_summary = SearchSummaryModel(
            total_searches=0,
            completed_searches=0,
            total_items_found=0,
            queries=[],
        )
        if input_data.include_search_details and searches:
            search_summary = SearchSummaryModel(
                total_searches=len(searches),
                completed_searches=sum(
                    1
                    for s in searches
                    if (s.status.value if hasattr(s.status, "value") else str(s.status))
                    == "completed"
                ),
                total_items_found=int(
                    sum(s.progress.found if s.progress else 0 for s in searches)
                ),
                queries=[s.query for s in searches[:3]],  # First 3 queries
            )

        # Build enrichment summary using Pydantic model
        enrichment_summary = EnrichmentSummaryModel(
            total_enrichments=0,
            completed_enrichments=0,
            enrichment_types=[],
            titles=[],
        )
        enrichments = webset.enrichments or []
        if input_data.include_enrichment_details and enrichments:
            enrichment_summary = EnrichmentSummaryModel(
                total_enrichments=len(enrichments),
                completed_enrichments=sum(
                    1
                    for e in enrichments
                    if (e.status.value if hasattr(e.status, "value") else str(e.status))
                    == "completed"
                ),
                enrichment_types=list(
                    set(
                        (
                            e.format.value
                            if e.format and hasattr(e.format, "value")
                            else str(e.format) if e.format else "text"
                        )
                        for e in enrichments
                    )
                ),
                titles=[(e.title or e.description or "")[:50] for e in enrichments[:3]],
            )

        # Build monitor summary using Pydantic model
        monitors = webset.monitors or []
        next_run_dt = None
        if monitors:
            next_runs = [m.next_run_at for m in monitors if m.next_run_at]
            if next_runs:
                next_run_dt = min(next_runs)

        monitor_summary = MonitorSummaryModel(
            total_monitors=len(monitors),
            active_monitors=sum(
                1
                for m in monitors
                if (m.status.value if hasattr(m.status, "value") else str(m.status))
                == "enabled"
            ),
            next_run=next_run_dt,
        )

        # Build statistics using Pydantic model
        statistics = WebsetStatisticsModel(
            total_operations=len(searches) + len(enrichments),
            is_processing=status in ["running", "pending"],
            has_monitors=len(monitors) > 0,
            avg_items_per_search=(
                search_summary.total_items_found / len(searches) if searches else 0
            ),
        )

        yield "webset_id", webset_id
        yield "status", status
        yield "entity_type", entity_type
        yield "total_items", total_items
        yield "sample_items", sample_items_data
        yield "search_summary", search_summary
        yield "enrichment_summary", enrichment_summary
        yield "monitor_summary", monitor_summary
        yield "statistics", statistics
        yield "created_at", webset.created_at.isoformat() if webset.created_at else ""
        yield "updated_at", webset.updated_at.isoformat() if webset.updated_at else ""


class ExaWebsetReadyCheckBlock(Block):
    """Check if a webset is ready for the next operation (conditional workflow helper)."""

    class Input(BlockSchemaInput):
        credentials: CredentialsMetaInput = exa.credentials_field(
            description="The Exa integration requires an API Key."
        )
        webset_id: str = SchemaField(
            description="The ID or external ID of the Webset to check",
            placeholder="webset-id-or-external-id",
        )
        min_items: int = SchemaField(
            default=1,
            description="Minimum number of items required to be 'ready'",
            ge=0,
        )

    class Output(BlockSchemaOutput):
        is_ready: bool = SchemaField(
            description="True if webset is idle AND has minimum items"
        )
        status: str = SchemaField(description="Current webset status")
        item_count: int = SchemaField(description="Number of items in webset")
        has_searches: bool = SchemaField(
            description="Whether webset has any searches configured"
        )
        has_enrichments: bool = SchemaField(
            description="Whether webset has any enrichments"
        )
        recommendation: str = SchemaField(
            description="Suggested next action (ready_to_process, waiting_for_results, needs_search, etc.)"
        )

    def __init__(self):
        super().__init__(
            id="faf9f0f3-e659-4264-b33b-284a02166bec",
            description="Check if webset is ready for next operation - enables conditional workflow branching",
            categories={BlockCategory.SEARCH, BlockCategory.LOGIC},
            input_schema=ExaWebsetReadyCheckBlock.Input,
            output_schema=ExaWebsetReadyCheckBlock.Output,
        )

    async def run(
        self, input_data: Input, *, credentials: APIKeyCredentials, **kwargs
    ) -> BlockOutput:
        aexa = AsyncExa(api_key=credentials.api_key.get_secret_value())

        # Get webset details
        webset = aexa.websets.get(id=input_data.webset_id)

        status = (
            webset.status.value
            if hasattr(webset.status, "value")
            else str(webset.status)
        )

        # Estimate item count from search progress
        item_count = 0
        if webset.searches:
            for search in webset.searches:
                if search.progress:
                    item_count += search.progress.found

        # Determine readiness
        is_idle = status == "idle"
        has_min_items = item_count >= input_data.min_items
        is_ready = is_idle and has_min_items

        # Check resources
        has_searches = len(webset.searches or []) > 0
        has_enrichments = len(webset.enrichments or []) > 0

        # Generate recommendation
        recommendation = ""
        if not has_searches:
            recommendation = "needs_search"
        elif status in ["running", "pending"]:
            recommendation = "waiting_for_results"
        elif not has_min_items:
            recommendation = "insufficient_items"
        elif not has_enrichments:
            recommendation = "ready_to_enrich"
        else:
            recommendation = "ready_to_process"

        yield "is_ready", is_ready
        yield "status", status
        yield "item_count", item_count
        yield "has_searches", has_searches
        yield "has_enrichments", has_enrichments
        yield "recommendation", recommendation
