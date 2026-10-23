import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import { ArrowRight } from 'lucide-react';
import toast from 'react-hot-toast';

export function RegisterPage() {
  const [form, setForm] = useState({ username: '', email: '', password: '', password_confirm: '' });
  const [isLoading, setIsLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== form.password_confirm) {
      toast.error('Passwords do not match');
      return;
    }
    setIsLoading(true);
    try {
      await register(form);
      navigate('/dashboard');
      toast.success('Account created');
    } catch (err: any) {
      toast.error(err.message || 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex">
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-primary/10 via-background to-background">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,_hsl(var(--primary)/0.08)_0%,_transparent_70%)]" />
        <div className="relative z-10 flex flex-col justify-center px-16 text-foreground">
          <h2 className="text-5xl font-extrabold tracking-tight leading-[1.1] mb-6 text-gradient">
            Process data at scale, in real time.
          </h2>
          <p className="text-lg text-muted-foreground leading-relaxed max-w-md">
            Upload CSV files, submit asynchronous processing jobs, and watch progress unfold live. Recover missed events with persistent sequence-based history.
          </p>
        </div>
      </div>
      <div className="flex w-full lg:w-1/2 items-center justify-center px-6 lg:px-16">
        <div className="w-full max-w-md">
          <h1 className="text-3xl font-extrabold tracking-tight text-foreground">Create account</h1>
          <p className="text-muted-foreground mt-2">Start processing with TaskFlow.</p>
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input id="username" placeholder="Enter username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" placeholder="you@example.com" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" placeholder="Enter password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password_confirm">Confirm Password</Label>
              <Input id="password_confirm" type="password" placeholder="Confirm password" value={form.password_confirm} onChange={e => setForm({ ...form, password_confirm: e.target.value })} required />
            </div>
            <Button type="submit" className="w-full btn-primary h-11" loading={isLoading}>
              {isLoading ? 'Creating account...' : 'Create account'}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="text-primary font-medium hover:underline underline-offset-4">Sign in</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
