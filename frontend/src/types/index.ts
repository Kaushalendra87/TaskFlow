export type JobStatus =
  | 'pending'
  | 'processing'
  | 'retrying'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type JobEventType =
  | 'created'
  | 'processing'
  | 'progress'
  | 'retrying'
  | 'completed'
  | 'failed'
  | 'cancelled';

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

export interface JobProgressEvent {
  id: number;
  sequence: number;
  event: string;
  status: string;
  progress: number;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface JobProgressHistoryResponse {
  job: {
    id: number;
    status: string;
    progress: number;
    latest_sequence: number;
  };
  events: JobProgressEvent[];
  has_more: boolean;
}

export interface JobListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Job[];
}

export interface JobSummary {
  total_jobs: number;
  pending_jobs: number;
  processing_jobs: number;
  retrying_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  cancelled_jobs: number;
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

export interface NotificationListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Notification[];
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface User {
  id: number;
  username: string;
  email: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
}

export interface JobEvent {
  id: number;
  job: number;
  event_type: JobEventType;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface JobEventListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: JobEvent[];
}

export interface JobCancelResponse {
  message: string;
  code: string;
  job: Job;
}

export interface ErrorResponse {
  detail: string;
  code: string;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
  status?: JobStatus;
  search?: string;
  ordering?: string;
}

export interface ProgressHistoryParams {
  after_sequence?: number;
}