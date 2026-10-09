import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { getSession, logoutUser } from '../api/client';

const Ctx = createContext(null);

export function useAuth() {
  return useContext(Ctx) || { session: null, expired: false, setSession: () => {}, logout: async () => {} };
}

// Keeps the signed-in user and an "expired" flag. When the server rejects the session the page that is currently open stays mounted
// (so unsaved edits are not lost) and a sign-in overlay appears on top of it.
export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => getSession());
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const onExpired = () => setExpired(true);
    window.addEventListener('rd-auth-expired', onExpired);
    return () => window.removeEventListener('rd-auth-expired', onExpired);
  }, []);

  const onAuthenticated = useCallback((next) => {
    // A different account signing in over an expired page must not see the previous user's on-screen data.
    const previous = session?.user?.id;
    setSession(next);
    setExpired(false);
    if (previous && next?.user?.id && previous !== next.user.id) window.location.reload();
  }, [session]);

  const logout = useCallback(async () => {
    await logoutUser();
    setSession(null);
    setExpired(false);
    window.location.assign('/dashboard');
  }, []);

  return <Ctx.Provider value={{ session, expired, onAuthenticated, logout }}>{children}</Ctx.Provider>;
}
