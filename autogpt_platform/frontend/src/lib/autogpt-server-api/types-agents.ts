/** Graph, execution, and library agent types. */

import type { Brand } from "./types-brand";
import type {
  BlockIOSubSchema,
  BlockIOSubSchemaMeta,
  BlockCost,
  Category,
} from "./types-block";
import type { CredentialsMetaInput } from "./types-credentials";
import type { Pagination, Webhook } from "./types-common";

export type NodeCreatable = {
  id: string;
  block_id: string;
  input_default: Record<string, any>;
  metadata: {
    position: { x: number; y: number };
    [key: string]: any;
  };
};

/* Mirror of backend/data/graph.py:Node */
export type Node = NodeCreatable & {
  input_links: Link[];
  output_links: Link[];
  webhook?: Webhook;
};

/* Mirror of backend/data/graph.py:Link */
export type Link = {
  id: string;
  source_id: string;
  sink_id: string;
  source_name: string;
  sink_name: string;
  is_static: boolean;
};

export type LinkCreatable = Omit<Link, "id" | "is_static"> & {
  id?: string;
};

/* Mirror of backend/data/execution.py:GraphExecutionMeta */
export type GraphExecutionMeta = {
  id: GraphExecutionID;
  user_id: UserID;
  graph_id: GraphID;
  graph_version: number;
  inputs: Record<string, any> | null;
  credential_inputs: Record<string, CredentialsMetaInput> | null;
  nodes_input_masks: Record<string, Record<string, any>> | null;
  preset_id: LibraryAgentPresetID | null;
  status:
    | "QUEUED"
    | "RUNNING"
    | "COMPLETED"
    | "TERMINATED"
    | "FAILED"
    | "INCOMPLETE";
  started_at: Date;
  ended_at: Date;
  stats: {
    error: string | null;
    cost: number;
    duration: number;
    duration_cpu_only: number;
    node_exec_time: number;
    node_exec_time_cpu_only: number;
    node_exec_count: number;
    activity_status: string | null;
    [key: string]: any;
  } | null;
};

export type GraphExecutionID = Brand<string, "GraphExecutionID">;

/* Mirror of backend/data/execution.py:GraphExecution */
export type GraphExecution = Omit<GraphExecutionMeta, "inputs"> & {
  inputs: Record<string, any>;
  outputs: Record<string, Array<any>>;
  node_executions?: NodeExecutionResult[];
};

export type GraphExecutionsResponse = {
  executions: GraphExecutionMeta[];
  pagination: Pagination;
};

/* Mirror of backend/data/graph.py:GraphMeta */
export type GraphMeta = {
  id: GraphID;
  user_id: UserID;
  version: number;
  is_active: boolean;
  name: string;
  description: string;
  instructions?: string | null;
  recommended_schedule_cron: string | null;
  forked_from_id?: GraphID | null;
  forked_from_version?: number | null;
  input_schema: GraphIOSchema;
  output_schema: GraphIOSchema;
  credentials_input_schema: CredentialsInputSchema;
} & (
  | {
      has_external_trigger: true;
      trigger_setup_info: GraphTriggerInfo;
    }
  | {
      has_external_trigger: false;
      trigger_setup_info: null;
    }
);

export type GraphID = Brand<string, "GraphID">;

/* Derived from backend/data/graph.py:Graph._generate_schema() */
export type GraphIOSchema = {
  type: "object";
  properties: Record<string, GraphIOSubSchema>;
  required: (keyof BlockIORootSchema["properties"])[];
};
export type GraphIOSubSchema = Omit<
  BlockIOSubSchemaMeta,
  "placeholder" | "depends_on" | "hidden"
> & {
  type: never; // bodge to avoid type checking hell; doesn't exist at runtime
  default?: string;
  secret: boolean;
  metadata?: any;
};

export type CredentialsInputSchema = {
  type: "object";
  properties: Record<string, BlockIOCredentialsSubSchema>;
  required?: (keyof CredentialsInputSchema["properties"])[];
};

/* Mirror of backend/data/graph.py:GraphTriggerInfo */
export type GraphTriggerInfo = {
  provider: CredentialsProviderName;
  config_schema: BlockIORootSchema;
  credentials_input_name: string | null;
};

/* Mirror of backend/data/graph.py:Graph */
export type Graph = GraphMeta & {
  created_at: Date;
  nodes: Node[];
  links: Link[];
  sub_graphs: Omit<Graph, "sub_graphs">[]; // Flattened sub-graphs
};

