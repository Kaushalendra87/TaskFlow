import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useJob } from '@/contexts/JobContext';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card, CardContent } from '@/components/ui/Card';
import { FolderOpen } from 'lucide-react';
import { formatRelativeTime, getStatusColor } from '@/lib/utils';
import { cn } from '@/lib/utils';
import toast from 'react-hot-toast';

export function DashboardPage() {
  const { user } = useAuth();
  const { jobs, pagination, isLoading, summary, fetchJobs, loadMoreJobs, fetchSummary, createJob } = useJob();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  useEffect(() => {
    fetchJobs();
    fetchSummary();
  }, [fetchJobs, fetchSummary]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected && (selected.type === 'text/csv' || selected.name.toLowerCase().endsWith('.csv'))) {
      setFile(selected);
    } else {
      toast.error('Please select a CSV file');
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Select a file first');
      return;
    }
    setUploadLoading(true);
    try {
      const job = await createJob(file);
      if (!job) return;
      setFile(null);
      await fetchJobs();
    } finally {
      setUploadLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Hero / Welcome */}
      <section className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-card to-card/50 shadow-elegant p-8 md:p-12">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_20%,_hsl(var(--primary)/0.1)_0%,_transparent_70%)]" />
        <div className="relative z-10 max-w-2xl">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-foreground mb-4 leading-tight">
            Welcome, {user?.username || 'User'}.
          </h1>
          <p className="text-lg text-muted-foreground mb-6">
            Submit a CSV file for asynchronous processing. Track live progress via WebSocket, recover missed events through persistent history, and receive notifications in real time.
          </p>
          <div className="flex items-center gap-4">
            <label htmlFor="csv-upload" className="cursor-pointer">
              <input
                id="csv-upload"
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                className="hidden"
              />
              <Button asChild variant="outline" size="lg">
                <span>Choose CSV file</span>
              </Button>
            </label>
            {file ? (
              <>
                <span className="text-sm text-muted-foreground">{file.name}</span>
                <Button onClick={handleUpload} loading={uploadLoading} variant="success" size="lg">
                  Submit Job
                </Button>
              </>
            ) : (
              <span className="text-sm text-muted-foreground">Select a CSV file to begin.</span>
            )}
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="grid gap-4 md:grid-cols-4 lg:grid-cols-7">
        {[
          { label: 'Total', value: summary?.total_jobs || 0, color: 'bg-primary/10 text-primary' },
          { label: 'Pending', value: summary?.pending_jobs || 0, color: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' },
          { label: 'Processing', value: summary?.processing_jobs || 0, color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
          { label: 'Retrying', value: summary?.retrying_jobs || 0, color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
          { label: 'Completed', value: summary?.completed_jobs || 0, color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
          { label: 'Failed', value: summary?.failed_jobs || 0, color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' },
          { label: 'Cancelled', value: summary?.cancelled_jobs || 0, color: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' },
        ].map((stat) => (
          <Card key={stat.label} className="card-elegant p-5 hover:-translate-y-0.5 transition-transform duration-300">
            <CardContent className="p-0 space-y-1">
              <p className="text-xs uppercase tracking-wider text-muted-foreground font-medium">{stat.label}</p>
              <p className="text-3xl font-extrabold text-foreground">{stat.value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      {/* Job List */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-extrabold tracking-tight">Your Jobs</h2>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">{jobs.length} results</Badge>
            {pagination?.count && pagination.count > 0 && (
              <span className="text-xs text-muted-foreground">Page {pagination?.next ? '...' : '1'} of ...</span>
            )}
          </div>
        </div>

        {isLoading && jobs.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">Loading jobs...</div>
        ) : jobs.length === 0 ? (
          <Card className="p-8 text-center border-dashed border-2 border-border/60 bg-muted/30">
            <FolderOpen className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No jobs yet. Upload a CSV file to begin.</p>
          </Card>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link key={job.id} to={`/jobs/${job.id}`} className="block">
                <Card className="card-elegant p-4 hover:-translate-y-0.5 transition-transform duration-300">
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold truncate">{job.file?.split('/').pop() || 'File'}</h3>
                        <Badge variant="outline" className={cn('text-xs', getStatusColor(job.status))}>{job.status}</Badge>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <span>Created: {formatRelativeTime(job.created_at)}</span>
                        <span>Progress: {job.progress}%</span>
                        {job.retry_count > 0 && <span>Retries: {job.retry_count}</span>}
                        <span>ID: {job.id}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {job.cancel_requested && (
                        <Badge variant="outline" className="text-xs bg-amber-100 text-amber-700">Cancel requested</Badge>
                      )}
                      <Button variant="ghost" size="sm" onClick={(e) => {
                        e.preventDefault();
                        navigate(`/jobs/${job.id}`);
                      }}>
                        View
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 w-full h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}

        {pagination?.next && (
          <div className="mt-4 flex justify-center">
            <Button variant="outline" onClick={loadMoreJobs}>Load More</Button>
          </div>
        )}
      </section>
    </div>
  );
}
