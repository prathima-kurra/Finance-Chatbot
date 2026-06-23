import { useState, useRef, useEffect } from "react";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from "recharts";
import Login from "./Login";
import Register from "./Register";
import "./App.css";

const COLORS = ["#6366f1","#f59e0b","#10b981","#ef4444","#3b82f6","#ec4899","#14b8a6","#f97316"];

function buildStats(transactions) {
  const categoryTotals = {};
  let totalSpent = 0;
  transactions.forEach(row => {
    const amount = parseFloat(row.amount || row.Amount || 0);
    const category = row.category || row.Category || row.description || row.Description || "Other";
    totalSpent += amount;
    categoryTotals[category] = (categoryTotals[category] || 0) + amount;
  });
  const chartData = Object.entries(categoryTotals)
    .map(([name, value]) => ({ name, value: parseFloat(value.toFixed(2)) }))
    .sort((a, b) => b.value - a.value);
  return { totalSpent, chartData, topCategory: chartData[0] || { name: "N/A", value: 0 } };
}

export default function App() {
  const [page, setPage] = useState("login");
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [email, setEmail] = useState(localStorage.getItem("email") || "");
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState("");
  const [stats, setStats] = useState(null);
  const [chartType, setChartType] = useState("pie");
  const bottomRef = useRef(null);

  useEffect(() => {
    if (token) {
      setPage("app");
      loadHistory();
    }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadHistory() {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/history`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` }
    });
    const data = await res.json();
    if (data.history && data.history.length > 0) {
      setMessages(data.history);
    } else {
      setMessages([{ role: "assistant", text: "Hi! Upload your transactions CSV, then ask me anything about your spending." }]);
    }
  }

  function handleLogin(newToken, newEmail) {
    setToken(newToken);
    setEmail(newEmail);
    setPage("app");
    loadHistory();
  }

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("email");
    setToken("");
    setEmail("");
    setMessages([]);
    setStats(null);
    setPage("login");
  }

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setFileName(file.name);
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${import.meta.env.VITE_API_URL}/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const data = await res.json();
    const s = buildStats(data.allTransactions || data.preview);
    setStats({ ...s, count: data.count });
    setMessages(prev => [...prev, {
      role: "assistant",
      text: `✓ Loaded ${data.count} transactions from ${file.name}. Charts updated! Ask me anything.`
    }]);
  }

  async function handleSend(q) {
    const text = q || question.trim();
    if (!text || loading) return;
    setQuestion("");
    const newMessages = [...messages, { role: "user", text }];
    setMessages(newMessages);
    setLoading(true);
    const res = await fetch(`${import.meta.env.VITE_API_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ question: text, history: newMessages.slice(1) }),
    });
    const data = await res.json();
    setLoading(false);
    setMessages(prev => [...prev, { role: "assistant", text: data.answer }]);
  }

  const suggestions = [
    "Where did I spend most?",
    "What's my total spending?",
    "How can I save money?",
    "Show my top 3 expenses",
  ];

  if (page === "login") return <Login onLogin={handleLogin} onSwitch={() => setPage("register")} />;
  if (page === "register") return <Register onSwitch={() => setPage("login")} />;

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <span className="logo">💰</span>
          <h1>Finance Assistant</h1>
        </div>
        <div className="header-right">
          <span className="user-email">👤 {email}</span>
          <label className="upload-btn">
            📂 {fileName || "Upload CSV"}
            <input type="file" accept=".csv,.txt" onChange={handleUpload} hidden />
          </label>
          <button className="logout-btn" onClick={handleLogout}>Log Out</button>
        </div>
      </header>

      <div className="main">
        <div className="left-panel">
          {stats ? (
            <>
              <div className="cards-row">
                <div className="card">
                  <span className="card-label">Total Spent</span>
                  <span className="card-value">${stats.totalSpent.toFixed(2)}</span>
                </div>
                <div className="card">
                  <span className="card-label">Transactions</span>
                  <span className="card-value">{stats.count}</span>
                </div>
                <div className="card">
                  <span className="card-label">Top Category</span>
                  <span className="card-value card-value--sm">{stats.topCategory.name}</span>
                  <span className="card-sub">${stats.topCategory.value.toFixed(2)}</span>
                </div>
              </div>

              <div className="chart-header">
                <span className="chart-title">Spending Breakdown</span>
                <div className="toggle-row">
                  <button className={`toggle-btn ${chartType === "pie" ? "active" : ""}`} onClick={() => setChartType("pie")}>Pie</button>
                  <button className={`toggle-btn ${chartType === "bar" ? "active" : ""}`} onClick={() => setChartType("bar")}>Bar</button>
                </div>
              </div>

              {chartType === "pie" && (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={stats.chartData} cx="50%" cy="50%" outerRadius={85} dataKey="value"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                      {stats.chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={v => `$${v.toFixed(2)}`} />
                  </PieChart>
                </ResponsiveContainer>
              )}

              {chartType === "bar" && (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={stats.chartData} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `$${v}`} />
                    <Tooltip formatter={v => `$${v.toFixed(2)}`} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {stats.chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}

              <div className="category-list">
                {stats.chartData.map((item, i) => (
                  <div key={i} className="category-row">
                    <span className="cat-dot" style={{ background: COLORS[i % COLORS.length] }} />
                    <span className="cat-name">{item.name}</span>
                    <span className="cat-amount">${item.value.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-panel">
              <span className="empty-icon">📊</span>
              <p>Upload a CSV to see your spending charts here.</p>
            </div>
          )}
        </div>

        <div className="right-panel">
          <div className="chat-window">
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role}`}>
                <span className="bubble-text">{m.text}</span>
              </div>
            ))}
            {loading && (
              <div className="bubble assistant">
                <span className="typing-dots"><span /><span /><span /></span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="suggestions">
            {suggestions.map((s, i) => (
              <button key={i} className="suggestion-chip" onClick={() => handleSend(s)}>{s}</button>
            ))}
          </div>

          <div className="input-row">
            <input
              type="text"
              placeholder="Ask about your spending..."
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSend()}
              disabled={loading}
            />
            <button onClick={() => handleSend()} disabled={loading}>Send</button>
          </div>
        </div>
      </div>
    </div>
  );
}