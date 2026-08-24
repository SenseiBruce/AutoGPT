/** StoreApi BackendAPI methods. */

import type {
  AddUserCreditsResponse,
  CreatorDetails,
  CreatorsResponse,
  MyAgentsResponse,
  ProfileDetails,
  ReviewSubmissionRequest,
  StoreAgentDetails,
  StoreAgentsResponse,
  StoreListingsWithVersionsResponse,
  StoreReview,
  StoreReviewCreate,
  StoreSubmission,
  StoreSubmissionRequest,
  StoreSubmissionsResponse,
  SubmissionStatus,
  UsersBalanceHistoryResponse,
} from "./types";

import type { BackendAPIBase } from "./client-base";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Constructor<T = object> = new (...args: any[]) => T;

export function withStoreApi<TBase extends Constructor<BackendAPIBase>>(Base: TBase) {
  return class extends Base {
      ///////////// V2 STORE API /////////////
      ////////////////////////////////////////

      getStoreProfile(): Promise<ProfileDetails | null> {
        try {
          const result = this._get("/store/profile");
          return result;
        } catch (error) {
          console.error("Error fetching store profile:", error);
          return Promise.resolve(null);
        }
      }

      getStoreAgents(params?: {
        featured?: boolean;
        creator?: string;
        sorted_by?: string;
        search_query?: string;
        category?: string;
        page?: number;
        page_size?: number;
      }): Promise<StoreAgentsResponse> {
        return this._get("/store/agents", params);
      }

      getStoreAgent(
        username: string,
        agentName: string,
      ): Promise<StoreAgentDetails> {
        return this._get(
          `/store/agents/${encodeURIComponent(username)}/${encodeURIComponent(
            agentName,
          )}`,
        );
      }

      getGraphMetaByStoreListingVersionID(
        storeListingVersionID: string,
      ): Promise<GraphMeta> {
        return this._get(`/store/graph/${storeListingVersionID}`);
      }

      getStoreAgentByVersionId(
        storeListingVersionID: string,
      ): Promise<StoreAgentDetails> {
        return this._get(`/store/agents/${storeListingVersionID}`);
      }

      getStoreCreators(params?: {
        featured?: boolean;
        search_query?: string;
        sorted_by?: string;
        page?: number;
        page_size?: number;
      }): Promise<CreatorsResponse> {
        return this._get("/store/creators", params);
      }

      getStoreCreator(username: string): Promise<CreatorDetails> {
        return this._get(`/store/creator/${encodeURIComponent(username)}`);
      }

      getStoreSubmissions(params?: {
        page?: number;
        page_size?: number;
      }): Promise<StoreSubmissionsResponse> {
        return this._get("/store/submissions", params);
      }

      createStoreSubmission(
        submission: StoreSubmissionRequest,
      ): Promise<StoreSubmission> {
        return this._request("POST", "/store/submissions", submission);
      }

      generateStoreSubmissionImage(
        agent_id: string,
      ): Promise<{ image_url: string }> {
        return this._request(
          "POST",
          "/store/submissions/generate_image?agent_id=" + agent_id,
        );
      }

      deleteStoreSubmission(submission_id: string): Promise<boolean> {
        return this._request("DELETE", `/store/submissions/${submission_id}`);
      }

      uploadStoreSubmissionMedia(file: File): Promise<string> {
        return this._uploadFile("/store/submissions/media", file);
      }

      uploadFile(
        file: File,
        provider: string = "gcs",
        expiration_hours: number = 24,
        onProgress?: (progress: number) => void,
      ): Promise<{
        file_uri: string;
        file_name: string;
        size: number;
        content_type: string;
        expires_in_hours: number;
      }> {
        return this._uploadFileWithProgress(
          "/files/upload",
          file,
          {
            provider,
            expiration_hours,
          },
          onProgress,
        ).then((response) => {
          if (typeof response === "string") {
            return JSON.parse(response);
          }
          return response;
        });
      }

      updateStoreProfile(profile: ProfileDetails): Promise<ProfileDetails> {
        return this._request("POST", "/store/profile", profile);
      }

      reviewAgent(
        username: string,
        agentName: string,
        review: StoreReviewCreate,
      ): Promise<StoreReview> {
        return this._request(
          "POST",
          `/store/agents/${encodeURIComponent(username)}/${encodeURIComponent(
            agentName,
          )}/review`,
          review,
        );
      }

      getMyAgents(params?: {
        page?: number;
        page_size?: number;
      }): Promise<MyAgentsResponse> {
        return this._get("/store/myagents", params);
      }

      downloadStoreAgent(
        storeListingVersionId: string,
        version?: number,
      ): Promise<BlobPart> {
        const url = version
          ? `/store/download/agents/${storeListingVersionId}?version=${version}`
          : `/store/download/agents/${storeListingVersionId}`;

        return this._get(url);
      }

      /////////////////////////////////////////
      /////////// Admin API ///////////////////
      /////////////////////////////////////////

      getAdminListingsWithVersions(params?: {
        status?: SubmissionStatus;
        search?: string;
        page?: number;
        page_size?: number;
      }): Promise<StoreListingsWithVersionsResponse> {
        return this._get("/store/admin/listings", params);
      }

      reviewSubmissionAdmin(
        storeListingVersionId: string,
        review: ReviewSubmissionRequest,
      ): Promise<StoreSubmission> {
        return this._request(
          "POST",
          `/store/admin/submissions/${storeListingVersionId}/review`,
          review,
        );
      }

      addUserCredits(
        user_id: string,
        amount: number,
        comments: string,
      ): Promise<AddUserCreditsResponse> {
        return this._request("POST", "/credits/admin/add_credits", {
          user_id,
          amount,
          comments,
        });
      }

      getUsersHistory(params?: {
        search?: string;
        page?: number;
        page_size?: number;
        transaction_filter?: string;
      }): Promise<UsersBalanceHistoryResponse> {
        return this._get("/credits/admin/users_history", params);
      }

      downloadStoreAgentAdmin(storeListingVersionId: string): Promise<BlobPart> {
        const url = `/store/admin/submissions/download/${storeListingVersionId}`;

        return this._get(url);
      }

      ////////////////////////////////////////
  };
}
