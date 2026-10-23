import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { ArrowLeft, AlertTriangle } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        <div className="mx-auto mb-6 h-16 w-16 rounded-full bg-muted flex items-center justify-center">
          <AlertTriangle className="h-8 w-8 text-muted-foreground" />
        </div>
        <h1 className="text-5xl font-extrabold tracking-tight text-foreground mb-4">404</h1>
        <h2 className="text-2xl font-bold mb-3">Page not found</h2>
        <p className="text-muted-foreground mb-6">The page you are looking for does not exist. Check the URL or navigate back to the dashboard.</p>
        <Link to="/dashboard">
          <Button className="btn-primary gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  );
}
