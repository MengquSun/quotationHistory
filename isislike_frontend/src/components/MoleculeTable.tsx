import * as XLSX from "xlsx";
import type { Molecule } from "../api/cheminformatics";
import StructureImage from "./StructureImage";

interface Props {
  rows: Molecule[];
  showSimilarity?: boolean;
  preview?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: Molecule) => void;
  selectedId?: string | null;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function compoundLabel(row: Molecule): string {
  return row.name?.trim() || "Unnamed compound";
}

export default function MoleculeTable({
  rows,
  showSimilarity,
  preview = false,
  emptyMessage = "No results yet.",
  onRowClick,
  selectedId,
}: Props) {
  const exportExcel = () => {
    const data = rows.map((r) => ({
      ID: r.id,
      Name: r.name ?? "",
      "Canonical SMILES": r.canonical_smiles,
      "Mol. Weight": r.molecular_weight ?? "",
      Formula: r.molecular_formula ?? "",
      Notes: r.notes ?? "",
      Created: r.created_at ?? "",
      Updated: r.updated_at ?? "",
      ...(showSimilarity ? { Similarity: r.similarity ?? "" } : {}),
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Molecules");
    XLSX.writeFile(wb, "molecules_export.xlsx");
  };

  if (rows.length === 0) {
    return <p className="empty">{emptyMessage}</p>;
  }

  if (preview) {
    return (
      <>
        <div className="toolbar" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
          <button type="button" className="secondary" onClick={exportExcel}>
            Export to Excel
          </button>
          <span className="toolbar-meta">
            {rows.length} compound{rows.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="table-scroll compound-preview-table-wrap">
          <table className="compound-preview-table">
            <thead>
              <tr>
                <th>Structure</th>
                <th>Name</th>
                <th>Formula</th>
                <th>MW</th>
                <th>Canonical SMILES</th>
                <th>Created</th>
                <th>Updated</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <StructureImage
                      moleculeId={r.id}
                      alt={r.name?.trim() || r.canonical_smiles}
                      width={80}
                      height={56}
                    />
                  </td>
                  <td>
                    <span className="compound-name-link">{compoundLabel(r)}</span>
                  </td>
                  <td>{r.molecular_formula ?? "—"}</td>
                  <td>
                    {r.molecular_weight != null
                      ? r.molecular_weight.toFixed(2)
                      : "—"}
                  </td>
                  <td>
                    <code className="record-smiles-cell">{r.canonical_smiles}</code>
                  </td>
                  <td>{formatDate(r.created_at)}</td>
                  <td>{formatDate(r.updated_at)}</td>
                  <td>{r.notes?.trim() || "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary table-action-link"
                      onClick={() => onRowClick?.(r)}
                    >
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="compound-preview-cards">
          {rows.map((r) => (
            <li key={r.id} className="compound-preview-card">
              <div className="compound-preview-card-top">
                <StructureImage
                  moleculeId={r.id}
                  alt={r.name?.trim() || r.canonical_smiles}
                  width={72}
                  height={52}
                />
                <div>
                  <div className="compound-preview-card-name">
                    <span className="compound-name-link">{compoundLabel(r)}</span>
                  </div>
                  <div className="compound-preview-card-meta">
                    {r.molecular_formula ?? "—"} ·{" "}
                    {r.molecular_weight != null
                      ? r.molecular_weight.toFixed(2)
                      : "—"}
                  </div>
                </div>
              </div>
              <code className="compound-preview-card-smiles">{r.canonical_smiles}</code>
              {r.notes?.trim() && (
                <p className="compound-preview-card-notes">{r.notes.trim()}</p>
              )}
              <div className="compound-preview-card-footer">
                <span>
                  Updated {formatDate(r.updated_at)}
                </span>
                <button
                  type="button"
                  className="secondary table-action-link"
                  onClick={() => onRowClick?.(r)}
                >
                  Details
                </button>
              </div>
            </li>
          ))}
        </ul>
      </>
    );
  }

  return (
    <>
      <div className="toolbar" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <button type="button" className="secondary" onClick={exportExcel}>
          Export to Excel
        </button>
        <span className="toolbar-meta">
          {rows.length} result{rows.length !== 1 ? "s" : ""}
          {onRowClick ? " · click a row for details" : ""}
        </span>
      </div>
      <ul className="molecule-cards">
        {rows.map((r) => (
          <li
            key={r.id}
            className={
              onRowClick
                ? `molecule-card${selectedId === r.id ? " selected" : ""}`
                : "molecule-card"
            }
            onClick={onRowClick ? () => onRowClick(r) : undefined}
            onKeyDown={
              onRowClick
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onRowClick(r);
                    }
                  }
                : undefined
            }
            role={onRowClick ? "button" : undefined}
            tabIndex={onRowClick ? 0 : undefined}
          >
            <div className="molecule-card-structure">
              <StructureImage
                moleculeId={r.id}
                alt={r.name?.trim() || r.canonical_smiles}
              />
            </div>
            <div className="molecule-card-body">
              <div className="molecule-card-title">
                <span className="compound-name-link">{compoundLabel(r)}</span>
              </div>
              <dl className="molecule-card-meta">
                <div>
                  <dt>Formula</dt>
                  <dd>{r.molecular_formula ?? "—"}</dd>
                </div>
                <div>
                  <dt>MW</dt>
                  <dd>
                    {r.molecular_weight != null
                      ? r.molecular_weight.toFixed(2)
                      : "—"}
                  </dd>
                </div>
                {showSimilarity && (
                  <div>
                    <dt>Similarity</dt>
                    <dd className="similarity-bar">
                      {r.similarity != null
                        ? `${(r.similarity * 100).toFixed(1)}%`
                        : "—"}
                    </dd>
                  </div>
                )}
              </dl>
              <code className="molecule-card-smiles">{r.canonical_smiles}</code>
              <div className="molecule-card-actions">
                <button
                  type="button"
                  className="table-action-link"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRowClick?.(r);
                  }}
                >
                  View details
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
