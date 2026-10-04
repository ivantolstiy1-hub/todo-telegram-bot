import React, { useState, useEffect } from 'react';

export default function App() {
  const [tab, setTab] = useState('chat');
  const [messages, setMessages] = useState([
    { role: 'bot', text: '👋 Привет! Я персональный AI-ассистент на базе Google Gemini и Antigravity. Чем я могу помочь?' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [config, setConfig] = useState({ style: 'default', temperature: 0.7, rules: [] });
  const [tasks, setTasks] = useState([]);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newRule, setNewRule] = useState('');

  // Загрузка настроек и задач
  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(data => setConfig(data))
      .catch(console.error);

    fetch('/api/tasks')
      .then(res => res.json())
      .then(data => setTasks(data.tasks || []))
      .catch(console.error);
  }, []);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userText = input.trim();
    setMessages(prev => [...prev, { role: 'user', text: userText }]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText })
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'bot', text: data.reply || 'Ошибка получения ответа.' }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'bot', text: `Ошибка сети: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const updateConfig = async (params) => {
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      });
      const data = await res.json();
      setConfig(data);
    } catch (err) {
      console.error(err);
    }
  };

  const toggleTask = async (id) => {
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle', id })
      });
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (err) {
      console.error(err);
    }
  };

  const addTask = async (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'add', title: newTaskTitle.trim() })
      });
      const data = await res.json();
      setTasks(data.tasks || []);
      setNewTaskTitle('');
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div style={{ background: '#0f172a', minHeight: '100vh', color: '#f8fafc', fontFamily: 'sans-serif' }}>
      {/* Header */}
      <header style={{ padding: '16px', background: 'rgba(15, 23, 42, 0.9)', borderBottom: '1px solid rgba(255,255,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '24px' }}>✨</span>
          <div>
            <h1 style={{ fontSize: '16px', margin: 0 }}>Gemini AI PWA</h1>
            <span style={{ fontSize: '11px', color: '#22c55e' }}>● Online 24/7</span>
          </div>
        </div>
      </header>

      {/* Main Tab Views */}
      <main style={{ padding: '16px', paddingBottom: '80px', maxWidth: '600px', margin: '0 auto' }}>
        {tab === 'chat' && (
          <div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', minHeight: '60vh' }}>
              {messages.map((m, i) => (
                <div key={i} style={{
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  background: m.role === 'user' ? '#2563eb' : 'rgba(30, 41, 59, 0.8)',
                  padding: '12px 16px',
                  borderRadius: '16px',
                  maxWidth: '85%',
                  fontSize: '14px',
                  lineHeight: '1.5'
                }}>
                  {m.text}
                </div>
              ))}
              {loading && <div style={{ color: '#94a3b8', fontSize: '13px' }}>AI думает...</div>}
            </div>

            <form onSubmit={handleSendMessage} style={{ position: 'fixed', bottom: '60px', left: 0, right: 0, padding: '12px 16px', background: '#0f172a', display: 'flex', gap: '8px' }}>
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Задайте вопрос..."
                style={{ flex: 1, padding: '12px', borderRadius: '20px', background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }}
              />
              <button type="submit" style={{ padding: '0 20px', background: '#38bdf8', color: '#000', border: 'none', borderRadius: '20px', fontWeight: 'bold' }}>
                Отправить
              </button>
            </form>
          </div>
        )}

        {tab === 'config' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ background: '#1e293b', padding: '16px', borderRadius: '12px' }}>
              <h3>🎨 Стиль ответов</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '10px' }}>
                {['default', 'concise', 'senior', 'detailed', 'friendly'].map(s => (
                  <button
                    key={s}
                    onClick={() => updateConfig({ action: 'set_style', style: s })}
                    style={{
                      padding: '10px',
                      borderRadius: '8px',
                      border: config.style === s ? '1px solid #38bdf8' : '1px solid rgba(255,255,255,0.1)',
                      background: config.style === s ? 'rgba(56, 189, 248, 0.2)' : 'rgba(15, 23, 42, 0.5)',
                      color: config.style === s ? '#38bdf8' : '#cbd5e1'
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ background: '#1e293b', padding: '16px', borderRadius: '12px' }}>
              <h3>🌡 Температура: {config.temperature}</h3>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={config.temperature}
                onChange={e => setConfig({ ...config, temperature: parseFloat(e.target.value) })}
                onMouseUp={() => updateConfig({ action: 'set_temp', temperature: config.temperature })}
                style={{ width: '100%', marginTop: '10px' }}
              />
            </div>

            <div style={{ background: '#1e293b', padding: '16px', borderRadius: '12px' }}>
              <h3>📋 Правила поведения</h3>
              <ul style={{ listStyle: 'none', padding: 0 }}>
                {(config.rules || []).map((r, idx) => (
                  <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <span>{idx + 1}. {r}</span>
                    <button onClick={() => updateConfig({ action: 'delete_rule', query: idx + 1 })} style={{ background: 'none', border: 'none', color: '#ef4444' }}>✕</button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {tab === 'tasks' && (
          <div>
            <form onSubmit={addTask} style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <input
                value={newTaskTitle}
                onChange={e => setNewTaskTitle(e.target.value)}
                placeholder="Новая задача..."
                style={{ flex: 1, padding: '10px', borderRadius: '8px', background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }}
              />
              <button type="submit" style={{ padding: '0 16px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px' }}>
                Добавить
              </button>
            </form>

            <div>
              {tasks.map(t => (
                <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px', background: '#1e293b', borderRadius: '8px', marginBottom: '8px', opacity: t.done ? 0.5 : 1 }}>
                  <input type="checkbox" checked={t.done} onChange={() => toggleTask(t.id)} />
                  <span style={{ textDecoration: t.done ? 'line-through' : 'none' }}>{t.title}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Bottom Nav */}
      <nav style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: '56px', background: 'rgba(15, 23, 42, 0.95)', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex' }}>
        {['chat', 'config', 'tasks'].map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              color: tab === t ? '#38bdf8' : '#94a3b8',
              fontWeight: tab === t ? 'bold' : 'normal',
              cursor: 'pointer'
            }}
          >
            {t === 'chat' ? '💬 Чат' : (t === 'config' ? '⚙️ Настройки' : '📋 Задачи')}
          </button>
        ))}
      </nav>
    </div>
  );
}
