/** Credential-related API types. */

export type CredentialsType =
  | "api_key"
  | "oauth2"
  | "user_password"
  | "host_scoped";

// --8<-- [start:BlockIOCredentialsSubSchema]
// Provider names are now dynamic and fetched from the API
// This allows for SDK-registered providers without hardcoding
export type CredentialsProviderName = string;

// For backward compatibility, we'll keep PROVIDER_NAMES but it should be
// populated dynamically from the API. This is a placeholder that will be
// replaced with actual values from the /api/integrations/providers endpoint
export const PROVIDER_NAMES = {} as Record<string, string>;
// --8<-- [end:BlockIOCredentialsSubSchema]


export type CredentialsMetaResponse = {
  id: string;
  provider: CredentialsProviderName;
  type: CredentialsType;
  title?: string;
  scopes?: Array<string>;
  username?: string;
  host?: string;
};

/* Mirror of backend/server/integrations/router.py:CredentialsDeletionResponse */
export type CredentialsDeleteResponse = {
  deleted: true;
  revoked: boolean | null;
};

/* Mirror of backend/server/integrations/router.py:CredentialsDeletionNeedsConfirmationResponse */
export type CredentialsDeleteNeedConfirmationResponse = {
  deleted: false;
  need_confirmation: true;
  message: string;
};

/* Mirror of backend/data/model.py:CredentialsMetaInput */
export type CredentialsMetaInput = {
  id: string;
  type: CredentialsType;
  title?: string | null;
  provider: string;
};

/* Mirror of backend/backend/data/model.py:_BaseCredentials */
type BaseCredentials = {
  id: string;
  type: CredentialsType;
  title?: string;
  provider: CredentialsProviderName;
};

/* Mirror of backend/backend/data/model.py:OAuth2Credentials */
export type OAuth2Credentials = BaseCredentials & {
  type: "oauth2";
  scopes: string[];
  username?: string;
  access_token: string;
  access_token_expires_at?: number;
  refresh_token?: string;
  refresh_token_expires_at?: number;
  metadata: Record<string, any>;
};

/* Mirror of backend/backend/data/model.py:APIKeyCredentials */
export type APIKeyCredentials = BaseCredentials & {
  type: "api_key";
  title: string;
  api_key: string;
  expires_at?: number;
};

export type UserPasswordCredentials = BaseCredentials & {
  type: "user_password";
  title: string;
  username: string;
  password: string;
};

/* Mirror of backend/backend/data/model.py:HostScopedCredentials */
export type HostScopedCredentials = BaseCredentials & {
  type: "host_scoped";
  title: string;
  host: string;
  headers: Record<string, string>;
};

// Mirror of backend/backend/data/notifications.py:NotificationType

export type Credentials =
  | APIKeyCredentials
  | OAuth2Credentials
  | UserPasswordCredentials
  | HostScopedCredentials;
