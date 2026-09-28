import { useCallback, useEffect, useState } from 'react';

const API = import.meta.env.VITE_API_BASE || '/api/v1';

export default function App() {
  const [token, setToken] = useState('');
  const [user, setUser] = useState(null);
  const [mode, setMode] = useState('login');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [documents, setDocuments] = useState([]);
  const [users, setUsers] = useState([]);
  const [file, setFile] = useState(null);
  const [tagInput, setTagInput] = useState('');
  const [documentTagFilter, setDocumentTagFilter] = useState('');
  const [queryTag, setQueryTag] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [history, setHistory] = useState([]);
  const [adminHistory, setAdminHistory] = useState(null);
  const [adminAudit, setAdminAudit] = useState(null);
  const [servicesReady, setServicesReady] = useState(null);
  const [shareKey, setShareKey] = useState(null);
  const [shareManager, setShareManager] = useState(null);
  const [redeemKey, setRedeemKey] = useState('');

  const callApi = useCallback(async (path, options = {}) => {
    const headers = { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const response = await fetch(`${API}${path}`, { ...options, headers });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${response.status})`);
    }
    return response.status === 204 ? null : response.json();
  }, [token]);

  const loadWorkspace = useCallback(async () => {
    const [profile, files, savedHistory] = await Promise.all([callApi('/auth/me'), callApi('/documents'), callApi('/rag/history')]);
    setUser(profile);
    setDocuments(files);
    setHistory(savedHistory);
    const accounts = profile.role?.name?.toLowerCase() === "admin" ? await callApi("/auth/users") : [];
    setUsers(accounts);
  }, [callApi]);

  useEffect(() => {
    if (!token) return;
    loadWorkspace().catch((e) => { setError(e.message); setToken(''); setUser(null); setDocuments([]); setUsers([]); setHistory([]); });
  }, [token, loadWorkspace]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    const checkServices = async () => {
      try {
        const base = API.replace(/\/api\/v1\/?$/, '');
        const response = await fetch(`${base}/health/ready`);
        const result = await response.json();
        if (active) setServicesReady(response.ok && result.status === 'healthy');
      } catch {
        if (active) setServicesReady(false);
      }
    };
    checkServices();
    const timer = setInterval(checkServices, 30000);
    return () => { active = false; clearInterval(timer); };
  }, [token]);

  async function submitAuth(event) {
    event.preventDefault(); setBusy(true); setError('');
    const data = new FormData(event.currentTarget);
    try {
      if (mode === 'register') {
        await callApi('/auth/register', { method: 'POST', body: JSON.stringify({
          username: data.get('username'), email: data.get('email'), password: data.get('password'),
        }) });
      }
      const form = new URLSearchParams({ username: data.get('username'), password: data.get('password') });
      const result = await fetch(`${API}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form });
      const body = await result.json();
      if (!result.ok) throw new Error(body.detail || 'Sign in failed');
      setToken(body.access_token); setNotice('');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function upload(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!file) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const body = new FormData(); body.append('file', file); body.append('tags', tagInput);
      const added = await callApi('/documents', { method: 'POST', body });
      setDocuments((current) => [added, ...current]); form.reset(); setFile(null); setTagInput("");
      setNotice(`Indexed ${added.original_filename} into ${added.chunk_count} searchable sections.`);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function ask(event) {
    event.preventDefault(); if (question.trim().length < 3) return;
    setBusy(true); setError(''); setAnswer(null);
    try { const result = await callApi('/rag/query', { method: 'POST', body: JSON.stringify({ question, tag: queryTag || null }) }); setAnswer(result); setHistory(await callApi('/rag/history')); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function createShare(document) {
    setError("");
    try {
      const created = await callApi(`/documents/${document.id}/shares`, { method: "POST" });
      setShareKey({ ...created, filename: document.original_filename });
    } catch (e) { setError(e.message); }
  }

  async function showShares(document) {
    setError("");
    try {
      const result = await callApi(`/documents/${document.id}/shares`);
      setShareManager({ document, shares: result.shares });
    } catch (e) { setError(e.message); }
  }

  async function revokeShare(shareId) {
    if (!shareManager) return;
    setError("");
    try {
      await callApi(`/documents/${shareManager.document.id}/shares/${shareId}`, { method: "DELETE" });
      setShareManager((current) => current ? {
        ...current,
        shares: current.shares.map((share) => share.share_id === shareId ? { ...share, revoked_at: new Date().toISOString() } : share),
      } : current);
      await loadWorkspace();
      setNotice("Document access revoked.");
    } catch (e) { setError(e.message); }
  }

  async function redeemShare(event) {
    event.preventDefault();
    setError("");
    try {
      const result = await callApi("/shares/redeem", {
        method: "POST", body: JSON.stringify({ token: redeemKey.trim() }),
      });
      setRedeemKey("");
      await loadWorkspace();
      setNotice(`${result.filename} is now available to your account.`);
    } catch (e) { setError(e.message); }
  }
  async function rateAnswer(rating) {
    if (!answer?.history_id) return;
    setError("");
    try {
      const result = await callApi(`/rag/history/${answer.history_id}/feedback`, {
        method: "PUT", body: JSON.stringify({ rating }),
      });
      setAnswer((current) => current ? { ...current, feedback_rating: result.rating } : current);
      setHistory((current) => current.map((item) => item.id === answer.history_id ? { ...item, feedback_rating: result.rating } : item));
      setNotice("Thanks, your feedback was saved.");
    } catch (e) { setError(e.message); }
  }
  async function removeDocument(document) {
    setError('');
    try {
      await callApi(`/documents/${document.id}`, { method: 'DELETE' });
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setNotice(`Removed ${document.original_filename}.`);
    } catch (e) { setError(e.message); }
  }

  async function clearHistory() {
    setError("");
    try {
      await callApi("/rag/history", { method: "DELETE" });
      setHistory([]); setAnswer(null);
      setNotice("Question history cleared.");
    } catch (e) { setError(e.message); }
  }

  function revisitHistory(item) {
    setQuestion(item.question);
    setAnswer({ answer: item.answer, sources: item.sources, history_id: item.id, feedback_rating: item.feedback_rating });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function changeUserRole(account, role) {
    setError("");
    try {
      const updated = await callApi(`/auth/users/${account.id}/role`, {
        method: "PATCH", body: JSON.stringify({ role }),
      });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (account.id === user.id) setUser(updated);
      setNotice(`Updated ${account.username}'s role to ${updated.role.name}.`);
    } catch (e) { setError(e.message); }
  }

  async function viewAccountHistory(account) {
    setError("");
    try {
      const entries = await callApi(`/auth/users/${account.id}/history`);
      setAdminHistory({ username: account.username, entries });
    } catch (e) { setError(e.message); }
  }

  async function viewAuditHistory() {
    setError("");
    try { setAdminAudit(await callApi("/auth/audit?limit=100")); }
    catch (e) { setError(e.message); }
  }
  async function changeUserStatus(account) {
    setError("");
    try {
      const updated = await callApi(`/auth/users/${account.id}/active`, {
        method: "PATCH", body: JSON.stringify({ is_active: !account.is_active }),
      });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${account.username}'s account is now ${updated.is_active ? "active" : "inactive"}.`);
    } catch (e) { setError(e.message); }
  }

  const allTags = [...new Set(documents.flatMap((doc) => doc.tags || []))].sort();
  const visibleDocuments = documentTagFilter ? documents.filter((doc) => (doc.tags || []).includes(documentTagFilter)) : documents;

  if (!token) return <main className="auth-page">
    <div className="auth-art"><div className="brand-mark">S<span>·</span>R</div><p className="eyebrow">PRIVATE KNOWLEDGE, CLEAR ANSWERS</p><h1>Your documents.<br />Your answers.</h1><p className="muted light">A local-first workspace for asking questions across your private files.</p><div className="auth-lines"><i /><i /><i /></div><small>SECURE ENTERPRISE RAG · LOCAL WORKSPACE</small></div>
    <section className="auth-panel"><div className="auth-box"><p className="eyebrow">WELCOME</p><h2>{mode === 'login' ? 'Sign in to your workspace' : 'Create your account'}</h2><p className="muted">Your files are indexed privately for your account.</p>
      <form onSubmit={submitAuth} className="stack-form">
        <label>Username<input name="username" required minLength="3" autoComplete="username" placeholder="your-name" /></label>
        {mode === 'register' && <label>Email<input name="email" type="email" required autoComplete="email" placeholder="you@company.com" /></label>}
        <label>Password<input name="password" type="password" required minLength={mode === 'register' ? 12 : 1} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder={mode === 'register' ? 'At least 12 characters' : 'Your password'} /></label>
        {error && <div className="alert error">{error}</div>}
        <button className="button primary full" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      <p className="switch-mode">{mode === 'login' ? 'New here?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p>
    </div></section>
  </main>;

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark small">S<span>·</span>R</div><div><strong>Secure RAG</strong><small>KNOWLEDGE WORKSPACE</small></div></div><div className="side-label">WORKSPACE</div><div className="nav-item active"><span>▦</span> Documents <b>{documents.length}</b></div><div className="privacy-card"><span className="lock-icon">◈</span><strong>Private by design</strong><p>Your documents are only searchable by you and workspace admins.</p></div><div className="side-bottom"><span className={`status-dot ${servicesReady === false ? 'offline' : ''}`} /> {servicesReady === null ? 'Checking local services…' : servicesReady ? 'Local services ready' : 'A local service is unavailable'}</div></aside>
    <main className="main-area"><header className="topbar"><div><p className="eyebrow">YOUR KNOWLEDGE BASE</p><h1>Document workspace</h1></div><div className="profile"><span className="avatar">{user?.username?.slice(0, 1).toUpperCase() || 'U'}</span><div><strong>{user?.username || 'Loading…'}</strong><small>{user?.role?.name || 'Account'}</small></div><button className="button ghost" onClick={() => { setToken(''); setUser(null); setDocuments([]); setUsers([]); setAnswer(null); setHistory([]); }}>Sign out</button></div></header>
      <div className="content"><section className="welcome-row"><div><h2>Ask your documents anything.</h2><p>Upload a file, then ask a question. Answers include source passages for review.</p></div><div className="privacy-pill"><span className="status-dot" /> Private workspace</div></section>
        {error && <div className="alert error dismiss"><span>{error}</span><button onClick={() => setError('')}>×</button></div>}
        {notice && <div className="alert success dismiss"><span>{notice}</span><button onClick={() => setNotice('')}>×</button></div>}
        {shareKey && <section className="panel share-key-panel"><div><h3>Share key for {shareKey.filename}</h3><p>This key can be redeemed once and expires {new Date(shareKey.expires_at).toLocaleString()}.</p></div><div className="share-key-actions"><input readOnly value={shareKey.token} onFocus={(event) => event.target.select()} aria-label="One-time document share key" /><button className="button ghost" onClick={() => navigator.clipboard.writeText(shareKey.token).then(() => setNotice('Share key copied.')).catch(() => setNotice('Select and copy the share key above.'))}>Copy</button><button className="button ghost" onClick={() => setShareKey(null)}>Close</button></div><small>Give this key only to the person who should access the document. The raw key will not be shown again.</small></section>}
        {shareManager && <section className="panel share-manager-panel"><div className="files-heading"><div><h3>Access keys · {shareManager.document.original_filename}</h3><p>Redeemed keys show who has access. Revoking a redeemed key removes that access.</p></div><button className="button ghost" onClick={() => setShareManager(null)}>Close</button></div>{shareManager.shares.length === 0 ? <p className="share-empty">No keys have been created for this document.</p> : <div className="share-list">{shareManager.shares.map((share) => <div className="share-row" key={share.share_id}><span>{share.revoked_at ? 'Revoked' : share.redeemed_by_username ? `Access granted to ${share.redeemed_by_username}` : `Unused · expires ${new Date(share.expires_at).toLocaleDateString()}`}</span>{!share.revoked_at && <button className="button ghost" onClick={() => revokeShare(share.share_id)}>Revoke</button>}</div>)}</div>}</section>}
        <section className="panel redeem-panel"><div><h3>Access a shared document</h3><p>Enter a one-time key from the document owner. Access stays available until revoked.</p></div><form onSubmit={redeemShare}><input value={redeemKey} onChange={(event) => setRedeemKey(event.target.value)} placeholder="Paste share key" minLength="32" maxLength="128" required /><button className="button primary" disabled={busy || redeemKey.trim().length < 32}>{busy ? 'Checking…' : 'Unlock document'}</button></form></section>
        <div className="dashboard-grid"><section className="panel upload-panel"><div className="panel-heading"><div className="panel-icon">↑</div><div><h3>Add a document</h3><p>PDF, DOCX, TXT, or Markdown · up to 20 MB</p></div></div><form onSubmit={upload} className="upload-form"><label className="dropzone"><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} /><span className="upload-symbol">＋</span><strong>{file ? file.name : 'Choose a file to upload'}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : 'or drag and drop it here'}</small></label><label className="tag-input-label">Tags <span>(optional, comma separated; up to 8)</span><input value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="policy, finance" maxLength="300" /></label><button className="button primary full" disabled={busy || !file}>{busy ? 'Working…' : 'Upload and index'}</button></form><div className="hint"><span>✦</span> Files are embedded locally; original uploads stay on this machine.</div></section>
          <section className="panel ask-panel"><div className="panel-heading"><div className="panel-icon violet">✧</div><div><h3>Ask a question</h3><p>Get a grounded answer from your indexed files.</p></div></div><form onSubmit={ask} className="ask-form"><textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What would you like to know?" rows="4" minLength="3" /><div className="ask-footer"><div className="ask-options"><small>Answers are based only on your documents.</small>{allTags.length > 0 && <label>Search in <select value={queryTag} onChange={(event) => setQueryTag(event.target.value)}><option value="">All documents</option>{allTags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}</select></label>}</div><button className="button dark" disabled={busy || question.trim().length < 3}>{busy ? 'Searching…' : 'Ask →'}</button></div></form></section></div>
        {answer && <section className="panel answer-panel"><div className="answer-title"><span className="panel-icon violet">✧</span><div><p className="eyebrow">GROUNDED RESPONSE</p><h3>Your answer</h3></div></div><p className="answer-text">{answer.answer}</p><div className="feedback-row"><span>Was this answer helpful?</span><button className={`button ${answer.feedback_rating === 'helpful' ? 'primary' : 'ghost'}`} aria-pressed={answer.feedback_rating === 'helpful'} onClick={() => rateAnswer('helpful')}>👍 Helpful</button><button className={`button ${answer.feedback_rating === 'not_helpful' ? 'primary' : 'ghost'}`} aria-pressed={answer.feedback_rating === 'not_helpful'} onClick={() => rateAnswer('not_helpful')}>👎 Not helpful</button>{answer.feedback_rating && <small>Your rating is saved and can be changed.</small>}</div>{answer.sources?.length > 0 && <div className="sources"><strong>Sources</strong><div className="source-list">{answer.sources.map((source, i) => <article className="source" key={`${source.document_id}-${source.chunk}-${i}`}><div><b>{source.filename}</b><small>Chunk {source.chunk}</small></div><p>{source.excerpt}{source.excerpt.length >= 360 ? '…' : ''}</p></article>)}</div></div>}</section>}
        {history.length > 0 && <section className="panel history-panel"><div className="files-heading"><div><h3>Recent questions</h3><p>Your latest {history.length} questions are private to your account</p></div><button className="button ghost" onClick={clearHistory}>Clear history</button></div><div className="history-list">{history.map((item) => <button className="history-item" key={item.id} onClick={() => revisitHistory(item)}><strong>{item.question}</strong><span>{item.answer.slice(0, 180)}{item.answer.length > 180 ? '…' : ''}</span><small>{new Date(item.created_at).toLocaleString()} · {item.sources.length} {item.sources.length === 1 ? 'source' : 'sources'}</small></button>)}</div></section>}
        {user?.role?.name?.toLowerCase() === "admin" && <section className="panel admin-panel"><div className="files-heading"><div><h3>Account access</h3><p>Manage workspace roles and account status</p></div><div className="admin-tools"><button className="button ghost account-action" onClick={viewAuditHistory}>View audit history</button><span className="admin-badge">ADMIN</span></div></div><div className="table-wrap"><table><thead><tr><th>USER</th><th>EMAIL</th><th>ROLE</th><th>STATUS</th><th>HISTORY</th><th /></tr></thead><tbody>{users.map((account) => <tr key={account.id}><td><strong>{account.username}{account.id === user.id ? " (you)" : ""}</strong></td><td>{account.email}</td><td><select className="role-select" value={account.role.name} disabled={account.id === user.id} onChange={(event) => changeUserRole(account, event.target.value)}><option value="user">user</option><option value="admin">admin</option></select></td><td><span className={account.is_active ? "ready" : "inactive-status"}><i />{account.is_active ? "active" : "inactive"}</span></td><td><button className={`button ${account.is_active ? "ghost" : "primary"} account-action`} disabled={account.id === user.id} onClick={() => changeUserStatus(account)}>{account.is_active ? "Deactivate" : "Activate"}</button></td><td><button className="button ghost account-action" onClick={() => viewAccountHistory(account)}>View</button></td></tr>)}</tbody></table></div></section>}
        {adminAudit && <section className="panel admin-audit-panel"><div className="files-heading"><div><h3>Workspace audit history</h3><p>Latest {adminAudit.length} account, document, and sharing events. No questions, file contents, or share keys are recorded.</p></div><div className="admin-tools"><button className="button ghost account-action" onClick={viewAuditHistory}>Refresh</button><button className="button ghost account-action" onClick={() => setAdminAudit(null)}>Close</button></div></div>{adminAudit.length === 0 ? <p className="share-empty">No audit events yet.</p> : <div className="admin-audit-list">{adminAudit.map((event) => <article className="admin-audit-item" key={event.id}><div><strong>{event.summary}</strong><small>{event.event_type.replaceAll('.', ' · ')}{event.actor_username ? ` · by ${event.actor_username}` : ''}{event.target_username ? ` · account ${event.target_username}` : ''}{event.document_id ? ` · document #${event.document_id}` : ''}</small></div><time>{new Date(event.created_at).toLocaleString()}</time></article>)}</div>}</section>}
        {adminHistory && <section className="panel admin-history-panel"><div className="files-heading"><div><h3>Question history · {adminHistory.username}</h3><p>Latest {adminHistory.entries.length} saved questions for this account</p></div><button className="button ghost" onClick={() => setAdminHistory(null)}>Close</button></div>{adminHistory.entries.length === 0 ? <div className="empty-state"><strong>No saved questions</strong><p>This account has not asked any questions yet.</p></div> : <div className="admin-history-list">{adminHistory.entries.map((item) => <article className="admin-history-item" key={item.id}><small>{new Date(item.created_at).toLocaleString()}</small><strong>{item.question}</strong><p>{item.answer}</p>{item.sources.length > 0 && <details><summary>{item.sources.length} {item.sources.length === 1 ? 'source' : 'sources'}</summary>{item.sources.map((source, i) => <div className="admin-history-source" key={`${source.document_id}-${i}`}><b>{source.filename} · chunk {source.chunk}</b><p>{source.excerpt}</p></div>)}</details>}</article>)}</div>}</section>}
        <section className="panel files-panel"><div className="files-heading"><div><h3>Your documents</h3><p>{visibleDocuments.length} shown · {documents.length} indexed in this workspace</p></div><div className="files-actions">{allTags.length > 0 && <label>Filter <select value={documentTagFilter} onChange={(event) => setDocumentTagFilter(event.target.value)}><option value="">All tags</option>{allTags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}</select></label>}<button className="button ghost" onClick={() => loadWorkspace().catch((e) => setError(e.message))}>↻ Refresh</button></div></div>
          {documents.length === 0 ? <div className="empty-state"><div className="empty-icon">▤</div><strong>No documents yet</strong><p>Upload a file above to build your searchable knowledge base.</p></div> : <div className="table-wrap"><table><thead><tr><th>DOCUMENT</th><th>STATUS</th><th>SECTIONS</th><th>ADDED</th><th /></tr></thead><tbody>{visibleDocuments.map((doc) => <tr key={doc.id}><td><span className="file-badge">{doc.original_filename.split('.').pop()?.toUpperCase()}</span><span className="document-name"><strong>{doc.original_filename}</strong><small className="doc-tags">{(doc.tags || []).map((tag) => <i key={tag}>{tag}</i>)}</small>{doc.shared && <small className="shared-by">Shared by {doc.owner_username}</small>}</span></td><td><span className="ready"><i /> {doc.status}</span></td><td>{doc.chunk_count}</td><td>{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}</td><td><div className="document-actions">{doc.can_delete && <><button className="button ghost account-action" onClick={() => createShare(doc)}>Share</button><button className="button ghost account-action" onClick={() => showShares(doc)}>Access</button><button className="icon-button" title="Delete document" onClick={() => removeDocument(doc)}>×</button></>}{doc.shared && <small>Read only</small>}</div></td></tr>)}</tbody></table></div>}
        </section><footer>Secure Enterprise RAG <span>·</span> Runs on local models and services</footer>
      </div>
    </main>
  </div>;
}



