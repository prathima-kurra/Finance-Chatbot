import { useState } from "react";

export default function Login({ onLogin, onSwitch }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!email || !password) return setError("Please fill in all fields");
    setLoading(true);
    setError("");
    const res = await fetch(`${import.meta.env.VITE_API_URL}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    setLoading(false);
    if (data.error) return setError(data.error);
    localStorage.setItem("token", data.token);
    localStorage.setItem("email", data.email);
    onLogin(data.token, data.email);
  }

  return (
    <div className="auth-page">
      <div className="auth-box">
        <span className="auth-logo">💰</span>
        <h1>Finance Assistant</h1>
        <p className="auth-sub">Log in to your account</p>
        {error && <div className="auth-error">{error}</div>}
        <input type="email" placeholder="Email" value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleLogin()} />
        <input type="password" placeholder="Password" value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleLogin()} />
        <button className="auth-btn" onClick={handleLogin} disabled={loading}>
          {loading ? "Logging in..." : "Log In"}
        </button>
        <p className="auth-switch">
          Don't have an account? <span onClick={onSwitch}>Sign up</span>
        </p>
      </div>
    </div>
  );
}