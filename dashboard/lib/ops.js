"use client";

import { API } from "./api";

// The Alaap team's console uses its own login, kept apart from shop owners' logins.
export function getOpsToken() {
  try { return localStorage.getItem("alaap_ops_token"); } catch { return null; }
}
export function setOpsToken(t) {
  try { t ? localStorage.setItem("alaap_ops_token", t) : localStorage.removeItem("alaap_ops_token"); } catch {}
}

export async function opsApi(path, { method = "GET", body, form } = {}) {
  const headers = form ? {} : { "Content-Type": "application/json" };
  const token = getOpsToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(API + "/api/ops" + path, {
    method, headers, body: form || (body === undefined ? undefined : JSON.stringify(body)),
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth")) {
    setOpsToken(null);
    window.location.href = "/ops/login";
    throw new Error("Signed out");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}
