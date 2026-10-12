"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import { APP_NAME } from "@/lib/constants";

// The product mark: a lavender pulse line in a deep twilight square.
// Its colours are fixed (not theme tokens) so the mark reads the same on the
// light canvas, the twilight hero and the dark theme. With `decorative` it is
// hidden from assistive technology (it sits beside the product name).
export function LogoMark({
  className,
  decorative = false,
}: {
  className?: string;
  decorative?: boolean;
}) {
  // One gradient id per mark: a repeated id resolves to the first definition,
  // which may sit in a hidden element (the mobile sidebar) and not render.
  const sheenId = useId();
  return (
    <svg
      viewBox="0 0 40 40"
      className={cn("size-10 shrink-0", className)}
      {...(decorative
        ? { "aria-hidden": true }
        : { role: "img", "aria-label": APP_NAME })}
    >
      <defs>
        <linearGradient id={sheenId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#805AD5" stopOpacity="0.3" />
          <stop offset="1" stopColor="#805AD5" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="#2D2152" />
      <rect width="40" height="40" rx="12" fill={`url(#${sheenId})`} />
      <rect
        x="0.5"
        y="0.5"
        width="39"
        height="39"
        rx="11.5"
        fill="none"
        stroke="#644B9E"
        strokeOpacity="0.5"
      />
      <path
        d="M30 20h-4l-3 7-6-14-3 7h-4"
        fill="none"
        stroke="#CBB7FB"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// The mark beside the product name. Not a heading: page headings stay with
// the pages, so a heading search for the app name finds one element.
export function Wordmark({
  className,
  markClassName,
}: {
  className?: string;
  markClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <LogoMark className={markClassName} decorative />
      <span className="text-[17px] font-bold tracking-tight">{APP_NAME}</span>
    </span>
  );
}
