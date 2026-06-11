import { NavLink, Outlet } from "react-router-dom";

export default function AppLayout() {
  const isEmbedded =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("embedded") === "1";

  return (
    <div className={isEmbedded ? "app-shell embedded" : "app-shell"}>
      <header className="app-header">
        <div className="app-header-inner">
          {!isEmbedded && (
            <a className="back-link" href="/">
              Back
            </a>
          )}
          <NavLink to="/" end className="app-brand">
            <span className="app-brand-mark" aria-hidden="true" />
            <span className="app-brand-text">
              <span className="app-brand-name">Chemical Structure Registration</span>
              <span className="app-brand-tagline">Draw, import, search, and register structures</span>
            </span>
          </NavLink>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
