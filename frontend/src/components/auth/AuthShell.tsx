import { LogoMark, Wordmark } from "@/components/brand/Logo";
import { APP_NAME } from "@/lib/constants";
import { cn } from "@/lib/utils";

// The signed-out pages' frame: the twilight hero dissolving into the warm
// white canvas, the logo above, a footer below. It always shows the light
// Twilight theme (`theme-light`), whatever the reader's theme setting, which
// it never changes. It uses no portals (toasts, dialogs), since those render
// on `body`, outside the light scope.
export function AuthShell({
  children,
  below,
  footnote = "Internal tool.",
  heroClassName,
}: {
  /** The hero's content, on the twilight gradient. */
  children: React.ReactNode;
  /** Content on the warm white canvas under the hero. */
  below?: React.ReactNode;
  footnote?: string;
  heroClassName?: string;
}) {
  return (
    <div className="theme-light flex min-h-svh flex-col bg-background text-foreground selection:bg-lavender selection:text-twilight">
      <div className="bg-(image:--gradient-twilight) pt-8 pb-20 sm:pb-28 lg:pb-36">
        <div className="mx-auto max-w-[1240px] px-4 sm:px-10 lg:px-12">
          <header className="mb-12 py-2 sm:mb-16 lg:mb-20">
            <Wordmark className="text-white" />
          </header>
          <div className={heroClassName}>{children}</div>
        </div>
      </div>
      {below && (
        <div className="mx-auto w-full max-w-[1240px] px-4 py-16 sm:px-10 sm:py-24 lg:px-12">
          {below}
        </div>
      )}
      <footer
        className={cn(
          "mx-auto mt-auto flex w-full max-w-[1240px] flex-col items-center justify-between gap-4 px-4 pt-8 pb-16 sm:flex-row sm:px-10 lg:px-12",
          below && "border-t border-border",
        )}
      >
        <span className="flex items-center gap-2.5 text-sm font-medium">
          <LogoMark className="size-5" decorative />
          {APP_NAME}
        </span>
        <span className="font-mono text-xs text-muted-foreground">
          {footnote}
        </span>
      </footer>
    </div>
  );
}
