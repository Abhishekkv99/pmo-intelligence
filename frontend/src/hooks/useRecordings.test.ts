import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError } from "@/lib/api";

const post = vi.fn();
const put = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      post: (...args: unknown[]) => post(...args),
      put: (...args: unknown[]) => put(...args),
    },
  };
});

import {
  chooseFolderConsultant,
  processRecording,
  requestScan,
} from "./useRecordings";

const created = {
  id: "s1",
  placement_id: "p1",
  source: "s3",
  status: "uploaded",
  held_at: "2026-10-01T09:00:00Z",
};

describe("recordings mutations", () => {
  beforeEach(() => {
    post.mockReset();
    put.mockReset();
  });

  it("processes with an empty body, or with the chosen placement", async () => {
    post.mockResolvedValue(created);

    await expect(processRecording("r1", null)).resolves.toEqual({
      kind: "queued",
      session: created,
    });
    expect(post).toHaveBeenCalledWith("/recordings/r1/process", {});

    await processRecording("r1", "p2");
    expect(post).toHaveBeenLastCalledWith("/recordings/r1/process", {
      placement_id: "p2",
    });
  });

  it("turns a 409 carrying placements into a choice", async () => {
    const choice = {
      detail: "More than one placement of this consultant covers 2026-10-01",
      placements: [{ id: "p1" }, { id: "p2" }],
    };
    post.mockRejectedValue(new ApiError(choice.detail, 409, choice));

    await expect(processRecording("r1", null)).resolves.toEqual({
      kind: "choose",
      choice,
    });
  });

  it("rejects any other refusal with the API's message", async () => {
    post.mockRejectedValue(
      new ApiError("This recording is already session s9", 409, {
        detail: "This recording is already session s9",
      }),
    );

    await expect(processRecording("r1", null)).rejects.toThrow(
      "already session s9",
    );
  });

  it("chooses a folder's consultant and asks for a scan", async () => {
    post.mockResolvedValue({ queued: true });

    await chooseFolderConsultant("f1", "c1");
    expect(put).toHaveBeenCalledWith("/recording-folders/f1/consultant", {
      consultant_id: "c1",
    });
    await expect(requestScan()).resolves.toEqual({ queued: true });
    expect(post).toHaveBeenCalledWith("/recordings/scan");
  });
});
