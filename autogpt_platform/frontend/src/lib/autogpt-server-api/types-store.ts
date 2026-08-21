/** Store, user, schedule, analytics, and admin types. */

import type { Brand } from "./types-brand";
import type { GraphExecutionID, GraphID, GraphMeta } from "./types-agents";
import type { Pagination } from "./types-common";



export type NotificationType =
  | "AGENT_RUN"
  | "ZERO_BALANCE"
  | "LOW_BALANCE"
  | "BLOCK_EXECUTION_FAILED"
  | "CONTINUOUS_AGENT_ERROR"
  | "DAILY_SUMMARY"
  | "WEEKLY_SUMMARY"
  | "MONTHLY_SUMMARY"
  | "AGENT_APPROVED"
  | "AGENT_REJECTED";

// Mirror of backend/backend/data/notifications.py:NotificationPreference
export type NotificationPreferenceDTO = {
  email: string;
  preferences: { [key in NotificationType]: boolean };
  daily_limit: number;
};

export type NotificationPreference = NotificationPreferenceDTO & {
  user_id: UserID;
  emails_sent_today: number;
  last_reset_date: Date;
};

/* Mirror of backend/data/integrations.py:Webhook */

export type User = {
  id: UserID;
  email: string;
};

export type UserID = Brand<string, "UserID">;

export enum BlockUIType {
  STANDARD = "Standard",
  INPUT = "Input",
  OUTPUT = "Output",
  NOTE = "Note",
  WEBHOOK = "Webhook",
  WEBHOOK_MANUAL = "Webhook (manual)",
  AGENT = "Agent",
  AI = "AI",
  AYRSHARE = "Ayrshare",
}

export enum SpecialBlockID {
  AGENT = "e189baac-8c20-45a1-94a7-55177ea42565",
  SMART_DECISION = "3b191d9f-356f-482d-8238-ba04b6d18381",
  OUTPUT = "363ae599-353e-4804-937e-b2ee3cef3da4",
}

export type AnalyticsMetrics = {
  metric_name: string;
  metric_value: number;
  data_string: string;
};

export type AnalyticsDetails = {
  type: string;
  data: Record<string, any>;
  index: string;
};


export type StoreAgent = {
  slug: string;
  agent_name: string;
  agent_image: string;
  creator: string;
  creator_avatar: string;
  sub_heading: string;
  description: string;
  runs: number;
  rating: number;
  updated_at: string;
};

export type StoreAgentsResponse = {
  agents: StoreAgent[];
  pagination: Pagination;
};

export type StoreAgentDetails = {
  store_listing_version_id: string;
  slug: string;
  updated_at: string;
  agent_name: string;
  agent_video: string;
  agent_image: string[];
  creator: string;
  creator_avatar: string;
  sub_heading: string;
  description: string;
  categories: string[];
  runs: number;
  rating: number;
  versions: string[];

  // Approval and status fields
  active_version_id?: string;
  has_approved_version?: boolean;
  is_available?: boolean;
};

export type Creator = {
  name: string;
  username: string;
  description: string;
  avatar_url: string;
  num_agents: number;
  agent_rating: number;
  agent_runs: number;
};

export type CreatorsResponse = {
  creators: Creator[];
  pagination: Pagination;
};

export type CreatorDetails = {
  name: string;
  username: string;
  description: string;
  links: string[];
  avatar_url: string;
  agent_rating: number;
  agent_runs: number;
  top_categories: string[];
};

export type StoreSubmission = {
  agent_id: string;
  agent_version: number;
  name: string;
  sub_heading: string;
  description: string;
  instructions?: string;
  image_urls: string[];
  date_submitted: string;
  status: SubmissionStatus;
  runs: number;
  rating: number;
  slug: string;
  store_listing_version_id?: string;
  version?: number; // Actual version number from the database

  // Review information
  reviewer_id?: string;
  review_comments?: string;
  internal_comments?: string; // Admin-only comments
  reviewed_at?: string;
  changes_summary?: string;
};

export type StoreSubmissionsResponse = {
  submissions: StoreSubmission[];
  pagination: Pagination;
};

export type StoreSubmissionRequest = {
  agent_id: string;
  agent_version: number;
  slug: string;
  name: string;
  sub_heading: string;
  video_url?: string;
  image_urls: string[];
  description: string;
  instructions?: string | null;
  categories: string[];
  changes_summary?: string;
  recommended_schedule_cron?: string | null;
};

export type ProfileDetails = {
  name: string;
  username: string;
  description: string;
  links: string[];
  avatar_url: string;
};

/* Mirror of backend/executor/scheduler.py:GraphExecutionJobInfo */
export type Schedule = {
  id: ScheduleID;
  name: string;
  cron: string;
  user_id: UserID;
  graph_id: GraphID;
  graph_version: number;
  input_data: Record<string, any>;
  input_credentials: Record<string, CredentialsMetaInput>;
  next_run_time: Date;
  timezone: string;
};

export type ScheduleID = Brand<string, "ScheduleID">;

/* Mirror of backend/server/routers/v1.py:ScheduleCreationRequest */
export type ScheduleCreatable = {
  graph_id: GraphID;
  graph_version: number;
  name: string;
  cron: string;
  inputs: Record<string, any>;
  credentials?: Record<string, CredentialsMetaInput>;
};

