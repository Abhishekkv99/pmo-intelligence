"use client";

import { useCallback, useId, useState } from "react";
import { Card } from "@/components/ui/card";

interface FileDropZoneProps {
  onFileSelect: (file: File) => void;
  selectedFile: File | null;
  accept?: string;
  /** What the zone accepts, shown under the prompt. */
  hint: string;
  error?: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Drag a file in, or click to browse (from Interview Intelligence). */
export function FileDropZone({
  onFileSelect,
  selectedFile,
  accept,
  hint,
  error,
}: FileDropZoneProps) {
  const inputId = useId();
  const [isDragging, setIsDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) onFileSelect(file);
    },
    [onFileSelect],
  );

  return (
    <Card
      className={`relative cursor-pointer border-2 border-dashed p-8 text-center transition-colors ${
        isDragging
          ? "border-primary bg-primary/5"
          : error
            ? "border-destructive"
            : selectedFile
              ? "border-primary/50 bg-primary/5"
              : "border-muted-foreground/25 hover:border-primary/50"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setIsDragging(false);
      }}
      onDrop={handleDrop}
      onClick={() => document.getElementById(inputId)?.click()}
    >
      <input
        id={inputId}
        data-testid="file-input"
        type="file"
        accept={accept}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelect(file);
        }}
        className="hidden"
      />
      {selectedFile ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">{selectedFile.name}</p>
          <p className="text-xs text-muted-foreground">
            {formatFileSize(selectedFile.size)}
          </p>
          <p className="text-xs text-muted-foreground">
            Click or drag to replace
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            {isDragging ? "Drop the file here" : "Drag a file here"}
          </p>
          <p className="text-xs text-muted-foreground">
            or click to browse: {hint}
          </p>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </Card>
  );
}