export type GraphUpdateable = Omit<
  Graph,
  | "user_id"
  | "version"
  | "created_at"
  | "is_active"
  | "nodes"
  | "links"
  | "sub_graphs"
  | "input_schema"
  | "output_schema"
  | "credentials_input_schema"
  | "has_external_trigger"
  | "trigger_setup_info"
> & {
  version?: number;
  is_active?: boolean;
  nodes: NodeCreatable[];
  links: LinkCreatable[];
  input_schema?: GraphIOSchema;
  output_schema?: GraphIOSchema;
};

export type GraphCreatable = _GraphCreatableInner & {
  sub_graphs?: _GraphCreatableInner[]; // Flattened sub-graphs
};
type _GraphCreatableInner = Omit<GraphUpdateable, "id"> & { id?: string };

/* Mirror of backend/data/execution.py:NodeExecutionResult */
export type NodeExecutionResult = {
  graph_id: GraphID;
  graph_version: number;
  graph_exec_id: GraphExecutionID;
  node_exec_id: string;
  node_id: string;
  block_id: string;
  status:
    | "INCOMPLETE"
    | "QUEUED"
    | "RUNNING"
    | "COMPLETED"
    | "TERMINATED"
    | "FAILED";
  input_data: Record<string, any>;
  output_data: Record<string, Array<any>>;
  add_time: Date;
  queue_time?: Date;
  start_time?: Date;
  end_time?: Date;
};

/* Structured validation error types for graph execution */
export type GraphValidationErrorResponse = {
  detail: {
    type: "validation_error";
    message: string;
    node_errors: Record<string, Record<string, string>>;
  };
};

/* *** LIBRARY *** */

/* Mirror of backend/server/v2/library/model.py:LibraryAgent */

export type LibraryAgent = {
  id: LibraryAgentID;
  graph_id: GraphID;
  graph_version: number;
  image_url: string | null;
  creator_name: string;
  creator_image_url: string;
  status: AgentStatus;
  updated_at: Date;
  name: string;
  description: string;
  instructions?: string | null;
  input_schema: GraphIOSchema;
  output_schema: GraphIOSchema;
  credentials_input_schema: CredentialsInputSchema;
  new_output: boolean;
  can_access_graph: boolean;
  is_favorite: boolean;
  is_latest_version: boolean;
  recommended_schedule_cron: string | null;
} & (
  | {
      has_external_trigger: true;
      trigger_setup_info: GraphTriggerInfo;
    }
  | {
      has_external_trigger: false;
      trigger_setup_info: null;
    }
);

export type LibraryAgentID = Brand<string, "LibraryAgentID">;

export enum AgentStatus {
  COMPLETED = "COMPLETED",
  HEALTHY = "HEALTHY",
  WAITING = "WAITING",
  ERROR = "ERROR",
}

export type LibraryAgentResponse = {
  agents: LibraryAgent[];
  pagination: Pagination;
};

export type LibraryAgentPreset = {
  id: LibraryAgentPresetID;
  created_at: Date;
  updated_at: Date;
  graph_id: GraphID;
  graph_version: number;
  inputs: Record<string, any>;
  credentials: Record<string, CredentialsMetaInput>;
  name: string;
  description: string;
  is_active: boolean;
} & (
  | {
      webhook_id: string;
      webhook: Webhook;
    }
  | {
      webhook_id?: undefined;
      webhook?: undefined;
    }
);

export type LibraryAgentPresetID = Brand<string, "LibraryAgentPresetID">;

export type LibraryAgentPresetResponse = {
  presets: LibraryAgentPreset[];
  pagination: Pagination;
};

export type LibraryAgentPresetCreatable = Omit<
  LibraryAgentPreset,
  "id" | "created_at" | "updated_at" | "is_active"
> & {
  is_active?: boolean;
};

export type LibraryAgentPresetCreatableFromGraphExecution = Omit<
  LibraryAgentPresetCreatable,
  "graph_id" | "graph_version" | "inputs" | "credentials"
> & {
  graph_execution_id: GraphExecutionID;
};

export type LibraryAgentPresetUpdatable = Partial<
  Omit<LibraryAgentPresetCreatable, "graph_id" | "graph_version">
>;

export enum LibraryAgentSortEnum {
  CREATED_AT = "createdAt",
  UPDATED_AT = "updatedAt",
}
