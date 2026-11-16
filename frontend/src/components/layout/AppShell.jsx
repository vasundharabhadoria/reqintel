import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import {
  ChevronUp,
  FileText,
  Folder,
  LayoutGrid,
  LogOut,
  Settings,
  Sparkles,
  User,
} from "lucide-react";
import {
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useClick,
  useDismiss,
  useFloating,
  useInteractions,
  useRole,
} from "@floating-ui/react";

import { useAuth } from "../../hooks/useAuth";
import {
  clearProfileSummary,
  useProfileSummary,
} from "../../hooks/useProfileSummary";
import { roleLabel } from "../../features/profile/profileFormat";
import "./appShell.css";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: LayoutGrid, to: "/dashboard" },
  { key: "projects", label: "Projects", icon: Folder, to: "/projects" },
  { key: "reports", label: "Reports", icon: FileText, to: "/reports" },
  { key: "settings", label: "Settings", icon: Settings, to: "/settings" },
];

function initialsOf(name, email) {
  const source = (name || "").trim() || (email || "").split("@")[0] || "";
  const parts = source.split(/[\s._-]+/).filter(Boolean);

  if (parts.length === 0) return "U";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();

  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

function AppShell({ active, children }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const profile = useProfileSummary(user?.id);
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const displayName = profile?.full_name || user?.email || "Account";
  const initials = initialsOf(profile?.full_name, user?.email);

  const { refs, floatingStyles, context } = useFloating({
    open: menuOpen,
    onOpenChange: setMenuOpen,
    placement: "top-start",
    middleware: [offset(8), flip({ padding: 8 }), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  const click = useClick(context);
  const dismiss = useDismiss(context);
  const role = useRole(context, { role: "menu" });

  const { getReferenceProps, getFloatingProps } = useInteractions([
    click,
    dismiss,
    role,
  ]);

  async function handleSignOut() {
    if (signingOut) return;

    setSigningOut(true);
    setMenuOpen(false);

    try {
      await logout();
    } finally {
      clearProfileSummary();
      // `replace`: the protected page must not stay in the history stack.
      navigate("/login", { replace: true });
    }
  }

  function goTo(path) {
    setMenuOpen(false);
    navigate(path);
  }

  return (
    <div className="app-shell">
      {/* ================= HEADER ================= */}
      <header className="app-topbar">
        <Link to="/dashboard" className="app-brand" aria-label="ReqIntel home">
          <div className="app-logo">R</div>

          <span className="app-brand-name">
            Req<span>Intel</span>
          </span>

          <span className="app-badge">
            <Sparkles size={13} />
            AI-POWERED
          </span>
        </Link>
      </header>

      {/* ================= BODY ================= */}
      <div className="app-body">
        {/* ================= SIDEBAR ================= */}
        <aside className="app-sidebar">
          <nav className="sidebar-navigation" aria-label="Main">
            <ul>
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;

                return (
                  <li key={item.key}>
                    <NavLink
                      to={item.to}
                      aria-current={active === item.key ? "page" : undefined}
                      className={`sidebar-item ${
                        active === item.key ? "sidebar-item-active" : ""
                      }`}
                    >
                      <Icon size={24} />
                      <span>{item.label}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </nav>

          {/* Single profile entry point */}
          <div className="sidebar-profile">
            <button
              type="button"
              ref={refs.setReference}
              {...getReferenceProps()}
              className={`sidebar-profile-trigger ${
                active === "profile" ? "sidebar-profile-active" : ""
              }`}
              aria-label={`Account menu for ${displayName}`}
            >
              <span className="profile-avatar" aria-hidden="true">
                {initials}
              </span>

              <span className="sidebar-profile-text">
                <span className="sidebar-profile-name">{displayName}</span>
                <span className="sidebar-profile-role">
                  {roleLabel(user?.role)}
                </span>
              </span>

              <ChevronUp size={14} aria-hidden="true" />
            </button>

            {menuOpen && (
              <FloatingPortal>
                <div
                  ref={refs.setFloating}
                  style={floatingStyles}
                  className="profile-dropdown"
                  {...getFloatingProps()}
                >
                  <div className="profile-dropdown-header">
                    <p className="profile-dropdown-name">{displayName}</p>
                    <p className="profile-dropdown-email">{user?.email}</p>
                  </div>

                  <button
                    type="button"
                    role="menuitem"
                    className="profile-dropdown-item"
                    onClick={() => goTo("/profile")}
                  >
                    <User size={15} />
                    My Profile
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    className="profile-dropdown-item"
                    onClick={() => goTo("/settings")}
                  >
                    <Settings size={15} />
                    Account Settings
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    className="profile-dropdown-logout"
                    onClick={handleSignOut}
                    disabled={signingOut}
                  >
                    <LogOut size={15} />
                    Sign Out
                  </button>
                </div>
              </FloatingPortal>
            )}
          </div>
        </aside>

        {/* ================= CONTENT ================= */}
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

export default AppShell;
