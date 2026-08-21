/** BackendAPI core: construction, HTTP, uploads, websockets. */

import { getWebSocketToken } from "@/lib/supabase/actions";
import { getServerSupabase } from "@/lib/supabase/server/getServerSupabase";
import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { Key, storage } from "@/services/storage/local-storage";
import {
  IMPERSONATION_HEADER_NAME,
  IMPERSONATION_STORAGE_KEY,
} from "@/lib/constants";
import * as Sentry from "@sentry/nextjs";
import type {
  AddUserCreditsResponse,
  AnalyticsDetails,
  AnalyticsMetrics,
  APIKey,
  APIKeyCredentials,
  APIKeyPermission,
  Block,
  CreateAPIKeyResponse,
  CreatorDetails,
  CreatorsResponse,
  Credentials,
  CredentialsDeleteNeedConfirmationResponse,
  CredentialsDeleteResponse,
  CredentialsMetaInput,
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
  LibraryAgent,
  LibraryAgentID,
  LibraryAgentPreset,
  LibraryAgentPresetCreatable,
  LibraryAgentPresetCreatableFromGraphExecution,
  LibraryAgentPresetID,
  LibraryAgentPresetResponse,
  LibraryAgentPresetUpdatable,
  LibraryAgentResponse,
  LibraryAgentSortEnum,
  MyAgentsResponse,
  NodeExecutionResult,
  NotificationPreference,
  NotificationPreferenceDTO,
  OttoQuery,
  OttoResponse,
  ProfileDetails,
  RefundRequest,
  ReviewSubmissionRequest,
  Schedule,
  ScheduleCreatable,
  ScheduleID,
  StoreAgentDetails,
  StoreAgentsResponse,
  StoreListingsWithVersionsResponse,
  StoreReview,
  StoreReviewCreate,
  StoreSubmission,
  StoreSubmissionRequest,
  StoreSubmissionsResponse,
  SubmissionStatus,
  TransactionHistory,
  User,
  UserOnboarding,
  UserPasswordCredentials,
  UsersBalanceHistoryResponse,
} from "./types";
import { environment } from "@/services/environment";

const isClient = environment.isClientSide();

export class BackendAPIBase {
  protected baseUrl: string;
  protected wsUrl: string;
  protected webSocket: WebSocket | null = null;
  protected wsConnecting: Promise<void> | null = null;
  protected wsOnConnectHandlers: Set<() => void> = new Set();
  protected wsOnDisconnectHandlers: Set<() => void> = new Set();
  protected wsMessageHandlers: Record<string, Set<(data: any) => void>> = {};
  protected isIntentionallyDisconnected: boolean = false;

  readonly HEARTBEAT_INTERVAL = 100_000; // 100 seconds
  readonly HEARTBEAT_TIMEOUT = 10_000; // 10 seconds
  heartbeatIntervalID: number | null = null;
  heartbeatTimeoutID: number | null = null;

  constructor(
    baseUrl: string = environment.getAGPTServerApiUrl(),
    wsUrl: string = environment.getAGPTWsServerUrl(),
  ) {
    this.baseUrl = baseUrl;
    this.wsUrl = wsUrl;
  }

  protected async getSupabaseClient(): Promise<SupabaseClient | null> {
    return isClient
      ? createBrowserClient(
          environment.getSupabaseUrl(),
          environment.getSupabaseAnonKey(),
          {
            isSingleton: true,
          },
        )
      : await getServerSupabase();
  }

  async isAuthenticated(): Promise<boolean> {
    const supabaseClient = await this.getSupabaseClient();
    if (!supabaseClient) return false;
    const {
      data: { session },
    } = await supabaseClient.auth.getSession();
    return session != null;
  }


  ////////// INTERNAL FUNCTIONS //////////
  ////////////////////////////////////////

  protected _get(path: string, query?: Record<string, any>) {
    return this._request("GET", path, query);
  }

  protected async getAuthToken(): Promise<string> {
    // Only try client-side session (for WebSocket connections)
    // This will return "no-token-found" with httpOnly cookies, which is expected
    const supabaseClient = await this.getSupabaseClient();
    const {
      data: { session },
    } = (await supabaseClient?.auth.getSession()) || {
      data: { session: null },
    };

    return session?.access_token || "no-token-found";
  }

  protected async _uploadFile(path: string, file: File): Promise<string> {
    const formData = new FormData();
    formData.append("file", file);

    if (isClient) {
      return this._makeClientFileUpload(path, formData);
    } else {
      return this._makeServerFileUpload(path, formData);
    }
  }

