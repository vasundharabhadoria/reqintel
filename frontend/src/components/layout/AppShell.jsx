import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bell,
  ChevronDown,
  Folder,
  Globe,
  LayoutGrid,
  LogOut,
  Settings,
  Sparkles,
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
import "./appShell.css";

const NAV_ITEMS = [
  {
    key: "dashboard",
    label: "Dashboard",
    icon: LayoutGrid,
    to: "/dashboard",
  },
  {
    key: "projects",
    label: "Projects",
    icon: Folder,
    to: "/projects",
  },
];

function AppShell({ active, children }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);

  const { refs, floatingStyles, context } = useFloating({
    open: profileOpen,
    onOpenChange: setProfileOpen,
    placement: "bottom-end",
    middleware: [
      offset(8),
      flip({ padding: 8 }),
      shift({ padding: 8 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  const click = useClick(context);
  const dismiss = useDismiss(context);
  const role = useRole(context, { role: "menu" });

  const { getReferenceProps, getFloatingProps } =
    useInteractions([click, dismiss, role]);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">

      {/* ================= HEADER ================= */}
      <header className="app-topbar">

        <div className="app-brand">
          <div className="app-logo">
            R
          </div>

          <span className="app-brand-name">
            Req<span>Intel</span>
          </span>

          <span className="app-badge">
            <Sparkles size={13} />
            AI-POWERED
          </span>
        </div>

        <div className="app-topbar-actions">

          {/* Notifications */}
          <button
            type="button"
            className="notification-button"
            aria-label="Notifications"
          >
            <Bell size={21} />

            <span className="notification-count">
              3
            </span>
          </button>

          {/* Profile */}
          <div className="profile-menu">

            <button
              type="button"
              ref={refs.setReference}
              {...getReferenceProps()}
              className="profile-trigger"
            >
              <span className="profile-avatar">
                {user?.email?.charAt(0).toUpperCase() || "U"}
              </span>

              <span className="profile-label">
                Business Analyst
              </span>

              <ChevronDown size={15} />
            </button>

            {profileOpen && (
              <FloatingPortal>
                <div
                  ref={refs.setFloating}
                  style={floatingStyles}
                  className="profile-dropdown"
                  {...getFloatingProps()}
                >
                  <p className="profile-dropdown-email">
                    {user?.email}
                  </p>

                  <button
                    type="button"
                    role="menuitem"
                    className="profile-dropdown-logout"
                    onClick={handleLogout}
                  >
                    <LogOut size={15} />
                    Logout
                  </button>
                </div>
              </FloatingPortal>
            )}
          </div>

          {/* Language */}
          <button
            type="button"
            className="lang-selector"
          >
            <Globe size={19} />
            <span>English</span>
            <ChevronDown size={15} />
          </button>

        </div>
      </header>

      {/* ================= BODY ================= */}
      <div className="app-body">

        {/* ================= SIDEBAR ================= */}
        <aside className="app-sidebar">

          <nav className="sidebar-navigation">
            <ul>
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;

                return (
                  <li key={item.key}>
                    <Link
                      to={item.to}
                      className={`sidebar-item ${
                        active === item.key
                          ? "sidebar-item-active"
                          : ""
                      }`}
                    >
                      <Icon size={24} />
                      <span>{item.label}</span>
                    </Link>
                  </li>
                );
              })}

              {/* Settings */}
              <li>
                <button
                  type="button"
                  className="sidebar-item"
                  onClick={() => navigate("/settings")}
                >
                  <Settings size={24} />
                  <span>Settings</span>
                </button>
              </li>
            </ul>
          </nav>

          {/* Logout */}
          <button
            type="button"
            className="sidebar-item sidebar-logout"
            onClick={handleLogout}
          >
            <LogOut size={24} />
            <span>Logout</span>
          </button>

        </aside>

        {/* ================= CONTENT ================= */}
        <main className="app-content">
          {children}
        </main>

      </div>

    </div>
  );
}

export default AppShell;