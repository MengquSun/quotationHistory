import { useCallback, useEffect, useState } from "react";
import {
  deleteMolecule,
  getMolecule,
  updateMolecule,
  type Molecule,
  type MoleculeDetail,
} from "../api/cheminformatics";
import StructureImage from "./StructureImage";

interface Props {
  moleculeId: string | null;
  onClose: () => void;
  onUpdated: (molecule: Molecule) => void;
  onDeleted: (id: string) => void;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function MoleculeDetailDrawer({
  moleculeId,
  onClose,
  onUpdated,
  onDeleted,
}: Props) {
  const [detail, setDetail] = useState<MoleculeDetail | null>(null);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      const row = await getMolecule(id);
      setDetail(row);
      setName(row.name ?? "");
      setNotes(row.notes ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load record");
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (moleculeId) {
      void load(moleculeId);
    } else {
      setDetail(null);
      setError(null);
      setStatus(null);
    }
  }, [moleculeId, load]);

  const handleSave = async () => {
    if (!moleculeId) return;
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const updated = await updateMolecule(moleculeId, {
        name: name.trim() || null,
        notes: notes.trim() || null,
      });
      setDetail((d) =>
        d
          ? {
              ...d,
              ...updated,
            }
          : null
      );
      setStatus("Saved.");
      onUpdated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!moleculeId || !detail) return;
    const label = detail.name || detail.canonical_smiles.slice(0, 40);
    if (!window.confirm(`Delete this record?\n\n${label}`)) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteMolecule(moleculeId);
      onDeleted(moleculeId);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  if (!moleculeId) return null;

  return (
    <>
      <button
        type="button"
        className="drawer-backdrop"
        aria-label="Close detail panel"
        onClick={onClose}
      />
      <aside className="detail-drawer" role="dialog" aria-labelledby="drawer-title">
        <header className="detail-drawer-header">
          <h2 id="drawer-title">Compound record</h2>
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="detail-drawer-body">
          {loading && <p className="empty">Loading…</p>}
          {error && <div className="status error">{error}</div>}
          {status && <div className="status success">{status}</div>}

          {detail && !loading && (
            <>
              <div className="structure-preview">
                <StructureImage
                  moleculeId={detail.id}
                  alt={detail.name?.trim() || "2D structure"}
                  className="structure-preview-img"
                  width={320}
                  height={240}
                />
              </div>

              <dl className="detail-meta">
                <div>
                  <dt>Canonical SMILES</dt>
                  <dd>
                    <code>{detail.canonical_smiles}</code>
                  </dd>
                </div>
                <div>
                  <dt>Molecular weight</dt>
                  <dd>
                    {detail.molecular_weight != null
                      ? detail.molecular_weight.toFixed(4)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Formula</dt>
                  <dd>{detail.molecular_formula ?? "—"}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{formatDate(detail.created_at)}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatDate(detail.updated_at)}</dd>
                </div>
              </dl>

              <div className="detail-form">
                <label htmlFor="mol-name">Name</label>
                <input
                  id="mol-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Compound name"
                />
                <label htmlFor="mol-notes">Notes</label>
                <textarea
                  id="mol-notes"
                  rows={4}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Lab notes, batch ID, etc."
                />
              </div>

              <div className="detail-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={saving || deleting}
                  onClick={() => void handleSave()}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={saving || deleting}
                  onClick={() => void handleDelete()}
                >
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
