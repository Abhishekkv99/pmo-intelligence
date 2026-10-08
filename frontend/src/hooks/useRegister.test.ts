import { describe, it, expect, vi, beforeEach } from "vitest";

const post = vi.fn();
const patch = vi.fn();
const postFormData = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    post: (...args: unknown[]) => post(...args),
    patch: (...args: unknown[]) => patch(...args),
    postFormData: (...args: unknown[]) => postFormData(...args),
  },
}));

import { importRegister, saveRecord } from "./useRegister";

describe("register mutations", () => {
  beforeEach(() => {
    post.mockReset();
    patch.mockReset();
    postFormData.mockReset();
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

  it("sends the file with the dry-run flag", async () => {
    const file = new File(["a,b"], "register.csv", { type: "text/csv" });

    await importRegister(file, true);

    const [path, form, options] = postFormData.mock.calls[0] as [
      string,
      FormData,
      { params: Record<string, string> },
    ];
    expect(path).toBe("/register/import");
    expect(form.get("file")).toBe(file);
    expect(options.params).toEqual({ dry_run: "true" });
  });
});
