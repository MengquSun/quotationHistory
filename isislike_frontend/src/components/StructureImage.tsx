import { useEffect, useRef, useState } from "react";
import { structureSvgUrl } from "../api/cheminformatics";

interface Props {
  moleculeId: string;
  alt?: string;
  className?: string;
  width?: number;
  height?: number;
}

export default function StructureImage({
  moleculeId,
  alt = "2D chemical structure",
  className = "structure-thumb",
  width = 140,
  height = 105,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const retries = useRef(0);

  useEffect(() => {
    setFailed(false);
    setSrc(null);
    retries.current = 0;

    const el = hostRef.current;
    if (!el) return;

    const load = () => {
      const base = structureSvgUrl(moleculeId);
      const bust =
        retries.current > 0 ? `?retry=${retries.current}` : "";
      setSrc(`${base}${bust}`);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          load();
          observer.disconnect();
        }
      },
      { rootMargin: "120px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [moleculeId]);

  const handleError = () => {
    if (retries.current < 2) {
      retries.current += 1;
      window.setTimeout(() => {
        const base = structureSvgUrl(moleculeId);
        setSrc(`${base}?retry=${retries.current}`);
      }, 800 * retries.current);
      return;
    }
    setFailed(true);
  };

  if (failed) {
    return (
      <div
        ref={hostRef}
        className={`${className} structure-thumb-fallback`}
        style={{ width, height }}
        aria-hidden
      >
        No image
      </div>
    );
  }

  return (
    <div ref={hostRef} className="structure-thumb-wrap" style={{ width, height }}>
      {src ? (
        <img
          className={className}
          src={src}
          alt={alt}
          width={width}
          height={height}
          decoding="async"
          onError={handleError}
        />
      ) : (
        <div
          className={`${className} structure-thumb-fallback structure-thumb-loading`}
          style={{ width, height }}
          aria-hidden
        />
      )}
    </div>
  );
}
