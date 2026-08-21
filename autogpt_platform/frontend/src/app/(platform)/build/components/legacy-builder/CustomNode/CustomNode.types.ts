/** Types for legacy CustomNode. */

import type { Node as XYNode } from "@xyflow/react";
import type {
  BlockCost,
  BlockIORootSchema,
  BlockUIType,
  Category,
  NodeExecutionResult,
} from "@/lib/autogpt-server-api/types";

export type ConnectionData = Array<{
  edge_id: string;
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
}>;

export type CustomNodeData = {
  blockType: string;
  blockCosts: BlockCost[];
  title: string;
  description: string;
  categories: Category[];
  inputSchema: BlockIORootSchema;
  outputSchema: BlockIORootSchema;
  hardcodedValues: { [key: string]: any };
  connections: ConnectionData;
  isOutputOpen: boolean;
  status?: NodeExecutionResult["status"];
  /** executionResults contains outputs across multiple executions
   * with the last element being the most recent output */
  executionResults?: {
    execId: string;
    data: NodeExecutionResult["output_data"];
    status: NodeExecutionResult["status"];
  }[];
  block_id: string;
  backend_id?: string;
  errors?: { [key: string]: string };
  isOutputStatic?: boolean;
  uiType: BlockUIType;
  metadata?: { [key: string]: any };
};

export type CustomNode = XYNode<CustomNodeData, "custom">;

