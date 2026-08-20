"""Graph domain models."""

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Optional, cast

from prisma.enums import SubmissionStatus
from prisma.models import (
    AgentGraph,
    AgentNode,
    AgentNodeLink,
    LibraryAgent,
    StoreListingVersion,
)
from prisma.types import (
    AgentGraphCreateInput,
    AgentGraphWhereInput,
    AgentNodeCreateInput,
    AgentNodeLinkCreateInput,
)
from pydantic import BaseModel, Field, create_model
from pydantic.fields import computed_field

from backend.blocks.agent import AgentExecutorBlock
from backend.blocks.io import AgentInputBlock, AgentOutputBlock
from backend.blocks.llm import LlmModel
from backend.data.db import prisma as db
from backend.data.dynamic_fields import extract_base_field_name
from backend.data.includes import MAX_GRAPH_VERSIONS_FETCH
from backend.data.model import (
    CredentialsField,
    CredentialsFieldInfo,
    CredentialsMetaInput,
    is_credentials_field_name,
)
from backend.integrations.providers import ProviderName
from backend.util import type as type_utils
from backend.util.exceptions import GraphNotAccessibleError, GraphNotInLibraryError
from backend.util.json import SafeJson
from backend.util.models import Pagination

from .block import (
    AnyBlockSchema,
    Block,
    BlockInput,
    BlockSchema,
    BlockType,
    EmptySchema,
    get_block,
    get_blocks,
)
from .db import BaseDbModel, query_raw_with_schema, transaction
from .includes import AGENT_GRAPH_INCLUDE, AGENT_NODE_INCLUDE

if TYPE_CHECKING:
    from .execution import NodesInputMasks
    from .integrations import Webhook

logger = logging.getLogger(__name__)


class Link(BaseDbModel):
    source_id: str
    sink_id: str
    source_name: str
    sink_name: str
    is_static: bool = False

    @staticmethod
    def from_db(link: AgentNodeLink):
        return Link(
            id=link.id,
            source_name=link.sourceName,
            source_id=link.agentNodeSourceId,
            sink_name=link.sinkName,
            sink_id=link.agentNodeSinkId,
            is_static=link.isStatic,
        )

    def __hash__(self):
        return hash((self.source_id, self.sink_id, self.source_name, self.sink_name))


class Node(BaseDbModel):
    block_id: str
    input_default: BlockInput = {}  # dict[input_name, default_value]
    metadata: dict[str, Any] = {}
    input_links: list[Link] = []
    output_links: list[Link] = []

    @property
    def block(self) -> AnyBlockSchema | "_UnknownBlockBase":
        """Get the block for this node. Returns UnknownBlock if block is deleted/missing."""
        block = get_block(self.block_id)
        if not block:
            # Log warning but don't raise exception - return a placeholder block for deleted blocks
            logger.warning(
                f"Block #{self.block_id} does not exist for Node #{self.id} (deleted/missing block), using UnknownBlock"
            )
            return _UnknownBlockBase(self.block_id)
        return block


