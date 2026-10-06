import { describe, it, expect, beforeEach } from "vitest";
import {
  generateCodeVerifier,
  generateCodeChallenge,
  storeCodeVerifier,
  retrieveCodeVerifier,
} from "./pkce";

describe("PKCE utilities", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("generateCodeVerifier returns a 64-character string", () => {
    const verifier = generateCodeVerifier();
    expect(verifier).toHaveLength(64);
    expect(typeof verifier).toBe("string");
  });

  it("generateCodeVerifier returns unique values on each call", () => {
    const v1 = generateCodeVerifier();
    const v2 = generateCodeVerifier();
    expect(v1).not.toBe(v2);
  });

  it("generateCodeChallenge returns a base64url-encoded SHA-256 hash", async () => {
    const verifier = "test_verifier_string";
    const challenge = await generateCodeChallenge(verifier);

    expect(typeof challenge).toBe("string");
    expect(challenge.length).toBeGreaterThan(0);
    // base64url: no +, /, or = characters
    expect(challenge).not.toMatch(/[+/=]/);
  });

  it("generateCodeChallenge returns consistent output for same input", async () => {
    const verifier = "deterministic_test";
    const c1 = await generateCodeChallenge(verifier);
    const c2 = await generateCodeChallenge(verifier);
    expect(c1).toBe(c2);
  });

  it("storeCodeVerifier persists to sessionStorage and retrieveCodeVerifier returns it", () => {
    storeCodeVerifier("my_verifier");
    const result = retrieveCodeVerifier();
    expect(result).toBe("my_verifier");
  });

  it("retrieveCodeVerifier clears the stored verifier after retrieval", () => {
    storeCodeVerifier("ephemeral");
    retrieveCodeVerifier();
    const second = retrieveCodeVerifier();
    expect(second).toBeNull();
  });

  it("retrieveCodeVerifier returns null when nothing is stored", () => {
    expect(retrieveCodeVerifier()).toBeNull();
  });
});
