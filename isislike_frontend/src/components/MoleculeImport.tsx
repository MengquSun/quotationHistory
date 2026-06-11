import { useRef, useState } from "react";
import { importMolecules, type ImportResult } from "../api/cheminformatics";

interface Props {
  onImported: (result: ImportResult) => void;
  disabled?: boolean;
}

export default function MoleculeImport({ onImported, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (
      !lower.endsWith(".mol") &&
      !lower.endsWith(".sdf") &&
      !lower.endsWith(".xlsx") &&
      !lower.endsWith(".xlsm")
    ) {
      setError("Choose a .mol, .sdf, or .xlsx file");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await importMolecules(file);
      onImported(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="import-block">
      <input
        ref={inputRef}
        type="file"
        accept=".mol,.sdf,.xlsx,.xlsm"
        hidden
        disabled={disabled || loading}
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />
      <button
        type="button"
        className="secondary"
        disabled={disabled || loading}
        onClick={() => inputRef.current?.click()}
      >
        {loading ? "Importing…" : "Import .mol / .sdf / Excel"}
      </button>
      {error && <span className="import-error">{error}</span>}
    </div>
  );
}
