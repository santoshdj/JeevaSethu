const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ---- Patient types ----
export interface Patient {
  id: string;
  name: string;
  age: number;
  sex: string;
  dob: string;
}

// ---- Trial match types ----
export interface Citation {
  title: string;
  url: string;
}

export interface MatchResult {
  patient_id: string;
  patient_name: string;
  thread_id: string;
  response: string;
  citations: Citation[];
}

export interface ChatResponse {
  response: string;
  citations: Citation[];
}

// A single turn in the chat history (local state only)
export interface ChatTurn {
  role: "user" | "agent";
  text: string;
  citations: Citation[];
}

// ---- API calls ----
export function fetchPatients(name?: string): Promise<Patient[]> {
  const qs = name ? `?name=${encodeURIComponent(name)}` : "";
  return request<Patient[]>(`/api/patients${qs}`);
}

export function fetchPatient(id: string): Promise<Patient> {
  return request<Patient>(`/api/patients/${id}`);
}

export interface PatientProfile {
  patient_id: string;
  profile: string;
}

export function fetchPatientProfile(id: string): Promise<PatientProfile> {
  return request<PatientProfile>(`/api/patients/${id}/profile`);
}

export function runTrialMatch(patientId: string): Promise<MatchResult> {
  return request<MatchResult>(`/api/patients/${patientId}/match-trials`, {
    method: "POST",
  });
}

export function sendChatMessage(
  threadId: string,
  message: string
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId, message }),
  });
}

