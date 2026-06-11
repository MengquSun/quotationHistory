import { useEffect, useState } from "react";
import { Editor } from "ketcher-react";
import "ketcher-react/dist/index.css";

export interface KetcherHandle {
  getSmiles: () => Promise<string>;
  getSmarts: () => Promise<string>;
  getMolfile: () => Promise<string>;
}

interface KetcherInstance {
  getMolfile: () => Promise<string>;
  getSmiles: () => Promise<string>;
  getSmarts: () => Promise<string>;
  setMolecule: (structure: string) => Promise<void> | void;
}

interface Props {
  onReady?: (handle: KetcherHandle) => void;
}

export default function KetcherEditor({ onReady }: Props) {
  const [structServiceProvider, setStructServiceProvider] =
    useState<unknown>(null);
  const [initError, setInitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("ketcher-standalone")
      .then((mod) => {
        if (!cancelled) {
          setStructServiceProvider(new mod.StandaloneStructServiceProvider());
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setInitError(
            e instanceof Error ? e.message : "Failed to load Ketcher engine"
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (initError) {
    return <div className="status error">{initError}</div>;
  }

  if (!structServiceProvider) {
    return (
      <div className="ketcher-wrap status info">Loading structure editor…</div>
    );
  }

  return (
    <div className="ketcher-wrap">
      <Editor
        staticResourcesUrl=""
        structServiceProvider={structServiceProvider as never}
        disableMacromoleculesEditor
        errorHandler={(message) => console.error("Ketcher:", message)}
        onInit={(ketcher: KetcherInstance) => {
          window.ketcher = ketcher;
          try {
            void ketcher.setMolecule("");
          } catch {
            /* empty canvas is fine */
          }
          onReady?.({
            getSmiles: async () => {
              const molfile = await ketcher.getMolfile();
              if (!molfile?.trim()) throw new Error("Draw a structure first");
              return ketcher.getSmiles();
            },
            getSmarts: async () => {
              const molfile = await ketcher.getMolfile();
              if (!molfile?.trim()) throw new Error("Draw a query structure first");
              return ketcher.getSmarts();
            },
            getMolfile: () => ketcher.getMolfile(),
          });
        }}
      />
    </div>
  );
}
