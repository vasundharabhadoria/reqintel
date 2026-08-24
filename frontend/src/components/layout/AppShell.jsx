import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bell,
  ChevronDown,
  FileBarChart,
  FileText,
  Folder,
  Globe,
  LayoutGrid,
  LogOut,
  Settings,
  Sparkles,
} from "lucide-react";

import { useAuth } from "../../hooks/useAuth";
import "./appShell.css";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: LayoutGrid, to: "/dashboard", enabled: true },
  { key: "projects", label: "Projects", icon: Folder, to: "/projects", enabled: true },
  { key: "requirements", label: "Requirements", icon: FileText, to: null, enabled: false },
  { key: "reports", label: "Reports", icon: FileBarChart, to: null, enabled: false },
  { key: "settings", label: "Settings", icon: Settings, to: null, enabled: false },
];

function AppShell({ active, children }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);

  useEffect(() => {
    if (!profileOpen) return undefined;

    function handleClickOutside(event) {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setProfileOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [profileOpen]);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-brand">
          <span className="app-logo">R</span>
          <span className="app-brand-name">ReqIntel</span>
          <span className="app-badge">
            <Sparkles size={12} /> AI-POWERED
          </span>
        </div>

        <div className="app-topbar-actions">
          <button type="button" className="icon-button" aria-label="Notifications">
            <Bell size={18} />
          </button>

          <div className="lang-selector">
            <Globe size={16} />
            <span>English</span>
            <ChevronDown size={14} />
          </div>

          <div className="profile-menu" ref={profileRef}>
            <button
              type="button"
              className="profile-trigger"
              onClick={() => setProfileOpen((current) => !current)}
            >
              <span className="profile-avatar">
                {user?.email?.charAt(0).toUpperCase() || "U"}
              </span>
              <span className="profile-label">Business Analyst</span>
              <ChevronDown size={14} />
            </button>

            {profileOpen && (
              <div className="profile-dropdown">
                <p className="profile-dropdown-email">{user?.email}</p>
                <button
                  type="button"
                  className="profile-dropdown-logout"
                  onClick={handleLogout}
                >
                  <LogOut size={14} /> Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="app-body">
        <nav className="app-sidebar">
          <ul>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;

              if (!item.enabled) {
                return (
                  <li key={item.key}>
                    <span className="sidebar-item sidebar-item-disabled" title="Coming soon">
                      <Icon size={18} />
                      {item.label}
                    </span>
                  </li>
                );
              }

              return (
                <li key={item.key}>
                  <Link
                    to={item.to}
                    className={`sidebar-item ${active === item.key ? "sidebar-item-active" : ""}`}
                  >
                    <Icon size={18} />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          <button type="button" className="sidebar-item sidebar-logout" onClick={handleLogout}>
            <LogOut size={18} />
            Logout
          </button>
        </nav>

        <main className="app-content">{children}</main>
      </div>

      <footer className="app-footer">
        <span>© 2026 ReqIntel Technologies. All rights reserved.</span>
        <span>Version 1.0.0</span>
        <span>Your data is secure with us</span>
      </footer>
    </div>
  );
}

export default AppShell;