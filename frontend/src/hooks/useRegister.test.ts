import { describe, it, expect, vi, beforeEach } from "vitest";

const post = vi.fn();
const patch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    post: (...args: unknown[]) => post(...args),
    patch: (...args: unknown[]) => patch(...args),
  },
}));

import { quickAdd, saveRecord } from "./useRegister";

describe("register mutations", () => {
  beforeEach(() => {
    post.mockReset();
    patch.mockReset();
  });

  it("creates with POST when there is no id", async () => {
    await saveRecord("/clients", null, { name: "Barclays" });

    expect(post).toHaveBeenCalledWith("/clients", { name: "Barclays" });
    expect(patch).not.toHaveBeenCalled();
  });

  it("updates with PATCH on the record's path", async () => {
    await saveRecord("/clients", "c1", { name: "Barclays" });

    expect(patch).toHaveBeenCalledWith("/clients/c1", { name: "Barclays" });
  });

  it("sends the quick-add lines with the dry-run flag", async () => {
    const lines = ["PRJ ITC DS - Asha Rao - WTW - 1/9/2026 - 1/3/2027"];

    await quickAdd(lines, true);

    expect(post).toHaveBeenCalledWith(
      "/register/quick-add",
      { lines },
      { params: { dry_run: "true" } },
    );
  });
});
