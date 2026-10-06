export interface RunningJob {
  /** The pipeline the job runs; each pipeline registers its own kind. */
  kind: string;
  /** The subject the job processes (a session, a message thread...). */
  id: string;
  started_at: string;
  /** Zero-based index of the worker executing the job. */
  worker: number;
}

export interface ProcessingStatusResponse {
  /** Jobs waiting to run, of every kind. */
  queue_depth: number;
  /** Worker count; at most this many entries appear in `running`. */
  capacity: number;
  running: RunningJob[];
  /** Resident memory of the backend process; null where /proc is unavailable. */
  rss_mib: number | null;
  memory_diagnostics_enabled: boolean;
}
