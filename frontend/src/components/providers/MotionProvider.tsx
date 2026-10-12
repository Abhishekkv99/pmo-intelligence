"use client";

import { MotionConfig } from "motion/react";

// Every animation follows the reader's "reduce motion" setting: transforms
// and layout animations are skipped, opacity changes still run.
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
