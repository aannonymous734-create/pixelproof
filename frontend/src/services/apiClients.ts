import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { store } from "@/AuthStore/store";
import { LogoutUser } from "@/AuthStore/slice";

// Laravel auth API. In dev, Vite proxies /auth-api/* to Laravel's /api/* (see vite.config.ts). The built app is
// served by FastAPI on :8000, so it calls Laravel on :8001 of the same host (same site, so the httpOnly JWT
// cookies are sent; Laravel's CORS allows these origins). Override either with VITE_AUTH_API.
export const AUTH_API_BASE =
  import.meta.env.VITE_AUTH_API ??
  (import.meta.env.DEV ? "/auth-api" : `${window.location.protocol}//${window.location.hostname}:8001/api`);

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

const api = axios.create({
  baseURL: AUTH_API_BASE,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
  withCredentials: true,
});

// One refresh at a time: parallel 401s all wait on the same request.
let refreshing: Promise<unknown> | null = null;

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined;
    const url = original?.url ?? "";
    const isAuthCall = url.includes("/auth/login") || url.includes("/auth/register") || url.includes("/auth/refresh");

    if (error.response?.status === 401 && original && !original._retry && !isAuthCall) {
      original._retry = true;
      try {
        refreshing ??= api.post("/auth/refresh").finally(() => {
          refreshing = null;
        });
        await refreshing;
        return api(original);
      } catch (refreshError) {
        store.dispatch(LogoutUser());
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);

export default api;
