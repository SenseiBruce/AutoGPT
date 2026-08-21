/** GraphsApi BackendAPI methods. */

import type {
  AnalyticsDetails,
  AnalyticsMetrics,
  APIKey,
  APIKeyCredentials,
  APIKeyPermission,
  Block,
  CreateAPIKeyResponse,
  Credentials,
  CredentialsDeleteNeedConfirmationResponse,
  CredentialsDeleteResponse,
  CredentialsMetaResponse,
  Graph,
  GraphCreatable,
  GraphExecution,
  GraphExecutionID,
  GraphExecutionMeta,
  GraphExecutionsResponse,
  GraphID,
  GraphMeta,
  GraphUpdateable,
  HostScopedCredentials,
  UserPasswordCredentials,
} from "./types";
import {
  parseGraphExecutionTimestamps,
  type GraphCreateRequestBody,
} from "./client-helpers";

import type { BackendAPIBase } from "./client-base";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Constructor<T = {}> = new (...args: any[]) => T;

export function withGraphsApi<TBase extends Constructor<BackendAPIBase>>(Base: TBase) {
  return class extends Base {
      //////////////// GRAPHS ////////////////
      ////////////////////////////////////////

      getBlocks(): Promise<Block[]> {
        return this._get("/blocks");
      }

      listGraphs(): Promise<GraphMeta[]> {
        return this._get(`/graphs`);
      }

      async getGraph(
        id: GraphID,
        version?: number,
        for_export?: boolean,
      ): Promise<Graph> {
        const query: Record<string, any> = {};
        if (version !== undefined) {
          query["version"] = version;
        }
        if (for_export !== undefined) {
          query["for_export"] = for_export;
        }
        const graph = await this._get(`/graphs/${id}`, query);
        if (for_export) delete graph.user_id;
        return graph;
      }

      getGraphAllVersions(id: GraphID): Promise<Graph[]> {
        return this._get(`/graphs/${id}/versions`);
      }

      createGraph(graph: GraphCreatable): Promise<Graph> {
        const requestBody = { graph } as GraphCreateRequestBody;

        return this._request("POST", "/graphs", requestBody);
      }

      updateGraph(id: GraphID, graph: GraphUpdateable): Promise<Graph> {
        return this._request("PUT", `/graphs/${id}`, graph);
      }

      deleteGraph(id: GraphID): Promise<void> {
        return this._request("DELETE", `/graphs/${id}`);
      }

      setGraphActiveVersion(id: GraphID, version: number): Promise<Graph> {
        return this._request("PUT", `/graphs/${id}/versions/active`, {
          active_graph_version: version,
        });
      }

      executeGraph(
        id: GraphID,
        version: number,
        inputs: { [key: string]: any } = {},
        credentials_inputs: { [key: string]: CredentialsMetaInput } = {},
      ): Promise<GraphExecutionMeta> {
        return this._request("POST", `/graphs/${id}/execute/${version}`, {
          inputs,
          credentials_inputs,
        });
      }

      getExecutions(): Promise<GraphExecutionMeta[]> {
        return this._get(`/executions`).then((results) =>
          results.map(parseGraphExecutionTimestamps),
        );
      }

      getGraphExecutions(graphID: GraphID): Promise<GraphExecutionsResponse> {
        return this._get(`/graphs/${graphID}/executions`).then((results) =>
          results.map(parseGraphExecutionTimestamps),
        );
      }

      async getGraphExecutionInfo(
        graphID: GraphID,
        runID: GraphExecutionID,
      ): Promise<GraphExecution> {
        const result = await this._get(`/graphs/${graphID}/executions/${runID}`);
        return parseGraphExecutionTimestamps<GraphExecution>(result);
      }

      async stopGraphExecution(
        graphID: GraphID,
        runID: GraphExecutionID,
      ): Promise<GraphExecution> {
        const result = await this._request(
          "POST",
          `/graphs/${graphID}/executions/${runID}/stop`,
        );
        return parseGraphExecutionTimestamps<GraphExecution>(result);
      }

      async deleteGraphExecution(runID: GraphExecutionID): Promise<void> {
        await this._request("DELETE", `/executions/${runID}`);
      }

      oAuthLogin(
        provider: string,
        scopes?: string[],
      ): Promise<{ login_url: string; state_token: string }> {
        const query = scopes ? { scopes: scopes.join(",") } : undefined;
        return this._get(`/integrations/${provider}/login`, query);
      }

      oAuthCallback(
        provider: string,
        code: string,
        state_token: string,
      ): Promise<CredentialsMetaResponse> {
        return this._request("POST", `/integrations/${provider}/callback`, {
          code,
          state_token,
        });
      }

      createAPIKeyCredentials(
        credentials: Omit<APIKeyCredentials, "id" | "type">,
      ): Promise<APIKeyCredentials> {
        return this._request(
          "POST",
          `/integrations/${credentials.provider}/credentials`,
          { ...credentials, type: "api_key" },
        );
      }

      createUserPasswordCredentials(
        credentials: Omit<UserPasswordCredentials, "id" | "type">,
      ): Promise<UserPasswordCredentials> {
        return this._request(
          "POST",
          `/integrations/${credentials.provider}/credentials`,
          { ...credentials, type: "user_password" },
        );
      }

      createHostScopedCredentials(
        credentials: Omit<HostScopedCredentials, "id" | "type">,
      ): Promise<HostScopedCredentials> {
        return this._request(
          "POST",
          `/integrations/${credentials.provider}/credentials`,
          { ...credentials, type: "host_scoped" },
        );
      }

      listProviders(): Promise<string[]> {
        return this._get("/integrations/providers");
      }

      listCredentials(provider?: string): Promise<CredentialsMetaResponse[]> {
        return this._get(
          provider
            ? `/integrations/${provider}/credentials`
            : "/integrations/credentials",
        );
      }

      getCredentials(provider: string, id: string): Promise<Credentials> {
        return this._get(`/integrations/${provider}/credentials/${id}`);
      }

      deleteCredentials(
        provider: string,
        id: string,
        force: boolean = true,
      ): Promise<
        CredentialsDeleteResponse | CredentialsDeleteNeedConfirmationResponse
      > {
        return this._request(
          "DELETE",
          `/integrations/${provider}/credentials/${id}`,
          force ? { force: true } : undefined,
        );
      }

      // API Key related requests
      async createAPIKey(
        name: string,
        permissions: APIKeyPermission[],
        description?: string,
      ): Promise<CreateAPIKeyResponse> {
        return this._request("POST", "/api-keys", {
          name,
          permissions,
          description,
        });
      }

      async listAPIKeys(): Promise<APIKey[]> {
        return this._get("/api-keys");
      }

      async revokeAPIKey(keyId: string): Promise<APIKey> {
        return this._request("DELETE", `/api-keys/${keyId}`);
      }

      async updateAPIKeyPermissions(
        keyId: string,
        permissions: APIKeyPermission[],
      ): Promise<APIKey> {
        return this._request("PUT", `/api-keys/${keyId}/permissions`, {
          permissions,
        });
      }

      /**
       * @returns `true` if a ping event was received, `false` if provider doesn't support pinging but the webhook exists.
       * @throws  `Error` if the webhook does not exist.
       * @throws  `Error` if the attempt to ping timed out.
       */
      async pingWebhook(webhook_id: string): Promise<boolean> {
        return this._request("POST", `/integrations/webhooks/${webhook_id}/ping`);
      }

      logMetric(metric: AnalyticsMetrics) {
        return this._request("POST", "/analytics/log_raw_metric", metric);
      }

      logAnalytic(analytic: AnalyticsDetails) {
        return this._request("POST", "/analytics/log_raw_analytics", analytic);
      }

      ////////////////////////////////////////
  };
}
