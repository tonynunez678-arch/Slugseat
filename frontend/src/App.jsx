import { useEffect, useState } from "react";
import { createWatch, deleteWatch, getTerms, listWatches } from "./api.js";

function SeatBadge({ status }) {
  if (!status) return <span className="badge pending">Checking soon</span>;
  if (status.seats_open > 0) return <span className="badge open">{status.seats_open} open</span>;
  return <span className="badge full">Full</span>;
}

export default function App() {
  const [terms, setTerms] = useState([]);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [term, setTerm] = useState("");
  const [subject, setSubject] = useState("");
  const [catalogNumber, setCatalogNumber] = useState("");
  const [classNumber, setClassNumber] = useState("");
  const [consent, setConsent] = useState(false);
  const [watches, setWatches] = useState([]);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getTerms()
      .then((data) => {
        setTerms(data);
        setTerm(data[1]?.code || data[0]?.code || "");
      })
      .catch((err) => setMessage({ kind: "error", text: err.message }));
  }, []);

  useEffect(() => {
    if (watches.length === 0) return undefined;
    const timer = setInterval(() => refresh().catch(() => {}), 30000);
    return () => clearInterval(timer);
  }, [watches.length, email]);

  async function refresh(forEmail = email) {
    if (!forEmail) return;
    setWatches(await listWatches(forEmail));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await createWatch({
        email,
        term,
        subject,
        catalog_number: catalogNumber,
        class_number: classNumber,
        phone: phone || null,
      });
      setClassNumber("");
      setMessage({ kind: "ok", text: "You're on the list. We'll alert you when a seat opens." });
      await refresh();
    } catch (err) {
      setMessage({ kind: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(id) {
    await deleteWatch(id, email);
    await refresh();
  }

  const termName = (code) => terms.find((t) => t.code === code)?.name || code;

  return (
    <main>
      <header>
        <h1>SlugSeat</h1>
        <p>Get a text or email the moment a seat opens in your UCSC class.</p>
      </header>

      <form onSubmit={handleSubmit} className="card">
        <label>
          UCSC email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} onBlur={() => refresh().catch(() => {})} placeholder="sammy@ucsc.edu" />
        </label>
        <label>
          Phone for texts (optional)
          <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+18315550123" />
        </label>
        <div className="row">
          <label>
            Term
            <select value={term} onChange={(e) => setTerm(e.target.value)}>
              {terms.map((t) => (
                <option key={t.code} value={t.code}>{t.name}</option>
              ))}
            </select>
          </label>
          <label>
            Class number
            <input required inputMode="numeric" pattern="\d{5}" value={classNumber} onChange={(e) => setClassNumber(e.target.value.trim())} placeholder="30628" />
          </label>
        </div>
        <div className="row">
          <label>
            Subject
            <input required pattern="[A-Za-z]{2,5}" value={subject} onChange={(e) => setSubject(e.target.value.trim().toUpperCase())} placeholder="CSE" />
          </label>
          <label>
            Course number
            <input required pattern="\d{1,3}[A-Za-z]{0,2}" value={catalogNumber} onChange={(e) => setCatalogNumber(e.target.value.trim().toUpperCase())} placeholder="101" />
          </label>
        </div>
        <p className="muted hint">Find all three on the UCSC class search. The class number is the 5-digit number for your section.</p>
        <label className="consent">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          I agree to receive seat alerts for the classes I add. I can remove them anytime.
        </label>
        <button type="submit" disabled={busy || !consent}>{busy ? "Adding..." : "Watch this class"}</button>
        {message && <p className={`message ${message.kind}`}>{message.text}</p>}
      </form>

      {watches.length > 0 && (
        <section className="card">
          <h2>Your watched classes</h2>
          <ul>
            {watches.map((w) => (
              <li key={w.id}>
                <div>
                  <strong>{w.class_status?.title || `${w.subject} ${w.catalog_number}`}</strong>
                  <span className="muted">#{w.class_number} · {termName(w.term)}</span>
                </div>
                <SeatBadge status={w.class_status} />
                <button className="link" onClick={() => handleRemove(w.id)}>Remove</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="muted">Not affiliated with UC Santa Cruz. Seat data comes from the public class search.</footer>
    </main>
  );
}
