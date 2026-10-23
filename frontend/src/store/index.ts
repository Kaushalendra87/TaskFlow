import { create } from 'zustand';
import { api } from '@/lib/api';
import type {
  Job, JobSummary, Notification, JobProgressEvent,
  JobEvent, User,
} from '@/types';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, access: string, refresh: string) => void;
  setUser: (user: User) => void;
  logout: () => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null, accessToken: null, refreshToken: null, isAuthenticated: false,
  setAuth: (user, access, refresh) => {
    set({ user, accessToken: access, refreshToken: refresh, isAuthenticated: true });
    if (typeof window !== 'undefined') {
      localStorage.setItem('auth-storage', JSON.stringify({ user, accessToken: access, refreshToken: refresh, isAuthenticated: true }));
    }
  },
  setUser: (user) => set({ user }),
  logout: () => {
    set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
    if (typeof window !== 'undefined') localStorage.removeItem('auth-storage');
  },
  hydrate: async () => {
    try {
      const saved = localStorage.getItem('auth-storage');
      if (saved) {
        const data = JSON.parse(saved);
        if (data.accessToken && data.user) {
          const user = await api.me();
          set({ user, accessToken: data.accessToken, refreshToken: data.refreshToken, isAuthenticated: true });
        }
      }
    } catch {}
  },
}));

// Hydrate on mount
if (typeof window !== 'undefined') {
  try {
    const saved = localStorage.getItem('auth-storage');
    if (saved) {
      const data = JSON.parse(saved);
      if (data.accessToken && data.user) {
        useAuthStore.getState().setAuth(data.user, data.accessToken, data.refreshToken);
      }
    }
  } catch {}
}

interface JobState {
  jobs: Job[];
  currentJob: Job | null;
  summary: JobSummary | null;
  pagination: { count: number; next: string | null; previous: string | null } | null;
  isLoading: boolean;
  error: string | null;
  setJobs: (jobs: Job[], pagination?: any) => void;
  appendJobs: (jobs: Job[]) => void;
  setCurrentJob: (job: Job | null) => void;
  updateJob: (id: number, updates: Partial<Job>) => void;
  removeJob: (id: number) => void;
  setSummary: (summary: JobSummary) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [], currentJob: null, summary: null, pagination: null,
  isLoading: false, error: null,
  setJobs: (jobs, pagination) => set({ jobs, pagination: pagination ?? null }),
  appendJobs: (jobs) => set((state) => ({ jobs: [...state.jobs, ...jobs] })),
  setCurrentJob: (job) => set({ currentJob: job }),
  updateJob: (id, updates) => set((state) => ({
    jobs: state.jobs.map((j) => (j.id === id ? { ...j, ...updates } : j)),
    currentJob: state.currentJob?.id === id ? { ...state.currentJob, ...updates } : state.currentJob,
  })),
  removeJob: (id) => set((state) => ({
    jobs: state.jobs.filter((job) => job.id !== id),
    currentJob: state.currentJob?.id === id ? null : state.currentJob,
    pagination: state.pagination
      ? { ...state.pagination, count: Math.max(0, state.pagination.count - 1) }
      : null,
  })),
  setSummary: (summary) => set({ summary }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  clearError: () => set({ error: null }),
}));

// Persist jobs to sessionStorage
if (typeof window !== 'undefined') {
  try {
    const saved = sessionStorage.getItem('job-storage');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (parsed.jobs) useJobStore.getState().setJobs(parsed.jobs, parsed.pagination || null);
      if (parsed.currentJob) useJobStore.getState().setCurrentJob(parsed.currentJob);
      if (parsed.summary) useJobStore.getState().setSummary(parsed.summary);
    }
  } catch {}
  useJobStore.subscribe((state) => {
    sessionStorage.setItem('job-storage', JSON.stringify({
      jobs: state.jobs, currentJob: state.currentJob, summary: state.summary, pagination: state.pagination,
    }));
  });
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  pagination: { count: number; next: string | null; previous: string | null } | null;
  isLoading: boolean;
  setNotifications: (notifications: Notification[], pagination?: any) => void;
  prependNotifications: (notifications: Notification[]) => void;
  updateNotification: (id: number, updates: Partial<Notification>) => void;
  setUnreadCount: (count: number) => void;
  incrementUnreadCount: () => void;
  decrementUnreadCount: () => void;
  setLoading: (loading: boolean) => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [], unreadCount: 0, pagination: null, isLoading: false,
  setNotifications: (notifications, pagination) => set({ notifications, pagination: pagination ?? null }),
  prependNotifications: (notifications) => set((state) => ({ notifications: [...notifications, ...state.notifications] })),
  updateNotification: (id, updates) => set((state) => ({ notifications: state.notifications.map((n) => n.id === id ? { ...n, ...updates } : n) })),
  setUnreadCount: (count) => set({ unreadCount: count }),
  incrementUnreadCount: () => set((state) => ({ unreadCount: state.unreadCount + 1 })),
  decrementUnreadCount: () => set((state) => ({ unreadCount: Math.max(0, state.unreadCount - 1) })),
  setLoading: (loading) => set({ isLoading: loading }),
}));

