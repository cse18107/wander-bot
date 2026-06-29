import { useState } from "react";
import { authRequest } from "./api";

export default function Auth({ onAuthed }: { onAuthed: (token: string, email: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [homeCity, setHomeCity] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!email || !password || busy) return;
    setBusy(true); setError("");
    try {
      const r = await authRequest(mode, email, password, mode === "register" ? homeCity : undefined);
      localStorage.setItem("va-token", r.token);
      localStorage.setItem("va-email", r.email);
      onAuthed(r.token, r.email);
    } catch (e: any) {
      setError(e.message || "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="brand big"><span className="material-symbols-outlined brand-ic">rocket_launch</span> <span>Roam</span></div>
        <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
        <p className="muted small">Your trips are private and saved to your account.</p>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
        <input type="password" placeholder="Password (min 6 chars)" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
        {mode === "register" && <input placeholder="Home city / nearest airport (e.g. Kolkata)" value={homeCity} onChange={(e) => setHomeCity(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />}
        {error && <div className="auth-error">{error}</div>}
        <button onClick={submit} disabled={busy}>{busy ? "…" : mode === "login" ? "Log in" : "Sign up"}</button>
        <div className="auth-switch">
          {mode === "login" ? "New here?" : "Already have an account?"}
          <button className="link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
            {mode === "login" ? "Create account" : "Log in"}
          </button>
        </div>
      </div>
    </div>
  );
}
