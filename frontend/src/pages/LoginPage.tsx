import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import { Badge } from '@/components/ui/Badge';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard');
      toast.success('Welcome back');
    } catch (err: any) {
      toast.error(err.message || 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left decorative panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-primary/10 via-background to-background">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,_hsl(var(--primary)/0.08)_0%,_transparent_70%)]" />
        <div className="relative z-10 flex flex-col justify-center px-16 text-foreground">
          <Badge variant="outline" className="w-fit mb-6 text-xs tracking-widest uppercase font-medium text-muted-foreground">
            TaskFlow Platform
          </Badge>
          <h2 className="text-5xl font-extrabold tracking-tight leading-[1.1] mb-6 text-gradient">
            Process data at<br />scale, in real time.
          </h2>
          <p className="text-lg text-muted-foreground leading-relaxed max-w-md">
            Upload CSV files, submit asynchronous processing jobs, and watch progress unfold live. Recover missed events with persistent sequence-based history.
          </p>
          <div className="mt-8 flex gap-8">
            <div>
              <p className="text-3xl font-bold text-foreground">72</p>
              <p className="text-sm text-muted-foreground mt-1">Tests passing</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-foreground">8</p>
              <p className="text-sm text-muted-foreground mt-1">Migrations</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-foreground">3</p>
              <p className="text-sm text-muted-foreground mt-1">Apps</p>
            </div>
          </div>
        </div>
      </div>

      {/* Right form */}
      <div className="flex w-full lg:w-1/2 items-center justify-center px-6 lg:px-16">
        <div className="w-full max-w-md">
          <div className="mb-8">
            <h1 className="text-3xl font-extrabold tracking-tight text-foreground">Welcome back</h1>
            <p className="text-muted-foreground mt-2">Sign in to manage your jobs and notifications.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            <Button type="submit" className="w-full btn-primary h-11" loading={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign in'}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </form>

          <div className="mt-8 text-center">
            <p className="text-sm text-muted-foreground">
              Don't have an account?{' '}
              <a href="/register" className="text-primary font-medium hover:underline underline-offset-4">Create one</a>
            </p>
          </div>

          <div className="mt-12 flex items-center gap-4 text-xs text-muted-foreground">
            <ShieldCheck className="h-4 w-4" />
            <span>JWT authentication · Secure WebSocket connections</span>
          </div>
        </div>
      </div>
    </div>
  );
}
