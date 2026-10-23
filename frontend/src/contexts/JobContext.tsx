import React, { createContext, useContext, useCallback } from 'react';
import { api } from '@/lib/api';
import { useJobStore } from '@/store';
import type { Job, JobSummary, PaginationParams } from '@/types';
import toast from 'react-hot-toast';

interface JobContextValue {
  jobs: Job[];
  currentJob: Job | null;
  summary: JobSummary | null;
  pagination: { count: number; next: string | null; previous: string | null } | null;
  isLoading: boolean;
  error: string | null;
  fetchJobs: (params?: PaginationParams) => Promise<void>;
  loadMoreJobs: () => Promise<void>;
  fetchJob: (id: number) => Promise<Job | null>;
  createJob: (file: File) => Promise<Job | null>;
  deleteJob: (id: number) => Promise<void>;
  cancelJob: (id: number) => Promise<void>;
  fetchSummary: () => Promise<void>;
  refreshCurrentJob: () => Promise<void>;
  clearError: () => void;
}

const JobContext = createContext<JobContextValue | null>(null);

export function JobProvider({ children }: { children: React.ReactNode }) {
  const {
    jobs,
    currentJob,
    summary,
    pagination,
    isLoading,
    error,
    setLoading,
    setError,
    clearError,
  } = useJobStore();

  const fetchJobs = useCallback(async (params: PaginationParams = {}) => {
    setLoading(true);
    try {
      const data = await api.listJobs(params);
      if (params.page && params.page > 1) {
        useJobStore.getState().appendJobs(data.results);
      } else {
        useJobStore.getState().setJobs(data.results, data);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch jobs');
      toast.error(err.message || 'Failed to fetch jobs');
    } finally {
      setLoading(false);
    }
  }, [setLoading, setError]);

  const loadMoreJobs = useCallback(async () => {
    const { pagination } = useJobStore.getState();
    if (pagination?.next && !useJobStore.getState().isLoading) {
      const page = new URL(pagination.next).searchParams.get('page');
      if (page) {
        await fetchJobs({ page: parseInt(page) });
      }
    }
  }, [fetchJobs]);

  const fetchJob = useCallback(async (id: number) => {
    setLoading(true);
    try {
      const job = await api.getJob(id);
      useJobStore.getState().setCurrentJob(job);
      return job;
    } catch (err: any) {
      setError(err.message || 'Failed to fetch job');
      toast.error(err.message || 'Failed to fetch job');
      return null;
    } finally {
      setLoading(false);
    }
  }, [setLoading, setError]);

  const createJob = useCallback(async (file: File) => {
    setLoading(true);
    try {
      const job = await api.createJob(file);
      useJobStore.getState().setJobs([job, ...useJobStore.getState().jobs]);
      toast.success('Job created successfully');
      return job;
    } catch (err: any) {
      setError(err.message || 'Failed to create job');
      toast.error(err.message || 'Failed to create job');
      return null;
    } finally {
      setLoading(false);
    }
  }, [setLoading, setError]);

  const deleteJob = useCallback(async (id: number) => {
    try {
      await api.deleteJob(id);
      useJobStore.getState().removeJob(id);
      toast.success('Completed job deleted');
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete job');
    }
  }, []);

  const cancelJob = useCallback(async (id: number) => {
    try {
      const job = await api.cancelJob(id);
      useJobStore.getState().updateJob(id, job);
      toast.success('Job cancellation requested');
    } catch (err: any) {
      toast.error(err.message || 'Failed to cancel job');
    }
  }, []);

  const fetchSummary = useCallback(async () => {
    try {
      const summary = await api.getSummary();
      useJobStore.getState().setSummary(summary);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  }, []);

  const refreshCurrentJob = useCallback(async () => {
    const { currentJob } = useJobStore.getState();
    if (currentJob) {
      await fetchJob(currentJob.id);
    }
  }, [fetchJob]);

  const value = {
    jobs,
    currentJob,
    summary,
    pagination,
    isLoading,
    error,
    fetchJobs,
    loadMoreJobs,
    fetchJob,
    createJob,
    deleteJob,
    cancelJob,
    fetchSummary,
    refreshCurrentJob,
    clearError,
  };

  return (
    <JobContext.Provider value={value}>
      {children}
    </JobContext.Provider>
  );
}

export function useJob() {
  const context = useContext(JobContext);
  if (!context) {
    throw new Error('useJob must be used within a JobProvider');
  }
  return context;
}