export type MyAgent = {
  agent_id: GraphID;
  agent_version: number;
  agent_name: string;
  agent_image: string | null;
  last_edited: string;
  description: string;
  recommended_schedule_cron: string | null;
};

export type MyAgentsResponse = {
  agents: MyAgent[];
  pagination: Pagination;
};

export type StoreReview = {
  score: number;
  comments?: string;
};

export type StoreReviewCreate = {
  store_listing_version_id: string;
  score: number;
  comments?: string;
};

// API Key Types

export enum APIKeyPermission {
  EXECUTE_GRAPH = "EXECUTE_GRAPH",
  READ_GRAPH = "READ_GRAPH",
  EXECUTE_BLOCK = "EXECUTE_BLOCK",
  READ_BLOCK = "READ_BLOCK",
}

export enum APIKeyStatus {
  ACTIVE = "ACTIVE",
  REVOKED = "REVOKED",
  SUSPENDED = "SUSPENDED",
}

export interface APIKey {
  id: string;
  name: string;
  prefix: string;
  postfix: string;
  status: APIKeyStatus;
  permissions: APIKeyPermission[];
  created_at: string;
  last_used_at?: string;
  revoked_at?: string;
  description?: string;
}

export interface CreateAPIKeyResponse {
  api_key: APIKey;
  plain_text_key: string;
}

export interface CreditTransaction {
  transaction_key: string;
  transaction_time: Date;
  transaction_type: CreditTransactionType;
  amount: number;
  running_balance: number;
  current_balance: number;
  description: string;
  usage_graph_id: GraphID;
  usage_execution_id: GraphExecutionID;
  usage_node_count: number;
  usage_starting_time: Date;
  user_id: string;
  user_email: string | null;
  reason: string | null;
  admin_email: string | null;
  extra_data: string | null;
}

export interface TransactionHistory {
  transactions: CreditTransaction[];
  next_transaction_time: Date | null;
}

export interface RefundRequest {
  id: string;
  user_id: UserID;
  transaction_key: string;
  amount: number;
  reason: string;
  result: string | null;
  status: string;
  created_at: Date;
  updated_at: Date;
}

export type OnboardingStep =
  // Introductory onboarding (Library)
  | "WELCOME"
  | "USAGE_REASON"
  | "INTEGRATIONS"
  | "AGENT_CHOICE"
  | "AGENT_NEW_RUN"
  | "AGENT_INPUT"
  | "CONGRATS"
  // First Wins
  | "GET_RESULTS"
  | "MARKETPLACE_VISIT"
  | "MARKETPLACE_ADD_AGENT"
  | "MARKETPLACE_RUN_AGENT"
  | "BUILDER_SAVE_AGENT"
  // Consistency Challenge
  | "RE_RUN_AGENT"
  | "SCHEDULE_AGENT"
  | "RUN_AGENTS"
  | "RUN_3_DAYS"
  // The Pro Playground
  | "TRIGGER_WEBHOOK"
  | "RUN_14_DAYS"
  | "RUN_AGENTS_100"
  // No longer used but tracked
  | "BUILDER_OPEN"
  | "BUILDER_RUN_AGENT";

export interface UserOnboarding {
  completedSteps: OnboardingStep[];
  walletShown: boolean;
  notified: OnboardingStep[];
  rewardedFor: OnboardingStep[];
  usageReason: string | null;
  integrations: string[];
  otherIntegrations: string | null;
  selectedStoreListingVersionId: string | null;
  agentInput: Record<string, string | number> | null;
  onboardingAgentExecutionId: GraphExecutionID | null;
  lastRunAt: Date | null;
  consecutiveRunDays: number;
  agentRuns: number;
}

/* *** UTILITIES *** */

/** Use branded types for IDs -> deny mixing IDs between different object classes */
export interface OttoDocument {
  url: string;
  relevance_score: number;
}

export interface OttoResponse {
  answer: string;
  documents: OttoDocument[];
  success: boolean;
  error: boolean;
}

export interface OttoQuery {
  query: string;
  conversation_history: { query: string; response: string }[];
  message_id: string;
  include_graph_data: boolean;
  graph_id?: string;
}

export interface StoreListingWithVersions {
  listing_id: string;
  slug: string;
  agent_id: string;
  agent_version: number;
  active_version_id: string | null;
  has_approved_version: boolean;
  creator_email: string | null;
  latest_version: StoreSubmission | null;
  versions: StoreSubmission[];
}

export interface StoreListingsWithVersionsResponse {
  listings: StoreListingWithVersions[];
  pagination: Pagination;
}

// Admin API Types
export type AdminSubmissionsRequest = {
  status?: SubmissionStatus;
  search?: string;
  page: number;
  page_size: number;
};

export type AdminListingHistoryRequest = {
  listing_id: string;
  page: number;
  page_size: number;
};

export type AdminSubmissionDetailsRequest = {
  store_listing_version_id: string;
};

export type AdminPendingSubmissionsRequest = {
  page: number;
  page_size: number;
};

export enum CreditTransactionType {
  TOP_UP = "TOP_UP",
  USAGE = "USAGE",
  GRANT = "GRANT",
  REFUND = "REFUND",
  CARD_CHECK = "CARD_CHECK",
}

export type UsersBalanceHistoryResponse = {
  history: CreditTransaction[];
  pagination: Pagination;
};

export type AddUserCreditsResponse = {
  new_balance: number;
  transaction_key: string;
};
