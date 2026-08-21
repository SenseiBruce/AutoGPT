/** UserApi BackendAPI methods. */

import type {
  NotificationPreference,
  NotificationPreferenceDTO,
  RefundRequest,
  StoreAgentDetails,
  TransactionHistory,
  User,
  UserOnboarding,
} from "./types";

import type { BackendAPIBase } from "./client-base";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Constructor<T = {}> = new (...args: any[]) => T;

export function withUserApi<TBase extends Constructor<BackendAPIBase>>(Base: TBase) {
  return class extends Base {
      createUser(): Promise<User> {
        return this._request("POST", "/auth/user", {});
      }

      updateUserEmail(email: string): Promise<{ email: string }> {
        return this._request("POST", "/auth/user/email", { email });
      }

      ////////////////////////////////////////
      /////////////// CREDITS ////////////////
      ////////////////////////////////////////

      getUserCredit(): Promise<{ credits: number }> {
        return this._get("/credits");
      }

      getUserPreferences(): Promise<NotificationPreferenceDTO> {
        return this._get("/auth/user/preferences");
      }

      updateUserPreferences(
        preferences: NotificationPreferenceDTO,
      ): Promise<NotificationPreference> {
        return this._request("POST", "/auth/user/preferences", preferences);
      }

      getAutoTopUpConfig(): Promise<{ amount: number; threshold: number }> {
        return this._get("/credits/auto-top-up");
      }

      setAutoTopUpConfig(config: {
        amount: number;
        threshold: number;
      }): Promise<{ amount: number; threshold: number }> {
        return this._request("POST", "/credits/auto-top-up", config);
      }

      getTransactionHistory(
        lastTransction: Date | null = null,
        countLimit: number | null = null,
        transactionType: string | null = null,
      ): Promise<TransactionHistory> {
        const filters: Record<string, any> = {};
        if (lastTransction) filters.transaction_time = lastTransction;
        if (countLimit) filters.transaction_count_limit = countLimit;
        if (transactionType) filters.transaction_type = transactionType;
        return this._get(`/credits/transactions`, filters);
      }

      getRefundRequests(): Promise<RefundRequest[]> {
        return this._get(`/credits/refunds`);
      }

      requestTopUp(credit_amount: number): Promise<{ checkout_url: string }> {
        return this._request("POST", "/credits", { credit_amount });
      }

      refundTopUp(transaction_key: string, reason: string): Promise<number> {
        return this._request("POST", `/credits/${transaction_key}/refund`, {
          reason,
        });
      }

      getUserPaymentPortalLink(): Promise<{ url: string }> {
        return this._get("/credits/manage");
      }

      fulfillCheckout(): Promise<void> {
        return this._request("PATCH", "/credits");
      }

      ////////////////////////////////////////
      ////////////// ONBOARDING //////////////
      ////////////////////////////////////////

      getUserOnboarding(): Promise<UserOnboarding> {
        return this._get("/onboarding");
      }

      updateUserOnboarding(
        onboarding: Omit<Partial<UserOnboarding>, "rewardedFor">,
      ): Promise<void> {
        return this._request("PATCH", "/onboarding", onboarding);
      }

      getOnboardingAgents(): Promise<StoreAgentDetails[]> {
        return this._get("/onboarding/agents");
      }

      /** Check if onboarding is enabled not if user finished it or not. */
      isOnboardingEnabled(): Promise<boolean> {
        return this._get("/onboarding/enabled");
      }

      ////////////////////////////////////////
  };
}
