"use client";

import { motion } from "motion/react";
import { MiniRiskBoard } from "./MiniRiskBoard";

// Every claim here is true of the product as built or planned in version 1;
// see "Copy" in docs/DESIGN.md before changing a word.
const HIGHLIGHTS = [
  {
    title: "Every call, read",
    body: "Recorded PMO calls are transcribed by speaker and read for issues, morale, client signals and actions, each with the words that raised it.",
  },
  {
    title: "Six dimensions, one score",
    body: "Delivery, technical, relationship, engagement, onboarding and communication, scored 1 to 10 by a fixed formula, never by the model.",
  },
  {
    title: "A flag only with evidence",
    body: "Every early warning links to the quote and the moment in the call that raised it. A person decides what to do.",
  },
];

// A short rise into place; MotionProvider skips the movement for readers who
// ask for reduced motion.
function rise(delay: number) {
  return {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, ease: "easeOut" as const, delay },
  };
}

/** The hero: the promise and the sign-in action beside the sample preview. */
export function ShowcaseHero({ action }: { action: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-14">
      <div className="flex flex-col items-start lg:col-span-7">
        <motion.p
          {...rise(0)}
          className="mb-6 font-mono text-[11px] font-bold tracking-[0.2em] text-lavender uppercase"
        >
          Placement health, live
        </motion.p>
        <motion.h1
          {...rise(0.05)}
          className="mb-8 text-[clamp(40px,4.4vw,62px)] leading-[0.98] font-bold tracking-[-0.035em] text-white"
        >
          Know which placement is at risk.{" "}
          <span className="block text-white/95">Before the client does.</span>
        </motion.h1>
        <motion.p
          {...rise(0.1)}
          className="mb-10 max-w-xl text-lg leading-relaxed text-balance text-white/80 sm:text-xl"
        >
          Recorded PMO calls and the Teams group chat become six health scores,
          a trend and early warnings, with the quote behind every one.
        </motion.p>
        <motion.div {...rise(0.15)} className="w-full">
          {action}
        </motion.div>
      </div>
      <motion.div {...rise(0.2)} className="lg:col-span-5">
        <MiniRiskBoard />
      </motion.div>
    </div>
  );
}

/** The three highlights on the warm white canvas under the hero. */
export function ShowcaseHighlights() {
  return (
    <ul className="grid grid-cols-1 divide-y divide-input border-y border-input md:grid-cols-3 md:divide-x md:divide-y-0">
      {HIGHLIGHTS.map((item) => (
        <li
          key={item.title}
          className="py-10 md:px-8 md:py-12 md:first:pl-0 md:last:pr-0"
        >
          <h2 className="mb-3 text-xl font-bold tracking-tight text-foreground sm:text-2xl">
            {item.title}
          </h2>
          <p className="text-[15px] leading-relaxed text-muted-foreground">
            {item.body}
          </p>
        </li>
      ))}
    </ul>
  );
}
