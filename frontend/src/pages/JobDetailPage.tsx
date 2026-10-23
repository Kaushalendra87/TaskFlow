import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useJob } from '@/contexts/JobContext';
import { useWebSocketContext } from '@/contexts/WebSocketContext';
import { useJobStore } from '@/store';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Progress } from '@/components/ui/Progress';
import { ArrowLeft, Download, AlertTriangle, XCircle } from 'lucide-react';
import { cn, formatRelativeTime, getStatusColor, getEventColor } from '@/lib/utils';
import type { JobProgressEvent } from '@/types';
import toast from 'react-hot-toast';

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const storedJob = useJobStore((state) => state.currentJob);
  const job = storedJob?.id === jobId ? storedJob : null;
  const { fetchJob: loadJob } = useJob();
  const { lastMessage } = useWebSocketContext();
  const [progressEvents, setProgressEvents] = useState<JobProgressEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);

  const fetchJob = useCallback(async () => {
    if (!id) return;
    try {
      const jobData = await loadJob(Number(id));
      setError(jobData ? null : 'Failed to load job');
    } catch (err: any) {
      setError(err.message || 'Failed to load job');
    } finally {
      setIsLoading(false);
    }
  }, [id, loadJob]);

  const fetchProgressHistory = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api.getJobProgressHistory(parseInt(id));
      setProgressEvents((current) => {
        const knownSequences = new Set(data.events.map((event) => event.sequence));
        return [...data.events, ...current.filter((event) => !knownSequences.has(event.sequence))]
          .sort((left, right) => left.sequence - right.sequence);
      });
    } catch (err) {
      console.error('Failed to fetch progress history:', err);
    }
  }, [id]);

  useEffect(() => {
    const data = lastMessage?.type === 'job_update' ? lastMessage.data : null;
    if (!data || data.job_id !== jobId || !data.extra?.sequence) return;

    const liveEvent: JobProgressEvent = {
      id: data.extra.progress_event_id ?? Date.now(),
      sequence: data.extra.sequence,
      event: data.event,
      status: data.status,
      progress: data.progress,
      message: data.message,
      metadata: data.extra.metadata ?? {},
      created_at: data.updated_at ?? new Date().toISOString(),
    };

    setProgressEvents((current) => {
      if (current.some((event) => event.sequence === liveEvent.sequence)) return current;
      return [...current, liveEvent].sort((left, right) => left.sequence - right.sequence);
    });
  }, [jobId, lastMessage]);

  useEffect(() => {
    fetchJob();
    fetchProgressHistory();
  }, [fetchJob, fetchProgressHistory]);

  const handleCancel = async () => {
    if (!id) return;
    setCancelLoading(true);
    try {
      await api.cancelJob(parseInt(id));
      toast.success('Cancellation requested');
      fetchJob();
    } catch (err: any) {
      toast.error(err.message || 'Failed to cancel job');
    } finally {
      setCancelLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!job) return;
    setDownloadLoading(true);
    try {
      await api.downloadJobFile(job.file);
    } catch (err: any) {
      toast.error(err.message || 'Failed to download file');
    } finally {
      setDownloadLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center flex-col gap-4">
        <AlertTriangle className="h-12 w-12 text-muted-foreground" />
        <h2 className="text-2xl font-bold">Job not found</h2>
        <p className="text-muted-foreground">The requested job could not be loaded or does not belong to you.</p>
        <Link to="/dashboard">
          <Button>Back to Dashboard</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <Link to="/dashboard">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={`text-xs ${getStatusColor(job.status)}`}>
            {job.status.toUpperCase()}
          </Badge>
          <span className="text-xs text-muted-foreground">ID: {job.id}</span>
        </div>
      </div>

      {/* Job Overview Card */}
      <Card className="card-elegant overflow-hidden">
        <CardHeader className="bg-gradient-to-r from-background via-card to-background/50">
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-2xl font-extrabold tracking-tight mb-2">
                Job Details
              </CardTitle>
              <p className="text-sm text-muted-foreground truncate max-w-md">{job.file.split('/').pop()}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={handleDownload} loading={downloadLoading}>
                <Download className="h-4 w-4" />
                Download
              </Button>
              {job.status === 'pending' || job.status === 'processing' || job.status === 'retrying' ? (
                <Button variant="destructive" size="sm" onClick={handleCancel} loading={cancelLoading}>
                  <XCircle className="mr-2 h-4 w-4" />
                  Cancel
                </Button>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-6">
          {/* Progress */}
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Progress</span>
              <span className="font-extrabold text-xl text-foreground">{job.progress}%</span>
            </div>
            <Progress value={job.progress} className="h-3" />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Retry count: {job.retry_count}</span>
              <span>Status: <span className="font-medium text-foreground">{job.status}</span></span>
            </div>
          </div>

          {/* Metadata */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Created</p>
              <p className="text-sm font-medium">{formatRelativeTime(job.created_at)}</p>
            </div>
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Status</p>
              <p className="text-sm font-medium">{job.status}</p>
            </div>
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Retries</p>
              <p className="text-sm font-medium">{job.retry_count}</p>
            </div>
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Completed</p>
              <p className="text-sm font-medium">{job.completed_at ? formatRelativeTime(job.completed_at) : 'Not yet'}</p>
            </div>
          </div>

          {/* Error */}
          {job.error_message && (
            <div className="p-4 rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30">
              <p className="text-sm font-medium text-red-700 dark:text-red-400 mb-1">Error</p>
              <p className="text-sm text-red-600 dark:text-red-300">{job.error_message}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Progress Events Timeline */}
      <Card className="card-elegant">
        <CardHeader>
          <CardTitle>Progress Timeline</CardTitle>
          <p className="text-sm text-muted-foreground mt-1">Sequence-based event history with persistent recovery.</p>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {progressEvents.map((event) => (
              <div key={event.sequence} className="flex items-start gap-4 p-3 rounded-lg bg-muted/30 border border-border/40 hover:bg-muted/50 transition-colors">
                <div className={cn('flex-shrink-0 w-2 h-2 rounded-full mt-2', getEventColor(event.event))} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <Badge variant="outline" className={cn('text-xs', getEventColor(event.event))}>
                      {event.event}
                    </Badge>
                    <span className="text-xs font-mono text-muted-foreground">#{event.sequence}</span>
                  </div>
                  <p className="text-sm font-medium text-foreground">{event.message}</p>
                  <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                    <span>Progress: <strong className="text-foreground">{event.progress}%</strong></span>
                    <span>Status: <strong className="text-foreground">{event.status}</strong></span>
                    <span>{formatRelativeTime(event.created_at)}</span>
                  </div>
                  {event.metadata && Object.keys(event.metadata).length > 0 && (
                    <pre className="mt-2 text-xs bg-background border border-border rounded px-2 py-1 overflow-x-auto font-mono">
                      {JSON.stringify(event.metadata)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
            {progressEvents.length === 0 && (
              <div className="py-8 text-center text-sm text-muted-foreground">No progress events yet.</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
