"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setToken } from "@/lib/auth-token";
import { retrieveCodeVerifier } from "@/lib/pkce";
import { API_ROUTES, ROUTES } from "@/lib/constants";
import type { TokenResponse } from "@/types/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function MicrosoftCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    async function handleCallback() {
      const code = searchParams.get("code");
      const errorParam = searchParams.get("error");
      const errorDescription = searchParams.get("error_description");

      if (errorParam) {
        setError(errorDescription ?? `Authentication failed: ${errorParam}`);
        return;
      }

      if (!code) {
        setError("No authorization code received from Microsoft.");
        return;
      }

      const codeVerifier = retrieveCodeVerifier();
      if (!codeVerifier) {
        setError(
          "Missing PKCE verifier. Please try signing in again from the login page.",
        );
        return;
      }

      try {
        const redirectUri = `${window.location.origin}${ROUTES.ssoCallback}`;
        const response = await api.post<TokenResponse>(
          API_ROUTES.ssoMicrosoftCallback,
          {
            code,
            code_verifier: codeVerifier,
            redirect_uri: redirectUri,
          },
        );
        setToken(response.access_token);
        // Full page navigation (not router.replace) ensures the browser
        // processes the Set-Cookie header before the next request, so
        // the proxy.ts middleware sees the refresh_token cookie.
        window.location.href = ROUTES.home;
      } catch (err) {
        // A refused sign-in (403: a guest, or no role) carries the reason
        setError(
          err instanceof ApiError && err.status === 403
            ? err.message
            : "Failed to complete SSO login. Please try again.",
        );
      }
    }

    void handleCallback();
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Sign In Failed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
            <Button
              className="w-full"
              onClick={() => router.replace(ROUTES.login)}
            >
              Back to Login
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Signing you in...</CardTitle>
        </CardHeader>
        <CardContent className="text-center text-muted-foreground">
          Completing Microsoft authentication. Please wait.
        </CardContent>
      </Card>
    </div>
  );
}

export default function MicrosoftCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center p-4">
          <Card className="w-full max-w-md">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">Loading...</CardTitle>
            </CardHeader>
          </Card>
        </div>
      }
    >
      <MicrosoftCallbackContent />
    </Suspense>
  );
}
