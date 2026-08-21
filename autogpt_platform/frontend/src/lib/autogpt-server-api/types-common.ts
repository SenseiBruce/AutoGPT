/** Shared API types. */

import type { CredentialsProviderName } from "./types-credentials";

export type Pagination = {
  total_items: number;
  total_pages: number;
  current_page: number;
  page_size: number;
};

export type Webhook = {
  id: string;
  url: string;
  provider: CredentialsProviderName;
  credentials_id: string; // empty string if not appicable
  webhook_type: string;
  resource: string; // empty string if not appicable
  events: string[];
  secret: string;
  config: Record<string, any>;
  provider_webhook_id?: string;
};
