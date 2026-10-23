import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useJob } from '@/contexts/JobContext';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { FolderOpen, Trash2 } from 'lucide-react';
import { formatRelativeTime, getStatusColor, cn } from '@/lib/utils';

export function JobsPage() {
  const { jobs, pagination, isLoading, fetchJobs, loadMoreJobs, deleteJob } = useJob();
  const [deletingJobId, setDeletingJobId] = useState<number | null>(null);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  return (
    <section className="space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Task history</p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Your jobs</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Review uploaded files and follow their processing status.
          </p>
        </div>
        <Badge variant="outline">{pagination?.count ?? jobs.length} jobs</Badge>
      </header>

      {isLoading && jobs.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading jobs...</div>
      ) : jobs.length === 0 ? (
        <Card className="border-dashed border-2 border-border/60 bg-muted/30 p-10 text-center">
          <FolderOpen className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
          <p className="font-medium">No jobs yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload a CSV from your dashboard to start processing.
          </p>
          <Link to="/dashboard" className="mt-5 inline-flex">
            <Button>Go to dashboard</Button>
          </Link>
        </Card>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <Card key={job.id} className="p-4 transition-transform hover:-translate-y-0.5">
              <div className="flex items-start justify-between gap-3">
                <Link to={`/jobs/${job.id}`} className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <h2 className="truncate font-semibold">
                        {job.file?.split('/').pop() || 'Uploaded file'}
                      </h2>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Job #{job.id} · Created {formatRelativeTime(job.created_at)}
                      </p>
                    </div>
                    <Badge variant="outline" className={cn('shrink-0', getStatusColor(job.status))}>
                      {job.status}
                    </Badge>
                  </div>
                </Link>
                {job.status === 'completed' && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="shrink-0 text-destructive hover:text-destructive"
                    aria-label={`Delete completed job ${job.id}`}
                    title="Delete completed job"
                    loading={deletingJobId === job.id}
                    onClick={async () => {
                      if (!window.confirm('Delete this completed job and its uploaded CSV? This also removes its job history and notifications.')) {
                        return;
                      }
                      setDeletingJobId(job.id);
                      try {
                        await deleteJob(job.id);
                      } finally {
                        setDeletingJobId(null);
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
              <Link to={`/jobs/${job.id}`} className="mt-4 block">
                <div className="flex items-center gap-3">
                  <div
                    className="h-2 flex-1 overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-valuenow={job.progress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Job ${job.id} progress`}
                  >
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                  <span className="w-12 text-right text-xs tabular-nums text-muted-foreground">
                    {job.progress}%
                  </span>
                </div>
              </Link>
            </Card>
          ))}
        </div>
      )}

      {pagination?.next && (
        <div className="flex justify-center">
          <Button variant="outline" onClick={() => void loadMoreJobs()} loading={isLoading}>
            Load more jobs
          </Button>
        </div>
      )}
    </section>
  );
}
