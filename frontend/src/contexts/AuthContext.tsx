import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/store';
import type { User } from '@/types';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { username: string; email: string; password: string; password_confirm: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, logout: logoutStore, hydrate } = useAuthStore();
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const userData = await api.me();
      useAuthStore.getState().setUser(userData);
    } catch (err) {
      console.error('Failed to refresh user:', err);
    }
  }, []);

  useEffect(() => {
    hydrate();
    const { accessToken } = useAuthStore.getState();
    if (accessToken && !user) {
      refreshUser().finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [hydrate, refreshUser, user]);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const tokens = await api.login({ email, password });
      const userData = await api.me();
      useAuthStore.getState().setAuth(userData, tokens.access, tokens.refresh);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (data: { username: string; email: string; password: string; password_confirm: string }) => {
    setIsLoading(true);
    try {
      await api.register(data);
      const tokens = await api.login({ email: data.email, password: data.password });
      const userData = await api.me();
      useAuthStore.getState().setAuth(userData, tokens.access, tokens.refresh);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    api.logout();
    logoutStore();
  }, [logoutStore]);

  const value: AuthContextValue = {
    user,
    isLoading,
    isAuthenticated,
    login,
    register,
    logout,
    refreshUser,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}