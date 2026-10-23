import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import { AuthProvider } from '@/contexts/AuthContext';
import { WebSocketProvider } from '@/contexts/WebSocketContext';
import { JobProvider } from '@/contexts/JobContext';
import { NotificationProvider } from '@/contexts/NotificationContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <NotificationProvider>
          <WebSocketProvider>
            <JobProvider>
              <App />
            </JobProvider>
          </WebSocketProvider>
        </NotificationProvider>
      </AuthProvider>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: 'hsl(var(--card))',
            color: 'hsl(var(--card-foreground))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 'var(--radius)',
            padding: '1rem',
            boxShadow: '0 4px 24px -4px hsl(var(--border)), 0 8px 32px -8px hsl(var(--border))',
          },
          success: {
            iconTheme: {
              primary: 'hsl(var(--success))',
              secondary: 'hsl(var(--success-foreground))',
            },
          },
          error: {
            iconTheme: {
              primary: 'hsl(var(--destructive))',
              secondary: 'hsl(var(--destructive-foreground))',
            },
          },
        }}
      />
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 6000,
          style: {
            background: 'hsl(var(--card))',
            color: 'hsl(var(--card-foreground))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 'var(--radius)',
            padding: '1rem',
          },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>
);