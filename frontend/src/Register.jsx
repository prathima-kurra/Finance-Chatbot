import { useState } from "react";

export default function Register({ onSwitch }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleRegister() {
    if (!email || !password) return setError("Please fill in all fields");
    setLoading(true);
    setError("");
    const res = await fetch(`${import.meta.env.VITE_API_URL}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    setLoading(false);
    if (data.error) return setError(data.error);
    setSuccess("Account created! Please log in.");
    setTimeout(() => onSwitch(), 1500);
  }

  return (
    <div className="auth-page">
      <div className="auth-box">
        <span className="auth-logo">💰</span>
        <h1>Finance Assistant</h1>
        <p className="auth-sub">Create your account</p>
        {error && <div className="auth-error">{error}</div>}
        {success && <div className="auth-success">{success}</div>}
        <input type="email" placeholder="Email" value={email}
          onChange={e => setEmail(e.target.value)} />
        <input type="password" placeholder="Password (min 6 characters)" value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleRegister()} />
        <button className="auth-btn" onClick={handleRegister} disabled={loading}>
          {loading ? "Creating account..." : "Sign Up"}
        </button>
        <p className="auth-switch">
          Already have an account? <span onClick={onSwitch}>Log in</span>
        </p>
      </div>
    </div>
  );
}