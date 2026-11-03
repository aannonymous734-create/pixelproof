import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { motion, useReducedMotion } from "motion/react";
import { Eye, EyeOff, Fingerprint, Loader2, LogIn, ScanSearch, ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { queueTour } from "@/components/tour/Tour";
import { useAuth } from "@/contexts/AuthContext";

const EMAIL_RE = /^\S+@\S+\.\S+$/;

const FEATURES = [
  { icon: Fingerprint, title: "Signed origin", body: "Every patch is checked against its Ed25519 signature, pixel by pixel." },
  { icon: ScanSearch, title: "Content forensics", body: "Explainable features and a forensic CNN flag post-capture manipulation." },
  { icon: ScrollText, title: "Tamper-evident log", body: "Each decision is hash-chained, so rewriting history is detected." },
];

// Laravel answers with {error}, {message} or {message, errors: {field: [..]}}; show one readable sentence.
function errorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    if (!err.response) return "Cannot reach the auth server. Is the Laravel backend running?";
    const d = err.response.data as { error?: string; message?: string; errors?: Record<string, string[]> } | undefined;
    const firstField = d?.errors ? Object.values(d.errors)[0]?.[0] : undefined;
    if (err.response.status === 401) return "Invalid email or password.";
    if (err.response.status === 429) return "Too many attempts. Wait a minute and try again.";
    return firstField ?? d?.error ?? d?.message ?? "Something went wrong. Please try again.";
  }
  return "Something went wrong. Please try again.";
}

export function Login() {
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});

  const emailId = useId();
  const passwordId = useId();

  const emailError = touched.email && !EMAIL_RE.test(email) ? "Enter a valid email address" : null;
  const passwordError = touched.password && password.length < 6 ? "Password must be at least 6 characters" : null;
  const valid = EMAIL_RE.test(email) && password.length >= 6;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched({ email: true, password: true });
    setError(null);
    if (!valid || isLoading) return;
    try {
      await login({ email, password });
      queueTour(); // every sign-in opens the dashboard with the guided tour
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const inputClass = (bad: boolean) =>
    cn(
      "h-11 w-full rounded-lg border bg-white/[0.03] px-3.5 text-sm text-foreground placeholder:text-muted-foreground/60",
      "transition-colors focus:outline-none focus:ring-2",
      bad ? "border-verdict-bad/60 focus:ring-verdict-bad/40" : "border-white/10 hover:border-white/20 focus:ring-primary/40",
    );

  const rise = (i: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.55, delay: 0.07 * i, ease: [0.16, 1, 0.3, 1] as const },
        };

  return (
    <div className="relative grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="bg-grid absolute inset-x-0 top-0 h-[640px]" />
        <div className="absolute -top-40 left-1/2 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-primary/[0.12] blur-[120px]" />
        <div className="absolute right-[-10%] top-[30%] h-[420px] w-[520px] rounded-full bg-accent/[0.08] blur-[130px]" />
      </div>

      {/* product story (desktop) */}
      <section className="relative hidden flex-col justify-between border-r border-white/[0.06] p-12 lg:flex xl:p-16">
        <motion.div {...rise(0)} className="flex items-center gap-2.5">
          <Logo />
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">PixelProof</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">ground station</div>
          </div>
        </motion.div>

        <div className="max-w-lg">
          <motion.h2 {...rise(1)} className="text-gradient text-balance text-4xl font-semibold leading-[1.08] tracking-tight xl:text-5xl">
            Prove where every pixel came from.
          </motion.h2>
          <motion.p {...rise(2)} className="mt-4 text-base leading-relaxed text-muted-foreground">
            Verify satellite image patches end to end: who signed them, whether the pixels changed, and what the
            ground station decided.
          </motion.p>
          <ul className="mt-10 space-y-5">
            {FEATURES.map(({ icon: Icon, title, body }, i) => (
              <motion.li key={title} {...rise(3 + i)} className="flex gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-primary">
                  <Icon size={18} aria-hidden />
                </span>
                <div>
                  <div className="text-sm font-medium">{title}</div>
                  <div className="mt-0.5 text-sm text-muted-foreground">{body}</div>
                </div>
              </motion.li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-muted-foreground">TSYP14 Track 3 · “Trust the Pixel”</p>
      </section>

      {/* sign-in form */}
      <section className="flex items-center justify-center px-4 py-12 sm:px-8">
        <motion.div {...rise(1)} className="w-full max-w-[400px]">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <span className="lg:hidden">
              <Logo size={44} />
            </span>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight lg:mt-0">Sign in to PixelProof</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">Welcome back. Enter your details to open the dashboard.</p>
          </div>

          <Card spotlight={false} className="p-6">
            {error && (
              <div
                role="alert"
                className="mb-4 rounded-lg border border-verdict-bad/30 bg-verdict-bad/10 px-3 py-2.5 text-sm text-foreground"
              >
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              <div>
                <label htmlFor={emailId} className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Email
                </label>
                <input
                  id={emailId}
                  type="email"
                  autoComplete="email"
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onBlur={() => setTouched((t) => ({ ...t, email: true }))}
                  placeholder="you@example.com"
                  aria-invalid={!!emailError}
                  aria-describedby={emailError ? `${emailId}-err` : undefined}
                  className={inputClass(!!emailError)}
                />
                {emailError && (
                  <p id={`${emailId}-err`} className="mt-1.5 text-xs text-verdict-bad">
                    {emailError}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor={passwordId} className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Password
                </label>
                <div className="relative">
                  <input
                    id={passwordId}
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onBlur={() => setTouched((t) => ({ ...t, password: true }))}
                    placeholder="••••••••"
                    aria-invalid={!!passwordError}
                    aria-describedby={passwordError ? `${passwordId}-err` : undefined}
                    className={cn(inputClass(!!passwordError), "pr-11")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-2 text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {passwordError && (
                  <p id={`${passwordId}-err`} className="mt-1.5 text-xs text-verdict-bad">
                    {passwordError}
                  </p>
                )}
              </div>

              <Button type="submit" variant="accent" className="h-11 w-full" disabled={isLoading}>
                {isLoading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <LogIn size={16} aria-hidden />}
                {isLoading ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </Card>

          <p className="mt-6 text-center text-xs text-muted-foreground lg:text-left">
            Access is restricted to authorised operators.
          </p>
        </motion.div>
      </section>
    </div>
  );
}
