"use client";

import { Button } from "@/components/ui/button";
import { useSSOLogin } from "@/hooks/useSSOLogin";

// Microsoft's four-square mark, as Microsoft's sign-in button guidance draws it.
function MicrosoftMark() {
  return (
    <svg viewBox="0 0 21 21" className="size-[18px]" aria-hidden>
      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </svg>
  );
}

// The only way in: Microsoft sign-in, for staff whose account holds a role.
// It sits on the twilight hero, so its colours are the hero's.
export function LoginForm() {
  const { initiateSSO, isLoading: ssoLoading, error: ssoError } = useSSOLogin();

  return (
    <div className="flex flex-col items-start gap-3">
      {ssoError && (
        <div
          role="alert"
          className="w-full max-w-md rounded-lg border border-white/20 bg-white/95 p-3 text-sm text-destructive"
        >
          {ssoError}
        </div>
      )}
      <Button
        type="button"
        disabled={ssoLoading}
        onClick={() => void initiateSSO()}
        className="h-auto gap-3 rounded-lg bg-secondary px-6 py-3.5 text-[15px] font-semibold text-twilight shadow-[0_4px_16px_rgb(0_0_0/0.18)] transition-all hover:-translate-y-0.5 hover:bg-accent hover:shadow-[0_8px_24px_rgb(0_0_0/0.22)] focus-visible:ring-lavender/60 motion-reduce:hover:translate-y-0"
      >
        <MicrosoftMark />
        {ssoLoading ? "Redirecting..." : "Sign in with Microsoft"}
      </Button>
      <p className="pl-0.5 text-[13px] font-medium text-white/70">
        Staff with a role only · Microsoft Entra ID
      </p>
    </div>
  );
}
