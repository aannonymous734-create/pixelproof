/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Laravel auth API (default: "/auth-api", proxied by Vite to Laravel's /api). */
  readonly VITE_AUTH_API?: string;
}
