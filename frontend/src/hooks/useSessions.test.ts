import { describe, it, expect, vi, beforeEach } from "vitest";

const post = vi.fn();
const patch = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      post: (...args: unknown[]) => post(...args),
      patch: (...args: unknown[]) => patch(...args),
    },
  };
});

import {
  retrySession,
  sessionPath,
  sessionRefreshInterval,
  setSessionKind,
} from "./useSessions";
import type { SessionDetail } from "@/types/sessions";

describe("session mutations", () => {
  beforeEach(() => {
    post.mockReset();
    patch.mockReset();
  });

  it("addresses a session by id", () => {
    expect(sessionPath("s1")).toBe("/sessions/s1");
  });

  it("sets the kind with a PATCH", async () => {
    patch.mockResolvedValue({ id: "s1" });
    await setSessionKind("s1", "escalation");
    expect(patch).toHaveBeenCalledWith("/sessions/s1/kind", {
      kind: "escalation",
    });
  });

  it("retries with an empty POST", async () => {
    post.mockResolvedValue({ id: "s1", status: "transcribed" });
    await retrySession("s1");
    expect(post).toHaveBeenCalledWith("/sessions/s1/retry");
  });
});

describe("session page polling", () => {
  const at = (status: string) => ({ status }) as SessionDetail;

  it("polls every 10 s until the session is completed or failed", () => {
    for (const status of [
      "uploaded",
      "transcribing",
      "transcribed",
      "analyzing",
    ]) {
      expect(sessionRefreshInterval(at(status))).toBe(10_000);
    }
    expect(sessionRefreshInterval(at("completed"))).toBe(0);
    expect(sessionRefreshInterval(at("failed"))).toBe(0);
    expect(sessionRefreshInterval(undefined)).toBe(0);
  });
});
