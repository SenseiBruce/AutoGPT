/** LibraryApi BackendAPI methods. */

import type {
  CredentialsMetaInput,
  GraphExecutionID,
  GraphID,
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
} from "./types";
import { parseLibraryAgentPresetTimestamp } from "./client-helpers";

import type { BackendAPIBase } from "./client-base";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Constructor<T = object> = new (...args: any[]) => T;

export function withLibraryApi<TBase extends Constructor<BackendAPIBase>>(Base: TBase) {
  return class extends Base {
      //////////// V2 LIBRARY API ////////////
      ////////////////////////////////////////

      listLibraryAgents(params?: {
        search_term?: string;
        sort_by?: LibraryAgentSortEnum;
        page?: number;
        page_size?: number;
      }): Promise<LibraryAgentResponse> {
        return this._get("/library/agents", params);
      }

      listFavoriteLibraryAgents(params?: {
        page?: number;
        page_size?: number;
      }): Promise<LibraryAgentResponse> {
        return this._get("/library/agents/favorites", params);
      }

      getLibraryAgent(id: LibraryAgentID): Promise<LibraryAgent> {
        return this._get(`/library/agents/${id}`);
      }

      getLibraryAgentByStoreListingVersionID(
        storeListingVersionId: string,
      ): Promise<LibraryAgent | null> {
        return this._get(`/library/agents/marketplace/${storeListingVersionId}`);
      }

      getLibraryAgentByGraphID(
        graphID: GraphID,
        graphVersion?: number,
      ): Promise<LibraryAgent> {
        return this._get(`/library/agents/by-graph/${graphID}`, {
          version: graphVersion,
        });
      }

      addMarketplaceAgentToLibrary(
        storeListingVersionID: string,
      ): Promise<LibraryAgent> {
        return this._request("POST", "/library/agents", {
          store_listing_version_id: storeListingVersionID,
        });
      }

      updateLibraryAgent(
        libraryAgentId: LibraryAgentID,
        params: {
          auto_update_version?: boolean;
          is_favorite?: boolean;
          is_archived?: boolean;
        },
      ): Promise<LibraryAgent> {
        return this._request("PATCH", `/library/agents/${libraryAgentId}`, params);
      }

      async deleteLibraryAgent(libraryAgentId: LibraryAgentID): Promise<void> {
        await this._request("DELETE", `/library/agents/${libraryAgentId}`);
      }

      forkLibraryAgent(libraryAgentId: LibraryAgentID): Promise<LibraryAgent> {
        return this._request("POST", `/library/agents/${libraryAgentId}/fork`);
      }

      async setupAgentTrigger(params: {
        name: string;
        description?: string;
        graph_id: GraphID;
        graph_version: number;
        trigger_config: Record<string, any>;
        agent_credentials: Record<string, CredentialsMetaInput>;
      }): Promise<LibraryAgentPreset> {
        return parseLibraryAgentPresetTimestamp(
          await this._request("POST", `/library/presets/setup-trigger`, params),
        );
      }

      async listLibraryAgentPresets(params?: {
        graph_id?: GraphID;
        page?: number;
        page_size?: number;
      }): Promise<LibraryAgentPresetResponse> {
        const response: LibraryAgentPresetResponse = await this._get(
          "/library/presets",
          params,
        );
        return {
          ...response,
          presets: response.presets.map(parseLibraryAgentPresetTimestamp),
        };
      }

      async getLibraryAgentPreset(
        presetID: LibraryAgentPresetID,
      ): Promise<LibraryAgentPreset> {
        const preset = await this._get(`/library/presets/${presetID}`);
        return parseLibraryAgentPresetTimestamp(preset);
      }

      async createLibraryAgentPreset(
        params:
          | LibraryAgentPresetCreatable
          | LibraryAgentPresetCreatableFromGraphExecution,
      ): Promise<LibraryAgentPreset> {
        const new_preset = await this._request("POST", "/library/presets", params);
        return parseLibraryAgentPresetTimestamp(new_preset);
      }

      async updateLibraryAgentPreset(
        presetID: LibraryAgentPresetID,
        partial_preset: LibraryAgentPresetUpdatable,
      ): Promise<LibraryAgentPreset> {
        const updated_preset = await this._request(
          "PATCH",
          `/library/presets/${presetID}`,
          partial_preset,
        );
        return parseLibraryAgentPresetTimestamp(updated_preset);
      }

      async deleteLibraryAgentPreset(
        presetID: LibraryAgentPresetID,
      ): Promise<void> {
        await this._request("DELETE", `/library/presets/${presetID}`);
      }

      executeLibraryAgentPreset(
        presetID: LibraryAgentPresetID,
        inputs?: Record<string, any>,
        credential_inputs?: Record<string, CredentialsMetaInput>,
      ): Promise<GraphExecutionMeta> {
        return this._request("POST", `/library/presets/${presetID}/execute`, {
          inputs,
          credential_inputs,
        });
      }

      //////////////////////////////////
  };
}
