import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";

import { useAuth } from "../../../hooks/useAuth";
function DashboardPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <main
      style={{
        padding: 40,
        fontFamily: "Segoe UI, Roboto, Arial, sans-serif",
      }}
    >
      <h1>ReqIntel Dashboard</h1>
      <p>Welcome to ReqIntel.</p>
      <p>Logged in as: {user?.email}</p>

      <button
        type="button"
        onClick={handleLogout}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 16px",
          background: "#1c64f2",
          color: "#fff",
          border: "none",
          borderRadius: 8,
          cursor: "pointer",
          fontSize: 14,
          fontWeight: 600,
        }}
      >
        <LogOut size={16} />
        Logout
      </button>
    </main>
  );
}

export default DashboardPage;