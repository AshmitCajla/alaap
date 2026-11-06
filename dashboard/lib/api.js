"use client";

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken() {
  try { return localStorage.getItem("alaap_token"); } catch { return null; }
}
export function setToken(t) {
  try { t ? localStorage.setItem("alaap_token", t) : localStorage.removeItem("alaap_token"); } catch {}
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(API + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth")) {
    setToken(null);
    window.location.href = "/login";
    throw new Error("Signed out");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

export const rupees = (n) => (n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN"));
export const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
