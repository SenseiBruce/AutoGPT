/** Shared helpers and utility types for BackendAPI. */

import type {
  GraphCreatable,
  GraphExecution,
  GraphExecutionID,
  GraphExecutionMeta,
  GraphID,
  LibraryAgentPreset,
  NodeExecutionResult,
  Schedule,
} from "./types";

/* *** UTILITY TYPES *** */

export type GraphCreateRequestBody = {
  graph: GraphCreatable;
};

export export type WebsocketMessageTypeMap = {
  subscribe_graph_execution: { graph_exec_id: GraphExecutionID };
  subscribe_graph_executions: { graph_id: GraphID };
  graph_execution_event: GraphExecution;
  node_execution_event: NodeExecutionResult;
  heartbeat: "ping" | "pong";
};

export type WebsocketMessage = {
  [M in keyof WebsocketMessageTypeMap]: {
    method: M;
    data: WebsocketMessageTypeMap[M];
  };
}[keyof WebsocketMessageTypeMap];

type _PydanticValidationError = {
  type: string;
  loc: string[];
  msg: string;
  input: any;
};

/* *** HELPER FUNCTIONS *** */

export function parseGraphExecutionTimestamps<
  T extends GraphExecutionMeta | GraphExecution,
>(result: any): T {
  const fixed = _parseObjectTimestamps<T>(result, ["started_at", "ended_at"]);
  if ("node_executions" in fixed && fixed.node_executions) {
    fixed.node_executions = fixed.node_executions.map(
      parseNodeExecutionResultTimestamps,
    );
  }
  return fixed;
}

export function parseNodeExecutionResultTimestamps(result: any): NodeExecutionResult {
  return _parseObjectTimestamps<NodeExecutionResult>(result, [
    "add_time",
    "queue_time",
    "start_time",
    "end_time",
  ]);
}

export function parseScheduleTimestamp(result: any): Schedule {
  return _parseObjectTimestamps<Schedule>(result, ["next_run_time"]);
}

export function parseLibraryAgentPresetTimestamp(result: any): LibraryAgentPreset {
  return _parseObjectTimestamps<LibraryAgentPreset>(result, ["updated_at"]);
}

function _parseObjectTimestamps<T>(obj: any, keys: (keyof T)[]): T {
  const result = { ...obj };
  keys.forEach(
    (key) => (result[key] = result[key] ? new Date(result[key]) : undefined),
  );
  return result;
}