class NodeModel(Node):
    graph_id: str
    graph_version: int

    webhook_id: Optional[str] = None
    webhook: Optional["Webhook"] = None

    @staticmethod
    def from_db(node: AgentNode, for_export: bool = False) -> "NodeModel":
        from .integrations import Webhook

        obj = NodeModel(
            id=node.id,
            block_id=node.agentBlockId,
            input_default=type_utils.convert(node.constantInput, dict[str, Any]),
            metadata=type_utils.convert(node.metadata, dict[str, Any]),
            graph_id=node.agentGraphId,
            graph_version=node.agentGraphVersion,
            webhook_id=node.webhookId,
            webhook=Webhook.from_db(node.Webhook) if node.Webhook else None,
        )
        obj.input_links = [Link.from_db(link) for link in node.Input or []]
        obj.output_links = [Link.from_db(link) for link in node.Output or []]
        if for_export:
            return obj.stripped_for_export()
        return obj

    def is_triggered_by_event_type(self, event_type: str) -> bool:
        return self.block.is_triggered_by_event_type(self.input_default, event_type)

    def stripped_for_export(self) -> "NodeModel":
        """
        Returns a copy of the node model, stripped of any non-transferable properties
        """
        stripped_node = self.model_copy(deep=True)

        # Remove credentials and other (possible) secrets from node input
        if stripped_node.input_default:
            stripped_node.input_default = NodeModel._filter_secrets_from_node_input(
                stripped_node.input_default, self.block.input_schema.jsonschema()
            )

        # Remove default secret value from secret input nodes
        if (
            stripped_node.block.block_type == BlockType.INPUT
            and stripped_node.input_default.get("secret", False) is True
            and "value" in stripped_node.input_default
        ):
            del stripped_node.input_default["value"]

        # Remove webhook info
        stripped_node.webhook_id = None
        stripped_node.webhook = None

        return stripped_node

    @staticmethod
    def _filter_secrets_from_node_input(
        input_data: dict[str, Any], schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        sensitive_keys = ["credentials", "api_key", "password", "token", "secret"]
        field_schemas = schema.get("properties", {}) if schema else {}
        result = {}
        for key, value in input_data.items():
            field_schema: dict | None = field_schemas.get(key)
            if (field_schema and field_schema.get("secret", False)) or (
                any(sensitive_key in key.lower() for sensitive_key in sensitive_keys)
                # Prevent removing `secret` flag on input nodes
                and type(value) is not bool
            ):
                # This is a secret value -> filter this key-value pair out
                continue
            elif isinstance(value, dict):
                result[key] = NodeModel._filter_secrets_from_node_input(
                    value, field_schema
                )
            else:
                result[key] = value
        return result


class BaseGraph(BaseDbModel):
    version: int = 1
    is_active: bool = True
    name: str
    description: str
    instructions: str | None = None
    recommended_schedule_cron: str | None = None
    nodes: list[Node] = []
    links: list[Link] = []
    forked_from_id: str | None = None
    forked_from_version: int | None = None

    @computed_field
    @property
    def input_schema(self) -> dict[str, Any]:
        return self._generate_schema(
            *(
                (block.input_schema, node.input_default)
                for node in self.nodes
                if (block := node.block).block_type == BlockType.INPUT
                and issubclass(block.input_schema, AgentInputBlock.Input)
            )
        )

    @computed_field
    @property
    def output_schema(self) -> dict[str, Any]:
        return self._generate_schema(
            *(
                (block.input_schema, node.input_default)
                for node in self.nodes
                if (block := node.block).block_type == BlockType.OUTPUT
                and issubclass(block.input_schema, AgentOutputBlock.Input)
            )
        )

    @computed_field
    @property
    def has_external_trigger(self) -> bool:
        return self.webhook_input_node is not None

    @property
    def webhook_input_node(self) -> Node | None:
        return next(
            (
                node
                for node in self.nodes
                if node.block.block_type
                in (BlockType.WEBHOOK, BlockType.WEBHOOK_MANUAL)
            ),
            None,
        )

    @computed_field
    @property
    def trigger_setup_info(self) -> "GraphTriggerInfo | None":
        if not (
            self.webhook_input_node
            and (trigger_block := self.webhook_input_node.block).webhook_config
        ):
            return None

        return GraphTriggerInfo(
            provider=trigger_block.webhook_config.provider,
            config_schema={
                **(json_schema := trigger_block.input_schema.jsonschema()),
                "properties": {
                    pn: sub_schema
                    for pn, sub_schema in json_schema["properties"].items()
                    if not is_credentials_field_name(pn)
                },
                "required": [
                    pn
                    for pn in json_schema.get("required", [])
                    if not is_credentials_field_name(pn)
                ],
            },
            credentials_input_name=next(
                iter(trigger_block.input_schema.get_credentials_fields()), None
            ),
        )

    @staticmethod
    def _generate_schema(
        *props: tuple[type[AgentInputBlock.Input] | type[AgentOutputBlock.Input], dict],
    ) -> dict[str, Any]:
        schema_fields: list[AgentInputBlock.Input | AgentOutputBlock.Input] = []
        for type_class, input_default in props:
            try:
                schema_fields.append(type_class.model_construct(**input_default))
            except Exception as e:
                logger.error(f"Invalid {type_class}: {input_default}, {e}")

        return {
            "type": "object",
            "properties": {
                p.name: {
                    **{
                        k: v
                        for k, v in p.generate_schema().items()
                        if k not in ["description", "default"]
                    },
                    "secret": p.secret,
                    # Default value has to be set for advanced fields.
                    "advanced": p.advanced and p.value is not None,
                    "title": p.title or p.name,
                    **({"description": p.description} if p.description else {}),
                    **({"default": p.value} if p.value is not None else {}),
                }
                for p in schema_fields
            },
            "required": [p.name for p in schema_fields if p.value is None],
        }


class GraphTriggerInfo(BaseModel):
    provider: ProviderName
    config_schema: dict[str, Any] = Field(
        description="Input schema for the trigger block"
    )
    credentials_input_name: Optional[str]


class Graph(BaseGraph):
    sub_graphs: list[BaseGraph] = []  # Flattened sub-graphs

    @computed_field
    @property
    def credentials_input_schema(self) -> dict[str, Any]:
        return self._credentials_input_schema.jsonschema()

    @property
    def _credentials_input_schema(self) -> type[BlockSchema]:
        graph_credentials_inputs = self.aggregate_credentials_inputs()
        logger.debug(
            f"Combined credentials input fields for graph #{self.id} ({self.name}): "
            f"{graph_credentials_inputs}"
        )

        # Warn if same-provider credentials inputs can't be combined (= bad UX)
        graph_cred_fields = list(graph_credentials_inputs.values())
        for i, (field, keys) in enumerate(graph_cred_fields):
            for other_field, other_keys in list(graph_cred_fields)[i + 1 :]:
                if field.provider != other_field.provider:
                    continue
                if ProviderName.HTTP in field.provider:
                    continue

                # If this happens, that means a block implementation probably needs
                # to be updated.
                logger.warning(
                    "Multiple combined credentials fields "
                    f"for provider {field.provider} "
                    f"on graph #{self.id} ({self.name}); "
                    f"fields: {field} <> {other_field};"
                    f"keys: {keys} <> {other_keys}."
                )

        fields: dict[str, tuple[type[CredentialsMetaInput], CredentialsMetaInput]] = {
            agg_field_key: (
                CredentialsMetaInput[
                    Literal[tuple(field_info.provider)],  # type: ignore
                    Literal[tuple(field_info.supported_types)],  # type: ignore
                ],
                CredentialsField(
                    required_scopes=set(field_info.required_scopes or []),
                    discriminator=field_info.discriminator,
                    discriminator_mapping=field_info.discriminator_mapping,
                    discriminator_values=field_info.discriminator_values,
                ),
            )
            for agg_field_key, (field_info, _) in graph_credentials_inputs.items()
        }

        return create_model(
            self.name.replace(" ", "") + "CredentialsInputSchema",
            __base__=BlockSchema,
            **fields,  # type: ignore
        )

    def aggregate_credentials_inputs(
        self,
    ) -> dict[str, tuple[CredentialsFieldInfo, set[tuple[str, str]]]]:
        """
        Returns:
            dict[aggregated_field_key, tuple(
                CredentialsFieldInfo: A spec for one aggregated credentials field
                    (now includes discriminator_values from matching nodes)
                set[(node_id, field_name)]: Node credentials fields that are
                    compatible with this aggregated field spec
            )]
        """
        # First collect all credential field data with input defaults
        node_credential_data = []

        for graph in [self] + self.sub_graphs:
            for node in graph.nodes:
                for (
                    field_name,
                    field_info,
                ) in node.block.input_schema.get_credentials_fields_info().items():

                    discriminator = field_info.discriminator
                    if not discriminator:
                        node_credential_data.append((field_info, (node.id, field_name)))
                        continue

                    discriminator_value = node.input_default.get(discriminator)
                    if discriminator_value is None:
                        node_credential_data.append((field_info, (node.id, field_name)))
                        continue

                    discriminated_info = field_info.discriminate(discriminator_value)
                    discriminated_info.discriminator_values.add(discriminator_value)

                    node_credential_data.append(
                        (discriminated_info, (node.id, field_name))
                    )

        # Combine credential field info (this will merge discriminator_values automatically)
        return CredentialsFieldInfo.combine(*node_credential_data)


class GraphModel(Graph):
    user_id: str
    nodes: list[NodeModel] = []  # type: ignore

    created_at: datetime

    @property
    def starting_nodes(self) -> list[NodeModel]:
        outbound_nodes = {link.sink_id for link in self.links}
        input_nodes = {
            node.id for node in self.nodes if node.block.block_type == BlockType.INPUT
        }
        return [
            node
            for node in self.nodes
            if node.id not in outbound_nodes or node.id in input_nodes
        ]

    @property
    def webhook_input_node(self) -> NodeModel | None:  # type: ignore
        return cast(NodeModel, super().webhook_input_node)

    def meta(self) -> "GraphMeta":
        """
        Returns a GraphMeta object with metadata about the graph.
        This is used to return metadata about the graph without exposing nodes and links.
        """
        return GraphMeta.from_graph(self)

    def reassign_ids(self, user_id: str, reassign_graph_id: bool = False):
        """
        Reassigns all IDs in the graph to new UUIDs.
        This method can be used before storing a new graph to the database.
        """
        if reassign_graph_id:
            graph_id_map = {
                self.id: str(uuid.uuid4()),
                **{sub_graph.id: str(uuid.uuid4()) for sub_graph in self.sub_graphs},
            }
        else:
            graph_id_map = {}

        self._reassign_ids(self, user_id, graph_id_map)
        for sub_graph in self.sub_graphs:
            self._reassign_ids(sub_graph, user_id, graph_id_map)

    @staticmethod
    def _reassign_ids(
        graph: BaseGraph,
        user_id: str,
        graph_id_map: dict[str, str],
    ):
        # Reassign Graph ID
        if graph.id in graph_id_map:
            graph.id = graph_id_map[graph.id]

        # Reassign Node IDs
        id_map = {node.id: str(uuid.uuid4()) for node in graph.nodes}
        for node in graph.nodes:
            node.id = id_map[node.id]

        # Reassign Link IDs
        for link in graph.links:
            if link.source_id in id_map:
                link.source_id = id_map[link.source_id]
            if link.sink_id in id_map:
                link.sink_id = id_map[link.sink_id]

        # Reassign User IDs for agent blocks
        for node in graph.nodes:
            if node.block_id != AgentExecutorBlock().id:
                continue
            node.input_default["user_id"] = user_id
            node.input_default.setdefault("inputs", {})
            if (
                graph_id := node.input_default.get("graph_id")
            ) and graph_id in graph_id_map:
                node.input_default["graph_id"] = graph_id_map[graph_id]

    def validate_graph(
        self,
        for_run: bool = False,
        nodes_input_masks: Optional["NodesInputMasks"] = None,
    ):
        """
        Validate graph structure and raise `ValueError` on issues.
        For structured error reporting, use `validate_graph_get_errors`.
        """
        self._validate_graph(self, for_run, nodes_input_masks)
        for sub_graph in self.sub_graphs:
            self._validate_graph(sub_graph, for_run, nodes_input_masks)

    @staticmethod
    def _validate_graph(
        graph: BaseGraph,
        for_run: bool = False,
        nodes_input_masks: Optional["NodesInputMasks"] = None,
    ) -> None:
        errors = GraphModel._validate_graph_get_errors(
            graph, for_run, nodes_input_masks
        )
        if errors:
            # Just raise the first error for backward compatibility
            first_error = next(iter(errors.values()))
            first_field_error = next(iter(first_error.values()))
            raise ValueError(first_field_error)

    def validate_graph_get_errors(
        self,
        for_run: bool = False,
        nodes_input_masks: Optional["NodesInputMasks"] = None,
    ) -> dict[str, dict[str, str]]:
        """
        Validate graph and return structured errors per node.

        Returns: dict[node_id, dict[field_name, error_message]]
        """
        return {
            **self._validate_graph_get_errors(self, for_run, nodes_input_masks),
            **{
                node_id: error
                for sub_graph in self.sub_graphs
                for node_id, error in self._validate_graph_get_errors(
                    sub_graph, for_run, nodes_input_masks
                ).items()
            },
        }

    @staticmethod
    def _validate_graph_get_errors(
        graph: BaseGraph,
        for_run: bool = False,
        nodes_input_masks: Optional["NodesInputMasks"] = None,
    ) -> dict[str, dict[str, str]]:
        """
        Validate graph and return structured errors per node.

        Returns: dict[node_id, dict[field_name, error_message]]
        """
        # First, check for structural issues with the graph
        try:
            GraphModel._validate_graph_structure(graph)
        except ValueError:
            # If structural validation fails, we can't provide per-node errors
            # so we re-raise as is
            raise

        # Collect errors per node
        node_errors: dict[str, dict[str, str]] = defaultdict(dict)

        # Validate smart decision maker nodes
        nodes_block = {
            node.id: block
            for node in graph.nodes
            if (block := get_block(node.block_id)) is not None
        }

        input_links: dict[str, list[Link]] = defaultdict(list)

        for link in graph.links:
            input_links[link.sink_id].append(link)

        # Nodes: required fields are filled or connected and dependencies are satisfied
        for node in graph.nodes:
            if (block := nodes_block.get(node.id)) is None:
                # For invalid blocks, we still raise immediately as this is a structural issue
                raise ValueError(f"Invalid block {node.block_id} for node #{node.id}")

            node_input_mask = (
                nodes_input_masks.get(node.id, {}) if nodes_input_masks else {}
            )
            provided_inputs = set(
                [_sanitize_pin_name(name) for name in node.input_default]
                + [
                    _sanitize_pin_name(link.sink_name)
                    for link in input_links.get(node.id, [])
                ]
                + ([name for name in node_input_mask] if node_input_mask else [])
            )
            InputSchema = block.input_schema

            for name in (required_fields := InputSchema.get_required_fields()):
                if (
                    name not in provided_inputs
                    # Checking availability of credentials is done by ExecutionManager
                    and name not in InputSchema.get_credentials_fields()
                    # Validate only I/O nodes, or validate everything when executing
                    and (
                        for_run
                        or block.block_type
                        in [
                            BlockType.INPUT,
                            BlockType.OUTPUT,
                            BlockType.AGENT,
                        ]
                    )
                ):
                    node_errors[node.id][name] = "This field is required"

                if (
                    block.block_type == BlockType.INPUT
                    and (input_key := node.input_default.get("name"))
                    and is_credentials_field_name(input_key)
                ):
                    node_errors[node.id]["name"] = (
                        f"'{input_key}' is a reserved input name: "
                        "'credentials' and `*_credentials` are reserved"
                    )

            # Get input schema properties and check dependencies
            input_fields = InputSchema.model_fields

            def has_value(node: Node, name: str):
                return (
                    (
                        name in node.input_default
                        and node.input_default[name] is not None
                        and str(node.input_default[name]).strip() != ""
                    )
                    or (name in input_fields and input_fields[name].default is not None)
                    or (
                        name in node_input_mask
                        and node_input_mask[name] is not None
                        and str(node_input_mask[name]).strip() != ""
                    )
                )

            # Validate dependencies between fields
            for field_name in input_fields.keys():
                field_json_schema = InputSchema.get_field_schema(field_name)

                dependencies: list[str] = []

                # Check regular field dependencies (only pre graph execution)
                if for_run:
                    dependencies.extend(field_json_schema.get("depends_on", []))

                # Require presence of credentials discriminator (always).
                # The `discriminator` is either the name of a sibling field (str),
                # or an object that discriminates between possible types for this field:
                # {"propertyName": prop_name, "mapping": {prop_value: sub_schema}}
                if (
                    discriminator := field_json_schema.get("discriminator")
                ) and isinstance(discriminator, str):
                    dependencies.append(discriminator)

                if not dependencies:
                    continue

                # Check if dependent field has value in input_default
                field_has_value = has_value(node, field_name)
                field_is_required = field_name in required_fields

                # Check for missing dependencies when dependent field is present
                missing_deps = [dep for dep in dependencies if not has_value(node, dep)]
                if missing_deps and (field_has_value or field_is_required):
                    node_errors[node.id][
                        field_name
                    ] = f"Requires {', '.join(missing_deps)} to be set"

        return node_errors

    @staticmethod
    def _validate_graph_structure(graph: BaseGraph):
        """Validate graph structure (links, connections, etc.)"""
        node_map = {v.id: v for v in graph.nodes}

        def is_static_output_block(nid: str) -> bool:
            return node_map[nid].block.static_output

        # Links: links are connected and the connected pin data type are compatible.
        for link in graph.links:
            source = (link.source_id, link.source_name)
            sink = (link.sink_id, link.sink_name)
            prefix = f"Link {source} <-> {sink}"

            for i, (node_id, name) in enumerate([source, sink]):
                node = node_map.get(node_id)
                if not node:
                    raise ValueError(
                        f"{prefix}, {node_id} is invalid node id, available nodes: {node_map.keys()}"
                    )

                block = get_block(node.block_id)
                if not block:
                    blocks = {v().id: v().name for v in get_blocks().values()}
                    raise ValueError(
                        f"{prefix}, {node.block_id} is invalid block id, available blocks: {blocks}"
                    )

                sanitized_name = _sanitize_pin_name(name)
                vals = node.input_default
                if i == 0:
                    fields = (
                        block.output_schema.get_fields()
                        if block.block_type not in [BlockType.AGENT]
                        else vals.get("output_schema", {}).get("properties", {}).keys()
                    )
                else:
                    fields = (
                        block.input_schema.get_fields()
                        if block.block_type not in [BlockType.AGENT]
                        else vals.get("input_schema", {}).get("properties", {}).keys()
                    )
                if sanitized_name not in fields and not _is_tool_pin(name):
                    fields_msg = f"Allowed fields: {fields}"
                    raise ValueError(f"{prefix}, `{name}` invalid, {fields_msg}")

            if is_static_output_block(link.source_id):
                link.is_static = True  # Each value block output should be static.

    @staticmethod
    def from_db(
        graph: AgentGraph,
        for_export: bool = False,
        sub_graphs: list[AgentGraph] | None = None,
    ) -> "GraphModel":
        return GraphModel(
            id=graph.id,
            user_id=graph.userId if not for_export else "",
            version=graph.version,
            forked_from_id=graph.forkedFromId,
            forked_from_version=graph.forkedFromVersion,
            created_at=graph.createdAt,
            is_active=graph.isActive,
            name=graph.name or "",
            description=graph.description or "",
            instructions=graph.instructions,
            recommended_schedule_cron=graph.recommendedScheduleCron,
            nodes=[NodeModel.from_db(node, for_export) for node in graph.Nodes or []],
            links=list(
                {
                    Link.from_db(link)
                    for node in graph.Nodes or []
                    for link in (node.Input or []) + (node.Output or [])
                }
            ),
            sub_graphs=[
                GraphModel.from_db(sub_graph, for_export)
                for sub_graph in sub_graphs or []
            ],
        )


def _is_tool_pin(name: str) -> bool:
    return name.startswith("tools_^_")


def _sanitize_pin_name(name: str) -> str:
    sanitized_name = extract_base_field_name(name)
    if _is_tool_pin(sanitized_name):
        return "tools"
    return sanitized_name


class GraphMeta(Graph):
    user_id: str

    # Easy work-around to prevent exposing nodes and links in the API response
    nodes: list[NodeModel] = Field(default=[], exclude=True)  # type: ignore
    links: list[Link] = Field(default=[], exclude=True)

    @staticmethod
    def from_graph(graph: GraphModel) -> "GraphMeta":
        return GraphMeta(**graph.model_dump())


class GraphsPaginated(BaseModel):
    """Response schema for paginated graphs."""

    graphs: list[GraphMeta]
    pagination: Pagination


# Simple placeholder class for deleted/missing blocks
class _UnknownBlockBase(Block):
    """
    Placeholder for deleted/missing blocks that inherits from Block
    but uses a name that doesn't end with 'Block' to avoid auto-discovery.
    """

    def __init__(self, block_id: str = "00000000-0000-0000-0000-000000000000"):
        # Initialize with minimal valid Block parameters
        super().__init__(
            id=block_id,
            description=f"Unknown or deleted block (original ID: {block_id})",
            disabled=True,
            input_schema=EmptySchema,
            output_schema=EmptySchema,
            categories=set(),
            contributors=[],
            static_output=False,
            block_type=BlockType.STANDARD,
            webhook_config=None,
        )

    @property
    def name(self):
        return "UnknownBlock"

    async def run(self, input_data, **kwargs):
        """Always yield an error for missing blocks."""
        yield "error", f"Block {self.id} no longer exists"
