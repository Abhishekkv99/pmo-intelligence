/**
 * Creating a session from an uploaded recording or a URL. The upload goes
 * through XMLHttpRequest, not fetch, for its upload progress events (from
 * Interview Intelligence's `lib/upload.ts`).
 */
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth-token";
import { API_ROUTES } from "@/lib/constants";
import type { SessionCreated } from "@/types/recordings";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

/** The recording types the backend accepts (`ALLOWED_EXTENSIONS`). */
export const RECORDING_ACCEPT = ".mp4,.mov,.webm,.mp3,.wav,.m4a,.ogg";
export const MAX_UPLOAD_MB = 500;

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface SessionUploadOptions {
  file: File;
  placementId: string;
  /** ISO 8601 with an offset. */
  heldAt: string;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}

function errorMessage(xhr: XMLHttpRequest): string {
  if (xhr.status === 413) return `The file is larger than ${MAX_UPLOAD_MB} MB`;
  try {
    const body = JSON.parse(xhr.responseText) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON: fall through to the status.
  }
  return `Upload failed (HTTP ${xhr.status})`;
}

export function uploadSession(
  options: SessionUploadOptions,
): Promise<SessionCreated> {
  const { file, onProgress, signal } = options;
  return new Promise<SessionCreated>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    form.append("placement_id", options.placementId);
    form.append("held_at", options.heldAt);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percentage: Math.round((event.loaded / event.total) * 100),
        });
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as SessionCreated);
        } catch {
          reject(new Error("The upload's answer could not be read"));
        }
      } else {
        reject(new Error(errorMessage(xhr)));
      }
    });
    xhr.addEventListener("error", () =>
      reject(new Error("Upload failed: network error")),
    );
    xhr.addEventListener("abort", () => reject(new Error("Upload cancelled")));
    signal?.addEventListener("abort", () => xhr.abort());

    xhr.open("POST", `${API_BASE_URL}${API_ROUTES.sessionUpload}`);
    xhr.withCredentials = true;
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(form);
  });
}

export function sessionFromUrl(
  url: string,
  placementId: string,
  heldAt: string,
): Promise<SessionCreated> {
  return api.post<SessionCreated>(API_ROUTES.sessionUrl, {
    url,
    placement_id: placementId,
    held_at: heldAt,
  });
}
