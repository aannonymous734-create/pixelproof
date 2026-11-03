import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { getCurrentUser } from "@/services/auth/auth_service";

// The stored profile only says "was signed in". Confirm the cookie session with /me once per page load
// (the API client refreshes an expired access token on the way).
let verified = false;

export default function ProtectedRoute() {
  const { isAuth, LoginUser, LogoutUser } = useAuth();
  const [checking, setChecking] = useState(isAuth && !verified);

  useEffect(() => {
    if (!isAuth || verified) return;
    let cancelled = false;
    getCurrentUser()
      .then((u) => {
        verified = true;
        if (!cancelled) LoginUser(u);
      })
      .catch(() => {
        if (!cancelled) LogoutUser();
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuth]);

  if (!isAuth) {
    verified = false;
    return <Navigate to="/login" replace />;
  }
  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground" role="status">
        Checking session…
      </div>
    );
  }
  return <Outlet />;
}
