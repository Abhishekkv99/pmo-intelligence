"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface EmptyStateAction {
  label: string;
  href?: string;
  onClick?: () => void;
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: EmptyStateAction;
  /**
   * A line icon, as an element (`<SquareCheck />`), shown in a soft lavender
   * circle above the title. An element rather than the component, so a
   * server page can pass it to this client component.
   */
  icon?: ReactNode;
}

/**
 * Nothing to show yet, or nothing to show this reader: a dashed card with an
 * optional icon, the title, a line of explanation and an optional action.
 */
export function EmptyState({
  title,
  description,
  action,
  icon,
}: EmptyStateProps) {
  return (
    <div
      className="flex min-h-[240px] flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-input bg-card/50 px-6 py-12 text-center"
      data-testid="empty-state"
    >
      {icon && (
        <div
          className="flex size-14 items-center justify-center rounded-full bg-lavender/25 text-primary dark:bg-lavender/15 [&_svg]:size-6"
          aria-hidden
        >
          {icon}
        </div>
      )}
      <div className="max-w-md space-y-1">
        <h3 className="text-lg font-medium">{title}</h3>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action &&
        (action.href ? (
          <Button variant="outline" asChild>
            <a href={action.href}>{action.label}</a>
          </Button>
        ) : (
          <Button variant="outline" onClick={action.onClick}>
            {action.label}
          </Button>
        ))}
    </div>
  );
}
