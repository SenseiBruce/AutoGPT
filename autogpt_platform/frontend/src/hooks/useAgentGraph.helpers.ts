/** Pure helpers for useAgentGraph. */

import type {
  Graph,
  GraphCreatable,
  LinkCreatable,
  NodeCreatable,
  BlockIOSubSchema,
} from "@/lib/autogpt-server-api/types";
import { deepEquals } from "@/lib/utils";

export const isToolSourceName = (sourceName: string) =>
  sourceName.startsWith("tools_^_");

export const cleanupSourceName = (sourceName: string) =>
  isToolSourceName(sourceName) ? "tools" : sourceName;

export const normalizeToolName = (str: string) =>
  str.replace(/[^a-zA-Z0-9_-]/g, "_").toLowerCase();

export function graphsEquivalent(saved: Graph, current: GraphCreatable): boolean {
  const sortNodes = (nodes: NodeCreatable[]) =>
    nodes.toSorted((a, b) => a.id.localeCompare(b.id));

  const sortLinks = (links: LinkCreatable[]) =>
    links.toSorted(
      (a, b) =>
        8 * a.source_id.localeCompare(b.source_id) +
        4 * a.sink_id.localeCompare(b.sink_id) +
        2 * a.source_name.localeCompare(b.source_name) +
        a.sink_name.localeCompare(b.sink_name),
    );

  const _saved = {
    name: saved.name,
    description: saved.description,
    nodes: sortNodes(saved.nodes).map((v) => ({
      block_id: v.block_id,
      input_default: v.input_default,
      metadata: v.metadata,
    })),
    links: sortLinks(saved.links).map((v) => ({
      sink_name: v.sink_name,
      source_name: v.source_name,
    })),
  };
  const _current = {
    name: current.name,
    description: current.description,
    nodes: sortNodes(current.nodes).map(({ id: _, ...rest }) => rest),
    links: sortLinks(current.links).map(
      ({ source_id: _, sink_id: __, ...rest }) => rest,
    ),
  };
  return deepEquals(_saved, _current);
}

export function rebuildObjectUsingSchema(
  schema: BlockIOSubSchema,
  object: { [key: string]: any },
): Record<string, any> {
  let inputData: Record<string, any> = {};

  if ("properties" in schema) {
    Object.keys(schema.properties).forEach((key) => {
      if (object[key] !== undefined) {
        if (
          "properties" in schema.properties[key] ||
          "additionalProperties" in schema.properties[key]
        ) {
          inputData[key] = rebuildObjectUsingSchema(
            schema.properties[key],
            object[key],
          );
        } else {
          inputData[key] = object[key];
        }
      }
    });
  }

  if ("additionalProperties" in schema) {
    inputData = { ...inputData, ...object };
  }

  return inputData;
}

export function reportLoadError(
  toast: (props: { title: string; variant?: string }) => void,
  title: string,
  error: unknown,
): void {
  console.error(title, error);
  toast({ title, variant: "destructive" });
}
