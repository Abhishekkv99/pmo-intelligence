"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import { API_ROUTES } from "@/lib/constants";
import {
  generateCodeVerifier,
  generateCodeChallenge,
  storeCodeVerifier,
} from "@/lib/pkce";
import type { SSOConfigResponse } from "@/types/auth";

interface UseSSOLoginReturn {
  initiateSSO: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export function useSSOLogin(): UseSSOLoginReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initiateSSO = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const config = await api.get<SSOConfigResponse>(
        API_ROUTES.ssoMicrosoftConfig,
      );

      const codeVerifier = generateCodeVerifier();
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      storeCodeVerifier(codeVerifier);

      const params = new URLSearchParams({
        client_id: config.client_id,
        response_type: "code",
        redirect_uri: config.redirect_uri,
        response_mode: "query",
        scope: "openid email profile",
        code_challenge: codeChallenge,
        code_challenge_method: "S256",
      });

      const authorizeUrl = `https://login.microsoftonline.com/${config.authority}/oauth2/v2.0/authorize?${params.toString()}`;
      window.location.href = authorizeUrl;
    } catch {
      setError("Failed to initiate SSO login. Please try again.");
      setIsLoading(false);
    }
  }, []);

  return { initiateSSO, isLoading, error };
}
