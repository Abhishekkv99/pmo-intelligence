/**
 * PKCE (Proof Key for Code Exchange) utilities for OAuth 2.0 authorization code flow.
 * Generates code_verifier and code_challenge per RFC 7636.
 */

const VERIFIER_LENGTH = 64;
const SESSION_KEY = "sso_code_verifier";

function generateRandomString(length: number): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(
    array,
    (byte) =>
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"[
        byte % 66
      ],
  ).join("");
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest("SHA-256", encoder.encode(plain));
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export function generateCodeVerifier(): string {
  return generateRandomString(VERIFIER_LENGTH);
}

export async function generateCodeChallenge(verifier: string): Promise<string> {
  const hash = await sha256(verifier);
  return base64UrlEncode(hash);
}

export function storeCodeVerifier(verifier: string): void {
  sessionStorage.setItem(SESSION_KEY, verifier);
}

export function retrieveCodeVerifier(): string | null {
  const verifier = sessionStorage.getItem(SESSION_KEY);
  if (verifier) {
    sessionStorage.removeItem(SESSION_KEY);
  }
  return verifier;
}
