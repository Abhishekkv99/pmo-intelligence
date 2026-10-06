"use client";

import { SWRConfig } from "swr";
import { apiFetcher, ApiError } from "@/lib/api";
import { removeToken } from "@/lib/auth-token";
import { ROUTES } from "@/lib/constants";

export function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher: apiFetcher,
        revalidateOnFocus: false,
        dedupingInterval: 5000,
        errorRetryCount: 3,
        onErrorRetry: (error, _key, _config, revalidate, { retryCount }) => {
          // Never retry on 401 — AuthProvider handles session recovery
          if (error instanceof ApiError && error.status === 401) return;
          // Default retry for other errors (max 3)
          if (retryCount >= 3) return;
          setTimeout(() => void revalidate({ retryCount }), 5000);
        },
        onError: (error: unknown) => {
          if (error instanceof ApiError && error.status === 401) {
            removeToken();
            // Only redirect if not already on a public page
            const path = window.location.pathname;
            if (path !== ROUTES.login) {
              window.location.href = ROUTES.login;
            }
          }
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