  protected async _uploadFileWithProgress(
    path: string,
    file: File,
    params?: Record<string, any>,
    onProgress?: (progress: number) => void,
  ): Promise<string> {
    const formData = new FormData();
    formData.append("file", file);

    if (isClient) {
      return this._makeClientFileUploadWithProgress(
        path,
        formData,
        params,
        onProgress,
      );
    } else {
      return this._makeServerFileUploadWithProgress(path, formData, params);
    }
  }

  protected async _makeClientFileUpload(
    path: string,
    formData: FormData,
  ): Promise<string> {
    // Dynamic import is required even for client-only functions because helpers.ts
    // has server-only imports (like getServerSupabase) at the top level. Static imports
    // would bundle server-only code into the client bundle, causing runtime errors.
    const { buildClientUrl, handleFetchError } = await import("./helpers");

    const uploadUrl = buildClientUrl(path);

    const response = await fetch(uploadUrl, {
      method: "POST",
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      throw await handleFetchError(response);
    }

    return await response.json();
  }

  protected async _makeServerFileUpload(
    path: string,
    formData: FormData,
  ): Promise<string> {
    const { makeAuthenticatedFileUpload, buildServerUrl } = await import(
      "./helpers"
    );
    const url = buildServerUrl(path);
    return await makeAuthenticatedFileUpload(url, formData);
  }

  protected async _makeClientFileUploadWithProgress(
    path: string,
    formData: FormData,
    params?: Record<string, any>,
    onProgress?: (progress: number) => void,
  ): Promise<any> {
    const { buildClientUrl, buildUrlWithQuery } = await import("./helpers");

    let url = buildClientUrl(path);
    if (params) {
      url = buildUrlWithQuery(url, params);
    }

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      if (onProgress) {
        xhr.upload.addEventListener("progress", (e) => {
          if (e.lengthComputable) {
            const progress = (e.loaded / e.total) * 100;
            onProgress(progress);
          }
        });
      }

      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve(response);
          } catch (_error) {
            reject(new Error("Invalid JSON response"));
          }
        } else {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      });

      xhr.addEventListener("error", () => {
        reject(new Error("Network error"));
      });

      xhr.open("POST", url);
      xhr.withCredentials = true;
      xhr.send(formData);
    });
  }

  protected async _makeServerFileUploadWithProgress(
    path: string,
    formData: FormData,
    params?: Record<string, any>,
  ): Promise<string> {
    const { makeAuthenticatedFileUpload, buildServerUrl, buildUrlWithQuery } =
      await import("./helpers");

    let url = buildServerUrl(path);
    if (params) {
      url = buildUrlWithQuery(url, params);
    }

    return await makeAuthenticatedFileUpload(url, formData);
  }

  protected async _request(
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    payload?: Record<string, any>,
  ) {
    if (method !== "GET") {
      console.debug(`${method} ${path} payload:`, payload);
    }

    if (isClient) {
      return this._makeClientRequest(method, path, payload);
    } else {
      return this._makeServerRequest(method, path, payload);
    }
  }

  protected async _makeClientRequest(
    method: string,
    path: string,
    payload?: Record<string, any>,
  ) {
    // Dynamic import is required even for client-only functions because helpers.ts
    // has server-only imports (like getServerSupabase) at the top level. Static imports
    // would bundle server-only code into the client bundle, causing runtime errors.
    const { buildClientUrl, buildUrlWithQuery, handleFetchError } =
      await import("./helpers");

    const payloadAsQuery = ["GET", "DELETE"].includes(method);
    let url = buildClientUrl(path);

    if (payloadAsQuery && payload) {
      url = buildUrlWithQuery(url, payload);
    }

    // Prepare headers with admin impersonation support
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (environment.isClientSide()) {
      try {
        const impersonatedUserId = sessionStorage.getItem(
          IMPERSONATION_STORAGE_KEY,
        );
        if (impersonatedUserId) {
          headers[IMPERSONATION_HEADER_NAME] = impersonatedUserId;
        }
      } catch (_error) {
        console.error(
          "Admin impersonation: Failed to access sessionStorage:",
          _error,
        );
      }
    }

    const response = await fetch(url, {
      method,
      headers,
      body: !payloadAsQuery && payload ? JSON.stringify(payload) : undefined,
      credentials: "include",
    });

    if (!response.ok) {
      throw await handleFetchError(response);
    }

    return await response.json();
  }

  protected async _makeServerRequest(
    method: string,
    path: string,
    payload?: Record<string, any>,
  ) {
    const { makeAuthenticatedRequest, buildServerUrl } = await import(
      "./helpers"
    );
    const url = buildServerUrl(path);
    return await makeAuthenticatedRequest(method, url, payload);
  }

  ////////////////////////////////////////

}

declare global {
  interface WebSocket {
    state: "connecting" | "connected" | "closed";
  }
}

