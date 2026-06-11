/**
 * All chemical operations go through the RDKit microservice.
 * The frontend NEVER writes SMILES directly to Supabase.
 */

/** Production Netlify: empty → same-origin /api (proxied in netlify.toml). Dev: local backend. */
function resolveApiBase(): string {
  const fromEnv = import.meta.env.VITE_CHEMINFORMATICS_API_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "http://localhost:8000";
  return "";
}

const API_BASE = resolveApiBase();

function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${p}` : p;
}

function formatNetworkError(op: string, err: unknown): string {
  if (err instanceof TypeError) {
    const hint = import.meta.env.DEV
      ? "Start the backend: cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000. Open the app at http://localhost:5173 (not 127.0.0.1) if CORS blocks."
      : "Redeploy Netlify after setting VITE_CHEMINFORMATICS_API_URL or the /api proxy in netlify.toml.";
    return `${op}: cannot reach API. ${hint}`;
  }
  return err instanceof Error ? err.message : `${op} failed`;
}

export interface Molecule {
  id: string;
  canonical_smiles: string;
  molecular_weight?: number | null;
  molecular_formula?: string | null;
  similarity?: number | null;
  name?: string | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MoleculeDetail extends Molecule {
  has_structure_svg: boolean;
}

export interface ImportResult {
  success_count: number;
  failed_count: number;
  errors: { index: number; reason: string }[];
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(`/api${path}`), init);
  } catch (e) {
    throw new Error(formatNetworkError("Request", e));
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail =
      typeof err.detail === "string"
        ? err.detail
        : JSON.stringify(err.detail ?? err);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** 2D structure SVG — same base as other API calls (Render in prod, localhost in dev). */
export function structureSvgUrl(moleculeId: string): string {
  const id = encodeURIComponent(moleculeId);
  return apiUrl(`/api/molecules/${id}/structure.svg`);
}

export async function getMolecule(id: string): Promise<MoleculeDetail> {
  return request<MoleculeDetail>(`/molecules/${id}`);
}

export async function updateMolecule(
  id: string,
  fields: { name?: string | null; notes?: string | null }
): Promise<Molecule> {
  return request<Molecule>(`/molecules/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function deleteMolecule(id: string): Promise<void> {
  await request<void>(`/molecules/${id}`, { method: "DELETE" });
}

export async function listMolecules(limit = 500): Promise<Molecule[]> {
  return request<Molecule[]>(`/molecules?limit=${limit}`);
}

export async function saveMolecule(
  smiles: string,
  options?: { molfile?: string; name?: string; notes?: string }
): Promise<Molecule> {
  return post<Molecule>("/molecules/save", {
    smiles,
    molfile: options?.molfile,
    name: options?.name,
    notes: options?.notes,
  });
}

export async function importMolecules(file: File): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return request<ImportResult>("/molecules/import", {
    method: "POST",
    body: form,
  });
}

export async function exactSearch(smiles: string): Promise<Molecule | null> {
  return post<Molecule | null>("/molecules/search/exact", { smiles });
}

export async function substructureSearch(
  smarts: string
): Promise<Molecule[]> {
  return post<Molecule[]>("/molecules/search/substructure", { smarts });
}

export async function similaritySearch(
  smiles: string,
  matchThreshold = 0.7,
  matchCount = 50
): Promise<Molecule[]> {
  return post<Molecule[]>("/molecules/search/similarity", {
    smiles,
    match_threshold: matchThreshold,
    match_count: matchCount,
  });
}