if (typeof window !== 'undefined') {
  try {
    const saved = sessionStorage.getItem('notification-storage');
    if (saved) {
      const parsed = JSON.parse(saved);
      useNotificationStore.getState().setNotifications(parsed.notifications || [], parsed.pagination || null);
      useNotificationStore.getState().setUnreadCount(parsed.unreadCount || 0);
    }
  } catch {}
  useNotificationStore.subscribe((state) => {
    sessionStorage.setItem('notification-storage', JSON.stringify({
      notifications: state.notifications, unreadCount: state.unreadCount, pagination: state.pagination,
    }));
  });
}

interface ProgressState {
  progressEvents: JobProgressEvent[];
  currentProgress: JobProgressEvent | null;
  latestSequence: number;
  isLoading: boolean;
  setProgressEvents: (events: JobProgressEvent[]) => void;
  addProgressEvent: (event: JobProgressEvent) => void;
  setCurrentProgress: (event: JobProgressEvent | null) => void;
  setLatestSequence: (seq: number) => void;
  setLoading: (loading: boolean) => void;
}

export const useProgressStore = create<ProgressState>((set) => ({
  progressEvents: [], currentProgress: null, latestSequence: 0, isLoading: false,
  setProgressEvents: (events) => set({ progressEvents: events, latestSequence: events[events.length - 1]?.sequence ?? 0 }),
  addProgressEvent: (event) => set((state) => ({
    progressEvents: [...state.progressEvents, event], currentProgress: event, latestSequence: Math.max(state.latestSequence, event.sequence),
  })),
  setCurrentProgress: (event) => set({ currentProgress: event }),
  setLatestSequence: (seq) => set({ latestSequence: seq }),
  setLoading: (loading) => set({ isLoading: loading }),
}));

if (typeof window !== 'undefined') {
  try {
    const saved = sessionStorage.getItem('progress-storage');
    if (saved) {
      const parsed = JSON.parse(saved);
      useProgressStore.getState().setProgressEvents(parsed.progressEvents || []);
      useProgressStore.getState().setCurrentProgress(parsed.currentProgress || null);
      useProgressStore.getState().setLatestSequence(parsed.latestSequence || 0);
    }
  } catch {}
  useProgressStore.subscribe((state) => {
    sessionStorage.setItem('progress-storage', JSON.stringify({
      progressEvents: state.progressEvents, currentProgress: state.currentProgress, latestSequence: state.latestSequence,
    }));
  });
}

interface JobEventState {
  events: JobEvent[];
  pagination: { count: number; next: string | null; previous: string | null } | null;
  isLoading: boolean;
  setEvents: (events: JobEvent[], pagination?: JobEventState['pagination']) => void;
  appendEvents: (events: JobEvent[]) => void;
  setLoading: (loading: boolean) => void;
}

export const useJobEventStore = create<JobEventState>((set) => ({
  events: [], pagination: null, isLoading: false,
  setEvents: (events, pagination) => set({ events, pagination: pagination ?? null }),
  appendEvents: (events) => set((state) => ({ events: [...state.events, ...events] })),
  setLoading: (loading) => set({ isLoading: loading }),
}));

if (typeof window !== 'undefined') {
  try {
    const saved = sessionStorage.getItem('job-event-storage');
    if (saved) {
      const parsed = JSON.parse(saved);
      useJobEventStore.getState().setEvents(parsed.events || []);
    }
  } catch {}
  useJobEventStore.subscribe((state) => {
    sessionStorage.setItem('job-event-storage', JSON.stringify({ events: state.events }));
  });
}

interface UIState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark' | 'system';
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  initializeTheme: () => void;
}

const applyTheme = (theme: UIState['theme']) => {
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle(
    'dark',
    theme === 'dark' || (theme === 'system' && prefersDark)
  );
};

export const useUIStore = create<UIState>((set, get) => ({
  sidebarOpen: true,
  theme: 'system',
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setTheme: (theme) => {
    set({ theme });
    applyTheme(theme);
  },
  initializeTheme: () => {
    applyTheme(get().theme);
  },
}));

// Persist UI to localStorage
if (typeof window !== 'undefined') {
  try {
    const saved = localStorage.getItem('ui-storage');
    if (saved) {
      const parsed = JSON.parse(saved);
      useUIStore.getState().setSidebarOpen(parsed.sidebarOpen ?? true);
      useUIStore.getState().setTheme(parsed.theme || 'system');
      useUIStore.getState().initializeTheme();
    }
  } catch {}
  useUIStore.subscribe((state) => {
    localStorage.setItem('ui-storage', JSON.stringify({
      sidebarOpen: state.sidebarOpen,
      theme: state.theme,
    }));
  });
}
