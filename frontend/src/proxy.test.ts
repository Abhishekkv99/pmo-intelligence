import { describe, it, expect } from "vitest";
import { config } from "./proxy";

// The matcher is a path regex; a path it does not match never reaches the
// proxy, so a signed-out browser can fetch it without being sent to /login.
const matcher = new RegExp(`^${config.matcher[0]}$`);

describe("proxy matcher", () => {
  it.each(["/icon.svg", "/favicon.ico", "/api/health", "/_next/static/x.js"])(
    "lets %s through without the sign-in check",
    (path) => {
      expect(matcher.test(path)).toBe(false);
    },
  );

  it.each(["/", "/login", "/sessions", "/placements/abc"])(
    "checks the sign-in on %s",
    (path) => {
      expect(matcher.test(path)).toBe(true);
    },
  );
});
