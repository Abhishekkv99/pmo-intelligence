"use client";

interface UploadProgressProps {
  percentage: number;
  isComplete: boolean;
}

/** The progress bar under an upload (from Interview Intelligence). */
export function UploadProgress({
  percentage,
  isComplete,
}: UploadProgressProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {isComplete ? "Upload complete" : "Uploading…"}
        </span>
        <span className="font-medium">{percentage}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 w-full overflow-hidden rounded-full bg-secondary"
      >
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            isComplete ? "bg-green-500" : "bg-primary"
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
