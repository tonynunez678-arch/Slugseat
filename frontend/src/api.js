const BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(", ") : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

export const getTerms = () => request("/api/terms");
export const listWatches = (email) => request(`/api/watches?email=${encodeURIComponent(email)}`);
export const createWatch = (watch) => request("/api/watches", { method: "POST", body: JSON.stringify(watch) });
export const deleteWatch = (id, email) =>
  request(`/api/watches/${id}?email=${encodeURIComponent(email)}`, { method: "DELETE" });
