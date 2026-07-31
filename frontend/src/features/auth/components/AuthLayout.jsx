import { Globe, ShieldCheck } from "lucide-react";

import AuthHero from "./AuthHero";

function AuthLayout({ children }) {
  return (
    <div className="auth-page">
      <div className="auth-language-selector">
        <Globe size={16} />
        English
      </div>

      <div className="auth-panels">
        <AuthHero />

        <section className="auth-form-section">{children}</section>
      </div>

      <div className="auth-security-note">
        <ShieldCheck size={14} />
        Your data is secure with us
      </div>
    </div>
  );
}

export default AuthLayout;