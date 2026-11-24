import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { User, UserRole } from '../types';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authError?: string | null;
  login: (email: string, pass: string) => Promise<void>;
  register: (email: string, pass: string, name: string, role: UserRole) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const getStoredToken = () => localStorage.getItem('inksight_token') || localStorage.getItem('token');
  const [token, setToken] = useState<string | null>(getStoredToken);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(() => Boolean(getStoredToken()));
  const [authError, setAuthError] = useState<string | null>(null);

  // In-flight deduplication ref to prevent duplicate initialization / side effects under React StrictMode
  const initPromiseRef = useRef<Promise<void> | null>(null);
  const isMountedRef = useRef<boolean>(true);

  const initAuth = (): Promise<void> => {
    // If initialization is already underway, reuse the pending promise
    if (initPromiseRef.current) {
      return initPromiseRef.current;
    }

    setIsLoading(true);
    setAuthError(null);

    const promise = (async () => {
      const existingToken = getStoredToken();
      if (existingToken) {
        try {
          const me = await api.getMe();
          if (isMountedRef.current) {
            setUser(me);
            setToken(existingToken);
            setAuthError(null);
            setIsLoading(false);
          }
          return;
        } catch (err) {
          console.warn('Existing session invalid:', err);
          localStorage.removeItem('inksight_token');
          localStorage.removeItem('token');
          if (isMountedRef.current) {
            setToken(null);
            setUser(null);
          }
        }
      }

      if (isMountedRef.current) {
        setToken(null);
        setUser(null);
        setAuthError(null);
        setIsLoading(false);
      }
    })().finally(() => {
      initPromiseRef.current = null;
    });

    initPromiseRef.current = promise;
    return promise;
  };

  useEffect(() => {
    isMountedRef.current = true;
    initAuth();
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const login = async (email: string, pass: string) => {
    setIsLoading(true);
    setAuthError(null);
    try {
      const res = await api.login(email, pass);
      localStorage.setItem('inksight_token', res.access_token);
      localStorage.setItem('token', res.access_token);
      setToken(res.access_token);
      setUser(res.user);
    } catch (err: any) {
      setAuthError(err?.message || 'Login failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (email: string, pass: string, name: string, role: UserRole) => {
    setIsLoading(true);
    setAuthError(null);
    try {
      await api.register(email, pass, name, role);
      // Auto login after registration
      await login(email, pass);
    } catch (err: any) {
      setAuthError(err?.message || 'Registration failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('inksight_token');
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    setAuthError(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        authError,
        login,
        register,
        logout,
        refreshUser: initAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
