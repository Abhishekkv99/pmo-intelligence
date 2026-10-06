"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import type { UserResponse } from "@/types/auth";
import {
  api,
  ApiError,
  refreshAccessToken,
  setSessionExpiredHandler,
} from "@/lib/api";
import { getToken, removeToken } from "@/lib/auth-token";
import { ROUTES, API_ROUTES } from "@/lib/constants";

interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const PUBLIC_PATHS: readonly string[] = [ROUTES.login, ROUTES.ssoCallback];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // On mount: try to restore session via refresh cookie.
  // If a refresh token cookie exists, POST /auth/refresh returns a new
  // access token. If not, the user must log in again.
  const initAuth = useCallback(async () => {
    // If we already have a token in memory (e.g. after login), fetch user
    if (getToken()) {
      try {
        const userData = await api.get<UserResponse>(API_ROUTES.authMe);
        setUser(userData);
      } catch {
        removeToken();
        setUser(null);
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // No in-memory token — try refreshing via httpOnly cookie. The shared
    // refresh times out, so a refresh that never answers cannot leave the
    // app loading forever.
    try {
      if (await refreshAccessToken()) {
        const userData = await api.get<UserResponse>(API_ROUTES.authMe);
        setUser(userData);
      } else {
        // Backend clears the stale cookie in its 401 response,
        // preventing redirect loops on next navigation.
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void initAuth();
  }, [initAuth]);

  // A session that cannot be recovered mid-use (the refresh failed, or a
  // request was still refused after refreshing) clears the user, and the
  // redirect below sends the browser to the login page rather than leaving
  // it on a page whose requests will never succeed.
  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null));
    return () => setSessionExpiredHandler(null);
  }, []);

  useEffect(() => {
    if (isLoading) return;
    const isPublic = PUBLIC_PATHS.includes(pathname);
    if (!user && !isPublic) {
      router.replace(ROUTES.login);
    }
    if (user && isPublic) {
      router.replace(ROUTES.home);
    }
  }, [user, isLoading, pathname, router]);

  const logout = useCallback(() => {
    // Call server logout to revoke refresh tokens + clear cookie
    void api
      .post(API_ROUTES.authLogout)
      .catch(() => {
        // Best-effort — even if server logout fails, clear local state
      })
      .finally(() => {
        removeToken();
        setUser(null);
        router.replace(ROUTES.login);
      });
  }, [router]);

  const value = useMemo(
    () => ({ user, isLoading, logout }),
    [user, isLoading, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export { ApiError };
