import React, { createContext, useContext, useCallback, useEffect } from 'react';
import { api } from '@/lib/api';
import { useAuthStore, useNotificationStore } from '@/store';
import type { Notification } from '@/types';
import toast from 'react-hot-toast';

interface NotificationContextValue {
  notifications: Notification[];
  unreadCount: number;
  pagination: { count: number; next: string | null; previous: string | null } | null;
  isLoading: boolean;
  fetchNotifications: (params?: { unread?: boolean; page?: number; page_size?: number }) => Promise<void>;
  loadMoreNotifications: () => Promise<void>;
  markAsRead: (id: number) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  clearError: () => void;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const {
    notifications,
    unreadCount,
    pagination,
    isLoading,
    setUnreadCount,
    setLoading,
  } = useNotificationStore();

  const fetchNotifications = useCallback(async (params: { unread?: boolean; page?: number; page_size?: number } = {}) => {
    setLoading(true);
    try {
      const data = await api.listNotifications(params);
      useNotificationStore.getState().setNotifications(data.results, data);
      setUnreadCount(data.results.filter(n => !n.is_read).length);
    } catch (err: any) {
      console.error('Failed to fetch notifications:', err);
    } finally {
      setLoading(false);
    }
  }, [setLoading]);

  const loadMoreNotifications = useCallback(async () => {
    const { pagination } = useNotificationStore.getState();
    if (pagination?.next && !useNotificationStore.getState().isLoading) {
      const page = new URL(pagination.next).searchParams.get('page');
      if (page) {
        await fetchNotifications({ page: parseInt(page) });
      }
    }
  }, [fetchNotifications]);

  const markAsRead = useCallback(async (id: number) => {
    try {
      const updatedNotification = await api.markNotificationRead(id);
      const store = useNotificationStore.getState();
      const wasUnread = store.notifications.some(
        (notification) => notification.id === id && !notification.is_read
      );
      store.updateNotification(id, {
        is_read: updatedNotification.is_read,
        read_at: updatedNotification.read_at,
      });
      if (wasUnread) {
        useNotificationStore.getState().decrementUnreadCount();
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to mark as read');
    }
  }, []);

  const markAllAsRead = useCallback(async () => {
    try {
      await api.markAllNotificationsRead();
      useNotificationStore.getState().setNotifications(
        useNotificationStore.getState().notifications.map(n => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      useNotificationStore.getState().setUnreadCount(0);
      toast.success('All notifications marked as read');
    } catch (err: any) {
      toast.error(err.message || 'Failed to mark all as read');
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      void fetchNotifications();
    }
  }, [fetchNotifications, isAuthenticated]);

  const value = {
    notifications,
    unreadCount,
    pagination,
    isLoading,
    fetchNotifications,
    loadMoreNotifications,
    markAsRead,
    markAllAsRead,
    clearError: () => {},
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotification() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotification must be used within a NotificationProvider');
  }
  return context;
}
