import { useCallback, useState } from "react";
import {
  exactSearch,
  listMolecules,
  saveMolecule,
  similaritySearch,
  substructureSearch,
  type ImportResult,
  type Molecule,
} from "../api/cheminformatics";
import ErrorBoundary from "../components/ErrorBoundary";
import KetcherEditor, { type KetcherHandle } from "../components/KetcherEditor";
import MoleculeDetailDrawer from "../components/MoleculeDetailDrawer";
import MoleculeImport from "../components/MoleculeImport";
import MoleculeTable from "../components/MoleculeTable";

type SearchMode = "save" | "exact" | "substructure" | "similarity";

function upsertRow(rows: Molecule[], updated: Molecule): Molecule[] {
  const i = rows.findIndex((r) => r.id === updated.id);
  if (i < 0) return rows;
  const next = [...rows];
  next[i] = { ...next[i], ...updated };
  return next;
}

function removeRow(rows: Molecule[], id: string): Molecule[] {
  return rows.filter((r) => r.id !== id);
}

export default function CheminformaticsPage() {
  const [ketcher, setKetcher] = useState<KetcherHandle | null>(null);
  const [mode, setMode] = useState<SearchMode>("save");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{
    type: "info" | "error" | "success";
    message: string;
  } | null>(null);
  const [results, setResults] = useState<Molecule[]>([]);
  const [singleResult, setSingleResult] = useState<Molecule | null>(null);
  const [threshold, setThreshold] = useState(0.7);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewAll, setViewAll] = useState(false);
  const [allMolecules, setAllMolecules] = useState<Molecule[]>([]);
  const [seeAllLoading, setSeeAllLoading] = useState(false);

  const run = useCallback(
    async (fn: () => Promise<void>) => {
      setLoading(true);
      setStatus(null);
      setResults([]);
      setSingleResult(null);
      setViewAll(false);
      try {
        await fn();
      } catch (e) {
        setStatus({
          type: "error",
          message: e instanceof Error ? e.message : "Operation failed",
        });
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleSave = () =>
    run(async () => {
      if (!ketcher) throw new Error("Editor not ready");
      const smiles = await ketcher.getSmiles();
      const molfile = await ketcher.getMolfile();
      const saved = await saveMolecule(smiles, { molfile });
      setSingleResult(saved);
      setResults([saved]);
      setStatus({
        type: "success",
        message: `Saved: ${saved.canonical_smiles}`,
      });
    });

  const handleExact = () =>
    run(async () => {
      if (!ketcher) throw new Error("Editor not ready");
      const smiles = await ketcher.getSmiles();
      const hit = await exactSearch(smiles);
      if (!hit) {
        setStatus({ type: "info", message: "No exact match found." });
        return;
      }
      setSingleResult(hit);
      setResults([hit]);
      setStatus({ type: "success", message: "Exact match found." });
    });

  const handleSubstructure = () =>
    run(async () => {
      if (!ketcher) throw new Error("Editor not ready");
      const smarts = await ketcher.getSmarts();
      const hits = await substructureSearch(smarts);
      setResults(hits);
      setStatus({
        type: hits.length ? "success" : "info",
        message:
          hits.length === 0
            ? "No substructure matches."
            : `${hits.length} substructure match(es).`,
      });
    });

  const handleSimilarity = () =>
    run(async () => {
      if (!ketcher) throw new Error("Editor not ready");
      const smiles = await ketcher.getSmiles();
      const hits = await similaritySearch(smiles, threshold);
      setResults(hits);
      setStatus({
        type: hits.length ? "success" : "info",
        message:
          hits.length === 0
            ? "No similar structures above threshold."
            : `${hits.length} similar structure(s).`,
      });
    });

  const handleImported = useCallback(
    (result: ImportResult) => {
      setResults([]);
      setSingleResult(null);
      setViewAll(false);
      const errPreview =
        result.errors.length > 0
          ? ` First error: ${result.errors[0].reason}`
          : "";
      setStatus({
        type: result.success_count > 0 ? "success" : "info",
        message: `Import: ${result.success_count} saved, ${result.failed_count} failed.${errPreview}`,
      });
    },
    []
  );

  const handleRecordUpdated = useCallback((updated: Molecule) => {
    setResults((r) => upsertRow(r, updated));
    setAllMolecules((r) => upsertRow(r, updated));
    if (singleResult?.id === updated.id) setSingleResult(updated);
  }, [singleResult?.id]);

  const handleRecordDeleted = useCallback((id: string) => {
    setResults((r) => removeRow(r, id));
    setAllMolecules((r) => removeRow(r, id));
    if (singleResult?.id === id) setSingleResult(null);
    setSelectedId(null);
    setStatus({ type: "info", message: "Record deleted." });
  }, [singleResult?.id]);

  const handleSeeAll = useCallback(async () => {
    setSeeAllLoading(true);
    setStatus(null);
    try {
      const rows = await listMolecules();
      setAllMolecules(rows);
      setViewAll(true);
      setResults([]);
      setSingleResult(null);
      setStatus({
        type: rows.length ? "success" : "info",
        message: rows.length
          ? `${rows.length} registered structure(s).`
          : "No registered structures yet.",
      });
    } catch (e) {
      setStatus({
        type: "error",
        message: e instanceof Error ? e.message : "Failed to load structures",
      });
    } finally {
      setSeeAllLoading(false);
    }
  }, []);

  const displayRows = viewAll ? allMolecules : mode === "exact" && singleResult ? [singleResult] : results;

  return (
    <>
      <div className="app-layout">
        <section className="panel">
          <div className="panel-header">Structure Editor (Ketcher)</div>
          <div className="panel-body">
            <div className="mode-tabs">
              {(
                [
                  ["save", "Draw & Save"],
                  ["exact", "Exact Search"],
                  ["substructure", "Substructure"],
                  ["similarity", "Similarity"],
                ] as const
              ).map(([m, label]) => (
                <button
                  key={m}
                  type="button"
                  className={mode === m ? "active" : ""}
                  onClick={() => {
                    setMode(m);
                    setStatus(null);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>

            <ErrorBoundary
              fallback={
                <div className="status error">
                  Structure editor failed to load. Try hard refresh (Cmd+Shift+R).
                  Results panel still works if the backend is running.
                </div>
              }
            >
              <KetcherEditor onReady={setKetcher} />
            </ErrorBoundary>

            {mode === "similarity" && (
              <div className="threshold-row">
                <label htmlFor="threshold">Min. Tanimoto:</label>
                <input
                  id="threshold"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                />
              </div>
            )}

            <div className="toolbar">
              {mode === "save" && (
                <button
                  type="button"
                  className="primary"
                  disabled={loading || !ketcher}
                  onClick={handleSave}
                >
                  Save Structure
                </button>
              )}
              {mode === "exact" && (
                <button
                  type="button"
                  className="primary"
                  disabled={loading || !ketcher}
                  onClick={handleExact}
                >
                  Exact Search
                </button>
              )}
              {mode === "substructure" && (
                <button
                  type="button"
                  className="primary"
                  disabled={loading || !ketcher}
                  onClick={handleSubstructure}
                >
                  Substructure Search
                </button>
              )}
              {mode === "similarity" && (
                <button
                  type="button"
                  className="primary"
                  disabled={loading || !ketcher}
                  onClick={handleSimilarity}
                >
                  Similarity Search
                </button>
              )}
            </div>

            {status && (
              <div className={`status ${status.type}`}>{status.message}</div>
            )}
          </div>
        </section>

        <section className="panel panel-results">
          <div className="panel-header">
            <span>{viewAll ? "All registered structures" : "Results"}</span>
            {viewAll ? (
              <button
                type="button"
                className="secondary header-action"
                onClick={() => {
                  setViewAll(false);
                  setStatus(null);
                }}
              >
                Back to results
              </button>
            ) : (
              <button
                type="button"
                className="secondary header-action"
                disabled={loading || seeAllLoading}
                onClick={() => void handleSeeAll()}
              >
                {seeAllLoading ? "Loading…" : "See All"}
              </button>
            )}
          </div>
          <div className="panel-body">
            <div className="toolbar" style={{ marginTop: 0 }}>
              <MoleculeImport
                onImported={(r) => void handleImported(r)}
                disabled={loading || viewAll}
              />
            </div>
            <MoleculeTable
              rows={displayRows}
              showSimilarity={!viewAll && mode === "similarity"}
              preview={viewAll}
              selectedId={selectedId}
              onRowClick={(row) => setSelectedId(row.id)}
              emptyMessage={
                viewAll
                  ? "No registered structures yet."
                  : "No results yet. Draw a structure, import a file, or run a search."
              }
            />
          </div>
        </section>
      </div>

      <MoleculeDetailDrawer
        moleculeId={selectedId}
        onClose={() => setSelectedId(null)}
        onUpdated={handleRecordUpdated}
        onDeleted={handleRecordDeleted}
      />
    </>
  );
}
