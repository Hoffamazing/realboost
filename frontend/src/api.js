/**
 * RealBoost AI — Frontend API Client
 * All calls to the FastAPI backend go through here
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── AUTH TOKEN MANAGEMENT ─────────────────────────────────────────────────────

let authToken = localStorage.getItem("realboost_token") || null;

export const setToken = (token) => {
  authToken = token;
  localStorage.setItem("realboost_token", token);
};

export const clearToken = () => {
  authToken = null;
  localStorage.removeItem("realboost_token");
};

export const getToken = () => authToken;

// ── BASE FETCH ─────────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (res.status === 402) {
    window.location.href = "/billing";
    throw new Error("Subscription required");
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  return res.status === 204 ? null : res.json();
}

// ── AUTH ──────────────────────────────────────────────────────────────────────

export const auth = {
  register: (data) =>
    apiFetch("/api/agents/register", { method: "POST", body: JSON.stringify(data) }),

  login: (email, password) =>
    apiFetch("/api/agents/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  getProfile: () => apiFetch("/api/agents/me"),

  updateProfile: (data) =>
    apiFetch("/api/agents/me", { method: "PATCH", body: JSON.stringify(data) }),
};

// ── LEADS ─────────────────────────────────────────────────────────────────────

export const leads = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/api/leads${qs ? "?" + qs : ""}`);
  },

  create: (data) =>
    apiFetch("/api/leads", { method: "POST", body: JSON.stringify(data) }),

  get: (id) => apiFetch(`/api/leads/${id}`),

  update: (id, data) =>
    apiFetch(`/api/leads/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  delete: (id) => apiFetch(`/api/leads/${id}`, { method: "DELETE" }),

  getMessages: (id) => apiFetch(`/api/leads/${id}/messages`),

  /** Core AI qualification — sends lead message through GPT-4o */
  sendMessage: (id, content, channel = "chat") =>
    apiFetch(`/api/leads/${id}/qualify`, {
      method: "POST",
      body: JSON.stringify({ content, channel }),
    }),

  getStats: () => apiFetch("/api/leads/stats/overview"),
};

// ── AI ────────────────────────────────────────────────────────────────────────

export const ai = {
  /** Generate a single email */
  generateEmail: (prompt, emailType = "newsletter") =>
    apiFetch("/api/ai/generate-email", {
      method: "POST",
      body: JSON.stringify({ prompt, email_type: emailType }),
    }),

  /** Generate a full drip campaign sequence */
  generateCampaign: (name, campaignType, targetAudience, numEmails = 5) =>
    apiFetch("/api/ai/generate-campaign", {
      method: "POST",
      body: JSON.stringify({
        name,
        campaign_type: campaignType,
        target_audience: targetAudience,
        num_emails: numEmails,
      }),
    }),

  /** Generate monthly market newsletter */
  generateNewsletter: (location, marketData = null) =>
    apiFetch("/api/ai/generate-newsletter", {
      method: "POST",
      body: JSON.stringify({ location, market_data: marketData }),
    }),
};

// ── CAMPAIGNS ─────────────────────────────────────────────────────────────────

export const campaigns = {
  list: () => apiFetch("/api/campaigns"),

  create: (data) =>
    apiFetch("/api/campaigns", { method: "POST", body: JSON.stringify(data) }),

  addStep: (campaignId, step) =>
    apiFetch(`/api/campaigns/${campaignId}/steps`, {
      method: "POST",
      body: JSON.stringify(step),
    }),

  enrollLeads: (campaignId, leadIds) =>
    apiFetch(`/api/campaigns/${campaignId}/enroll`, {
      method: "POST",
      body: JSON.stringify({ lead_ids: leadIds }),
    }),
};

// ── ADS ───────────────────────────────────────────────────────────────────────

export const ads = {
  getPerformance: () => apiFetch("/api/ads/performance"),

  runOptimization: () =>
    apiFetch("/api/ads/optimize", { method: "POST" }),

  applyOptimization: (logId) =>
    apiFetch(`/api/ads/optimize/${logId}/apply`, { method: "POST" }),

  connectAccount: (platform, accessToken, accountId) =>
    apiFetch("/api/ads/accounts/connect", {
      method: "POST",
      body: JSON.stringify({ platform, access_token: accessToken, account_id: accountId }),
    }),

  updateBudget: (platform, monthlyBudget) =>
    apiFetch(`/api/ads/accounts/${platform}/budget`, {
      method: "PATCH",
      body: JSON.stringify({ platform, monthly_budget: monthlyBudget }),
    }),

  getMetaPerformance: () => apiFetch("/api/ads/meta/performance"),
  getGooglePerformance: () => apiFetch("/api/ads/google/performance"),
  getTikTokPerformance: () => apiFetch("/api/ads/tiktok/performance"),
  getWazePerformance: () => apiFetch("/api/ads/waze/performance"),
};

// ── BILLING ───────────────────────────────────────────────────────────────────

export const billing = {
  getPlans: () => apiFetch("/api/billing/plans"),

  getStatus: () => apiFetch("/api/billing/status"),

  /** Creates a Stripe Checkout session and redirects to it */
  startCheckout: async (plan) => {
    const result = await apiFetch("/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({
        plan,
        success_url: `${window.location.origin}/billing/success`,
        cancel_url: `${window.location.origin}/billing`,
      }),
    });
    if (result.url) window.location.href = result.url;
    return result;
  },

  /** Opens Stripe Customer Portal for self-serve billing management */
  openPortal: async () => {
    const result = await apiFetch("/api/billing/portal", {
      method: "POST",
      body: JSON.stringify({ return_url: `${window.location.origin}/settings` }),
    });
    if (result.url) window.location.href = result.url;
    return result;
  },
};

// ── CONVERSATIONS ─────────────────────────────────────────────────────────────

export const conversations = {
  list: () => apiFetch("/api/conversations"),
};
