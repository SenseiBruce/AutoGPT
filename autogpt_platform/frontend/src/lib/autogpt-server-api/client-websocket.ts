/** WebSocket methods for BackendAPI. */

import { getWebSocketToken } from "@/lib/supabase/actions";
import { Key, storage } from "@/services/storage/local-storage";
import * as Sentry from "@sentry/nextjs";
import type { GraphExecutionID, GraphID } from "./types";
import type { BackendAPIBase } from "./client-base";
import {
  parseGraphExecutionTimestamps,
  parseNodeExecutionResultTimestamps,
  type WebsocketMessage,
  type WebsocketMessageTypeMap,
} from "./client-helpers";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Constructor<T = {}> = new (...args: any[]) => T;

export function withWebSocketApi<TBase extends Constructor<BackendAPIBase>>(Base: TBase) {
  return class extends Base {
      subscribeToGraphExecution(graphExecID: GraphExecutionID): Promise<void> {
        return this.sendWebSocketMessage("subscribe_graph_execution", {
          graph_exec_id: graphExecID,
        });
      }

      subscribeToGraphExecutions(graphID: GraphID): Promise<void> {
        return this.sendWebSocketMessage("subscribe_graph_executions", {
          graph_id: graphID,
        });
      }

      async sendWebSocketMessage<M extends keyof WebsocketMessageTypeMap>(
        method: M,
        data: WebsocketMessageTypeMap[M],
        callCount = 0,
        callCountLimit = 4,
      ): Promise<void> {
        if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
          this.webSocket.send(JSON.stringify({ method, data }));
          return;
        }
        if (callCount >= callCountLimit) {
          throw new Error(
            `WebSocket connection not open after ${callCountLimit} attempts`,
          );
        }
        await this.connectWebSocket();
        if (callCount === 0) {
          return this.sendWebSocketMessage(method, data, callCount + 1);
        }
        const delayMs = 2 ** (callCount - 1) * 1000;
        await new Promise((res) => setTimeout(res, delayMs));
        return this.sendWebSocketMessage(method, data, callCount + 1);
      }

      onWebSocketMessage<M extends keyof WebsocketMessageTypeMap>(
        method: M,
        handler: (data: WebsocketMessageTypeMap[M]) => void,
      ): () => void {
        this.wsMessageHandlers[method] ??= new Set();
        this.wsMessageHandlers[method].add(handler);

        // Return detacher
        return () => this.wsMessageHandlers[method].delete(handler);
      }

      /**
       * All handlers are invoked when the WebSocket (re)connects. If it's already connected
       * when this function is called, the passed handler is invoked immediately.
       *
       * Use this hook to subscribe to topics and refresh state,
       * to ensure re-subscription and re-sync on re-connect.
       *
       * @returns a detacher for the passed handler.
       */
      onWebSocketConnect(handler: () => void): () => void {
        this.wsOnConnectHandlers.add(handler);

        this.connectWebSocket();
        if (this.webSocket?.readyState == WebSocket.OPEN) handler();

        // Return detacher
        return () => this.wsOnConnectHandlers.delete(handler);
      }

      /**
       * All handlers are invoked when the WebSocket disconnects.
       *
       * @returns a detacher for the passed handler.
       */
      onWebSocketDisconnect(handler: () => void): () => void {
        this.wsOnDisconnectHandlers.add(handler);

        // Return detacher
        return () => this.wsOnDisconnectHandlers.delete(handler);
      }

      async connectWebSocket(): Promise<void> {
        // Do not attempt to connect if a disconnect intent is present (e.g., during logout)
        if (this._hasDisconnectIntent()) {
          return;
        }

        this.isIntentionallyDisconnected = false;
        return (this.wsConnecting ??= new Promise(async (resolve, reject) => {
          try {
            let token = "";
            try {
              const { token: serverToken, error } = await getWebSocketToken();
              if (serverToken && !error) {
                token = serverToken;
              } else if (error) {
                console.warn("Failed to get WebSocket token from server:", error);
              }
            } catch (error) {
              console.warn("Failed to get token for WebSocket connection:", error);
              // Intentionally fall through; we'll bail out below if no token is available
            }

            // If we don't have a token, skip attempting a connection.
            if (!token) {
              console.info(
                "[BackendAPI] Skipping WebSocket connect: no auth token available",
              );
              // Resolve first, then clear wsConnecting to avoid races for awaiters
              resolve();
              this.wsConnecting = null;
              this.webSocket = null;
              return;
            }

            const wsUrlWithToken = `${this.wsUrl}?token=${token}`;
            this.webSocket = new WebSocket(wsUrlWithToken);
            this.webSocket.state = "connecting";

            this.webSocket.onopen = () => {
              this.webSocket!.state = "connected";
              console.info("[BackendAPI] WebSocket connected to", this.wsUrl);
              this._startWSHeartbeat(); // Start heartbeat when connection opens
              this._clearDisconnectIntent(); // Clear disconnect intent when connected
              this.wsOnConnectHandlers.forEach((handler) => handler());
              resolve();
            };

            this.webSocket.onclose = (event) => {
              if (this.webSocket?.state == "connecting") {
                console.error(
                  `[BackendAPI] WebSocket failed to connect: ${event.reason}`,
                  event,
                );
              } else if (this.webSocket?.state == "connected") {
                console.warn(
                  `[BackendAPI] WebSocket connection closed: ${event.reason}`,
                  event,
                );
              }
              this.webSocket!.state = "closed";

              this._stopWSHeartbeat(); // Stop heartbeat when connection closes
              this.wsConnecting = null;

              const wasIntentional =
                this.isIntentionallyDisconnected || this._hasDisconnectIntent();

              if (!wasIntentional) {
                this.wsOnDisconnectHandlers.forEach((handler) => handler());
                setTimeout(() => this.connectWebSocket().then(resolve), 1000);
              } else {
                // Ensure pending connect calls settle on intentional close
                resolve();
              }
            };

            this.webSocket.onerror = (error) => {
              if (this.webSocket?.state == "connected") {
                console.error("[BackendAPI] WebSocket error:", error);
              }
            };
            this.webSocket.onmessage = (event) => this._handleWSMessage(event);
          } catch (error) {
            console.error("[BackendAPI] Error connecting to WebSocket:", error);
            reject(error);
          }
        }));
      }

      disconnectWebSocket() {
        this.isIntentionallyDisconnected = true;
        this._stopWSHeartbeat(); // Stop heartbeat when disconnecting
        if (
          this.webSocket &&
          (this.webSocket.readyState === WebSocket.OPEN ||
            this.webSocket.readyState === WebSocket.CONNECTING)
        ) {
          this.webSocket.close();
        }
        this.wsConnecting = null;
      }

      protected _hasDisconnectIntent(): boolean {
        if (!isClient) return false;

        try {
          return storage.get(Key.WEBSOCKET_DISCONNECT_INTENT) === "true";
        } catch {
          return false;
        }
      }

      protected _clearDisconnectIntent(): void {
        if (!isClient) return;

        try {
          storage.clean(Key.WEBSOCKET_DISCONNECT_INTENT);
        } catch {
          Sentry.captureException(
            new Error("Failed to clear WebSocket disconnect intent"),
          );
        }
      }

      protected _handleWSMessage(event: MessageEvent): void {
        const message: WebsocketMessage = JSON.parse(event.data);

        // Handle heartbeat response
        if (message.method === "heartbeat" && message.data === "pong") {
          this._handleWSHeartbeatResponse();
          return;
        }

        if (message.method === "node_execution_event") {
          message.data = parseNodeExecutionResultTimestamps(message.data);
        } else if (message.method == "graph_execution_event") {
          message.data = parseGraphExecutionTimestamps(message.data);
        }
        this.wsMessageHandlers[message.method]?.forEach((handler) =>
          handler(message.data),
        );
      }

      protected _startWSHeartbeat() {
        this._stopWSHeartbeat();
        this.heartbeatIntervalID = window.setInterval(() => {
          if (this.webSocket?.readyState === WebSocket.OPEN) {
            this.webSocket.send(
              JSON.stringify({
                method: "heartbeat",
                data: "ping",
                success: true,
              }),
            );

            this.heartbeatTimeoutID = window.setTimeout(() => {
              console.warn("Heartbeat timeout - reconnecting");
              this.webSocket?.close();
              this.connectWebSocket();
            }, this.HEARTBEAT_TIMEOUT);
          }
        }, this.HEARTBEAT_INTERVAL);
      }

      protected _stopWSHeartbeat() {
        if (this.heartbeatIntervalID) {
          clearInterval(this.heartbeatIntervalID);
          this.heartbeatIntervalID = null;
        }
        if (this.heartbeatTimeoutID) {
          clearTimeout(this.heartbeatTimeoutID);
          this.heartbeatTimeoutID = null;
        }
      }

      protected _handleWSHeartbeatResponse() {
        if (this.heartbeatTimeoutID) {
          clearTimeout(this.heartbeatTimeoutID);
          this.heartbeatTimeoutID = null;
        }
      }
    };
}
