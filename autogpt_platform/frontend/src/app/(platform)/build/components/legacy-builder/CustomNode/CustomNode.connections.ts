/** Connection helpers for CustomNode. */

import type { CustomNodeData } from "./CustomNode.types";

export function isInputHandleConnected(
  data: CustomNodeData,
  id: string,
  key: string,
): boolean {
  return (
    !!data.connections &&
    data.connections.some((conn: any) => {
      if (typeof conn === "string") {
        const [_source, target] = conn.split(" -> ");
        return target.includes(key) && target.includes(data.title);
      }
      return conn.target === id && conn.targetHandle === key;
    })
  );
}

export function isOutputHandleConnected(
  data: CustomNodeData,
  id: string,
  key: string,
): boolean {
  return (
    !!data.connections &&
    data.connections.some((conn: any) => {
      if (typeof conn === "string") {
        const [source, _target] = conn.split(" -> ");
        return source.includes(key) && source.includes(data.title);
      }
      return conn.source === id && conn.sourceHandle === key;
    })
  );
}
