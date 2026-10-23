import React, { createContext, useContext, useEffect, useCallback, useRef, useState } from 'react';
import { useAuthStore, useNotificationStore, useProgressStore, useJobStore } from '@/store';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';

interface WebSocketContextValue {
  isConnected: boolean;
  lastMessage: any;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  reconnect: () => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((state) => state.accessToken);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const getStores = useCallback(() => {
    return {
      notification: useNotificationStore.getState(),
      progress: useProgressStore.getState(),
      job: useJobStore.getState(),
    };
  }, []);

  const handleMessage = useCallback((message: any) => {
    const { notification, progress, job } = getStores();

    switch (message.type) {
      case 'connection.established':
        console.log('WebSocket connected:', message.message);
        break;

      case 'notification':
        if (message.notification && message.unread_count !== undefined) {
          const n = message.notification;
          notification.setUnreadCount(message.unread_count);
          notification.prependNotifications([
            {
              id: n.id,
              title: n.title,
              message: n.message,
              job_id: n.job_id,
              event_id: n.event_id,
              is_read: n.is_read,
              created_at: n.created_at,
              read_at: null,
            }
          ]);
          toast.success(n.title, { duration: 5000 });
          if (n.title === 'Job Completed' && Number.isInteger(n.job_id)) {
            void api.getJob(n.job_id).then((latestJob) => {
              job.updateJob(n.job_id, {
                status: latestJob.status,
                progress: latestJob.progress,
                error_message: latestJob.error_message,
                completed_at: latestJob.completed_at,
              });
            }).catch((refreshError) => {
              console.error('Failed to refresh completed job state:', refreshError);
            });
          }
        }
        break;

      case 'job_update':
        if (message.data) {
          const data = message.data;
          const progressEvent = {
            id: data.extra?.progress_event_id || Date.now(),
            sequence: data.extra?.sequence || 0,
            event: data.event,
            status: data.status,
            progress: data.progress,
            message: data.message,
            metadata: data.extra?.metadata || {},
            created_at: data.updated_at,
          };
          progress.addProgressEvent(progressEvent);
          job.updateJob(data.job_id, {
            status: data.status,
            progress: data.progress,
            error_message: data.status === 'failed' ? data.message : undefined,
          });
        }
        break;

      case 'pong':
        break;

      case 'error':
        console.warn('WebSocket error:', message.message);
        break;

      default:
        console.log('Unknown message type:', message.type);
    }
  }, [getStores]);

  const connect = useCallback(() => {
    const currentAccessToken = useAuthStore.getState().accessToken;
    if (!currentAccessToken) {
      setError('No access token available');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const ws = new WebSocket(api.getWebSocketUrl('/ws/notifications/'));
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      setError(null);
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        setLastMessage(message);
        handleMessage(message);
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);
      setIsConnected(false);
      if (wsRef.current !== ws) {
        return;
      }
      if (reconnectAttempts.current < 10) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttempts.current++;
          connect();
        }, delay);
      } else {
        setError('Max reconnection attempts reached');
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      setError('WebSocket connection error');
    };
  }, [handleMessage]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      const ws = wsRef.current;
      wsRef.current = null;
      ws.close();
    }
    setIsConnected(false);
  }, []);

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    disconnect();
    setTimeout(() => connect(), 100);
  }, [connect, disconnect]);

  useEffect(() => {
    if (accessToken) {
      connect();
    }
    return () => {
      disconnect();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [accessToken, connect, disconnect]);

  const value = {
    isConnected,
    lastMessage,
    error,
    connect,
    disconnect,
    reconnect,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocketContext() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
}

// Re-export other providers
export { AuthProvider } from './AuthContext';
export { JobProvider } from './JobContext';
export { NotificationProvider } from './NotificationContext';