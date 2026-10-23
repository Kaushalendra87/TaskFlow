import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Separator } from '@/components/ui/Separator';
import { User, Shield, Bell, Server, KeyRound } from 'lucide-react';

export function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await refreshUser();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-3xl font-extrabold tracking-tight mb-2">Account Settings</h1>
        <p className="text-muted-foreground">Manage your profile, authentication, and preferences.</p>
      </section>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Profile Card */}
        <Card className="card-elegant">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              Profile
            </CardTitle>
            <CardDescription>Your account details.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center text-primary-foreground font-extrabold text-lg">
                {user?.username?.[0]?.toUpperCase() || 'U'}
              </div>
              <div>
                <p className="font-semibold text-foreground">{user?.username}</p>
                <p className="text-sm text-muted-foreground">{user?.email}</p>
              </div>
            </div>
            <Separator />
            <Button variant="outline" className="w-full" disabled>Update Profile</Button>
          </CardContent>
        </Card>

        {/* Authentication Card */}
        <Card className="card-elegant">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-success" />
              Authentication
            </CardTitle>
            <CardDescription>JWT-based authentication settings.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Access Token</span>
                <Badge variant="outline" className="text-xs">15 min</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Refresh Token</span>
                <Badge variant="outline" className="text-xs">7 days</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Rotation</span>
                <Badge variant="success" className="text-xs">Enabled</Badge>
              </div>
            </div>
            <Button variant="outline" className="w-full" onClick={handleRefresh} loading={isRefreshing}>
              <KeyRound className="mr-2 h-4 w-4" />
              Refresh User Data
            </Button>
          </CardContent>
        </Card>

        {/* System Info Card */}
        <Card className="card-elegant">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" />
              System
            </CardTitle>
            <CardDescription>Backend service status.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">API Base URL</span>
              <span className="font-mono text-xs">http://localhost:8000</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">WebSocket</span>
              <span className="font-mono text-xs">ws://localhost:8000</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Channel Layer</span>
              <Badge variant="outline" className="text-xs">Redis</Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Celery Broker</span>
              <Badge variant="outline" className="text-xs">Redis</Badge>
            </div>
            <Separator />
            <Link to="/dashboard" className="text-sm text-primary hover:underline underline-offset-4">
              Back to Dashboard →
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Notifications Settings */}
      <Card className="card-elegant">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-amber-500" />
            Notifications
          </CardTitle>
          <CardDescription>Notification delivery settings and preferences.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <h4 className="font-semibold text-sm mb-2">Event Types</h4>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>• Job Created</li>
                <li>• Job Completed</li>
                <li>• Job Failed</li>
                <li>• Job Cancelled</li>
                <li>• Job Retrying</li>
              </ul>
            </div>
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <h4 className="font-semibold text-sm mb-2">WebSocket Groups</h4>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>• notifications_user_{"{id}"}</li>
                <li>• job_updates_user_{"{id}"}</li>
                <li>• Per-job updates via job_{"{id}"}</li>
              </ul>
            </div>
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50">
              <h4 className="font-semibold text-sm mb-2">Recovery</h4>
              <p className="text-xs text-muted-foreground">Clients recover missed events via REST API (`after_sequence`) after reconnecting.</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
