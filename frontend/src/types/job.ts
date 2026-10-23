export type JobStatus =
  | "pending"
  | "processing"
  | "retrying"
  | "completed"
  | "failed"
  | "cancelled";

export interface Job {
  id: number;
  file: string;
  status: JobStatus;
  progress: number;
  error_message: string | null;
  cancel_requested: boolean;
  retry_count: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ProgressEvent {
  id: number;
  sequence: number;
  event: string;
  status: JobStatus;
  progress: number;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Notification {
  id: number;
  title: string;
  message: string;
  job_id: number | null;
  event_id: number | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}
