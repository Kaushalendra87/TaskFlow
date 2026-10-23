import type {
  Job,
  JobListResponse,
  JobSummary,
  JobProgressHistoryResponse,
  Notification,
  NotificationListResponse,
  UnreadCountResponse,
  User,
  AuthTokens,
  LoginRequest,
  RegisterRequest,
  JobEventListResponse,
  ErrorResponse,
  PaginationParams,
  ProgressHistoryParams,
} from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

class APIClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  constructor() {
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
  }

  setTokens(access: string, refresh: string) {
    this.accessToken = access;
    this.refreshToken = refresh;
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
  }

  clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers: HeadersInit = {
      ...(options.body instanceof FormData
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...options.headers,
    };

    if (this.accessToken) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401 && this.refreshToken) {
      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        return this.request<T>(endpoint, options);
      }
    }

    if (!response.ok) {
      let errorData: ErrorResponse = {
        detail: 'Request failed',
        code: 'unknown',
      };
      try {
        errorData = await response.json();
      } catch {
        // Use default error
      }
      throw new APIError(
        errorData.detail || 'Request failed',
        errorData.code || 'unknown',
        response.status
      );
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  private async refreshAccessToken(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: this.refreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        this.setTokens(data.access, data.refresh);
        return true;
      }
    } catch {
      // Refresh failed
    }
    this.clearTokens();
    return false;
  }

  // Auth
  async login(credentials: LoginRequest): Promise<AuthTokens> {
    const data = await this.request<AuthTokens>('/api/auth/login/', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
    this.setTokens(data.access, data.refresh);
    return data;
  }

  async register(data: RegisterRequest): Promise<User> {
    return this.request<User>('/api/auth/register/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async refresh(): Promise<AuthTokens> {
    const data = await this.request<AuthTokens>('/api/auth/refresh/', {
      method: 'POST',
      body: JSON.stringify({ refresh: this.refreshToken }),
    });
    this.setTokens(data.access, data.refresh);
    return data;
  }

  async me(): Promise<User> {
    return this.request<User>('/api/auth/me/');
  }

  logout() {
    this.clearTokens();
  }

  // Jobs
  async listJobs(params: PaginationParams = {}): Promise<JobListResponse> {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    return this.request<JobListResponse>(`/api/jobs/?${searchParams.toString()}`);
  }

  async createJob(file: File): Promise<Job> {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<Job>('/api/jobs/', {
      method: 'POST',
      body: formData,
      headers: {}, // Let browser set Content-Type for FormData
    });
  }

  async getJob(id: number): Promise<Job> {
    return this.request<Job>(`/api/jobs/${id}/`);
  }

  async deleteJob(id: number): Promise<void> {
    await this.request<void>(`/api/jobs/${id}/`, {
      method: 'DELETE',
    });
  }

  async downloadJobFile(filePath: string): Promise<void> {
    const mediaBaseUrl =
      import.meta.env.VITE_MEDIA_URL ||
      API_BASE_URL ||
      window.location.origin;
    let fileUrl = new URL(filePath, mediaBaseUrl);

    if (
      import.meta.env.DEV &&
      !import.meta.env.VITE_MEDIA_URL &&
      !API_BASE_URL &&
      fileUrl.pathname.startsWith('/media/')
    ) {
      fileUrl = new URL(
        `${fileUrl.pathname}${fileUrl.search}${fileUrl.hash}`,
        window.location.origin
      );
    }

    const headers: HeadersInit = {};
    if (this.accessToken) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(fileUrl, { headers });
    if (!response.ok) {
      throw new APIError('Unable to download this uploaded file.', 'download_failed', response.status);
    }

    const contentType = response.headers.get('Content-Type') || '';
    if (contentType.includes('text/html')) {
      throw new APIError(
        'The server returned a webpage instead of the uploaded file. Check the media URL configuration.',
        'invalid_download_response',
        response.status
      );
    }

    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = decodeURIComponent(fileUrl.pathname.split('/').pop() || 'taskflow-upload.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  async cancelJob(id: number): Promise<Job> {
    return this.request<Job>(`/api/jobs/${id}/cancel/`, {
      method: 'POST',
    });
  }

  async getJobProgress(id: number): Promise<{
    job_id: number;
    status: string;
    progress: number;
    created_at: string;
    updated_at: string;
    completed_at: string | null;
    retry_count: number;
    error_message: string | null;
  }> {
    return this.request(`/api/jobs/${id}/progress/`);
  }

  async getJobProgressHistory(
    id: number,
    params: ProgressHistoryParams = {}
  ): Promise<JobProgressHistoryResponse> {
    const searchParams = new URLSearchParams();
    if (params.after_sequence !== undefined) {
      searchParams.append('after_sequence', String(params.after_sequence));
    }
    return this.request<JobProgressHistoryResponse>(
      `/api/jobs/${id}/progress-history/?${searchParams.toString()}`
    );
  }

  async getJobEvents(
    id: number,
    params: PaginationParams = {}
  ): Promise<JobEventListResponse> {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    return this.request<JobEventListResponse>(
      `/api/jobs/${id}/events/?${searchParams.toString()}`
    );
  }

  // Summary
  async getSummary(): Promise<JobSummary> {
    return this.request<JobSummary>('/api/jobs/summary/');
  }

  async getDailySummary(date?: string): Promise<{
    summary_date: string;
    total_jobs: number;
    pending_jobs: number;
    processing_jobs: number;
    retrying_jobs: number;
    completed_jobs: number;
    failed_jobs: number;
    cancelled_jobs: number;
    run_status: string;
  }> {
    const searchParams = new URLSearchParams();
    if (date) searchParams.append('date', date);
    return this.request(`/api/jobs/summary/daily/?${searchParams.toString()}`);
  }

  // Notifications
  async listNotifications(params: { unread?: boolean; page?: number; page_size?: number } = {}): Promise<NotificationListResponse> {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    return this.request<NotificationListResponse>(
      `/api/jobs/notifications/?${searchParams.toString()}`
    );
  }

  async getUnreadCount(): Promise<UnreadCountResponse> {
    return this.request<UnreadCountResponse>('/api/jobs/notifications/unread-count/');
  }

  async markNotificationRead(id: number): Promise<Notification> {
    return this.request<Notification>(`/api/jobs/notifications/${id}/read/`, {
      method: 'POST',
    });
  }

  async markAllNotificationsRead(): Promise<{ message: string; updated_count: number }> {
    return this.request('/api/jobs/notifications/read-all/', {
      method: 'POST',
    });
  }

  // WebSocket helpers
  getWebSocketUrl(path: string): string {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const baseUrl = import.meta.env.VITE_WS_URL || `${wsProtocol}//127.0.0.1:8000`;
    const url = new URL(path, baseUrl);
    if (this.accessToken) {
      url.searchParams.set('token', this.accessToken);
    }
    return url.toString();
  }
}

export class APIError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number
  ) {
    super(message);
    this.name = 'APIError';
  }
}

export const api = new APIClient();