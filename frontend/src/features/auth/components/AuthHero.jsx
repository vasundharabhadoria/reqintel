import { BarChart3, Brain, GitBranch, ShieldCheck, Sparkles } from "lucide-react";

import FeatureCard from "./FeatureCard";
import heroArt from "../../../assets/hero.png";

function AuthHero() {
  return (
    <section className="auth-hero">
      <div className="auth-brand">
        <span className="auth-logo">R</span>
        <span className="auth-brand-name">ReqIntel</span>
      </div>

      <span className="auth-badge">
        <Sparkles size={14} />
        AI-POWERED
      </span>

      <h1 className="auth-hero-heading">
        AI-Powered Enterprise
        <br />
        Requirement <span className="auth-highlight">Intelligence</span> Platform
      </h1>

      <h2 className="auth-hero-subheading">
        Transform Requirements into
        <br />
        Actionable Intelligence
      </h2>

      <p className="auth-hero-description">
        ReqIntel helps business analysts analyze, validate, and manage
        software requirements with AI-assisted insights and end-to-end
        traceability.
      </p>

      <div className="auth-feature-grid">
        <FeatureCard
          icon={<Brain size={20} />}
          title="AI Analysis"
          description="Extract insights and detect gaps using advanced AI."
        />
        <FeatureCard
          icon={<ShieldCheck size={20} />}
          title="Smart Validation"
          description="Rule-based validation ensures quality and consistency."
        />
        <FeatureCard
          icon={<GitBranch size={20} />}
          title="End-to-End Traceability"
          description="Trace requirements across their entire lifecycle."
        />
        <FeatureCard
          icon={<BarChart3 size={20} />}
          title="Intelligent Reports"
          description="Generate actionable reports and dashboards instantly."
        />
      </div>

      <div className="auth-hero-illustration">
        <img src={heroArt} alt="" className="auth-hero-illustration-accent" />

        <div className="auth-mock-card">
          <div className="auth-mock-row">
            <span>Requirements</span>
            <strong>1,248</strong>
          </div>
          <div className="auth-mock-row">
            <span>Validated</span>
            <strong>842</strong>
          </div>
          <div className="auth-mock-row">
            <span>Issues Found</span>
            <strong>126</strong>
          </div>
          <div className="auth-mock-bars">
            <span style={{ height: "40%" }} />
            <span style={{ height: "65%" }} />
            <span style={{ height: "50%" }} />
            <span style={{ height: "85%" }} />
            <span style={{ height: "60%" }} />
          </div>
        </div>
      </div>

      <div className="auth-hero-footer">
        <span>© 2026 ReqIntel Technologies. All rights reserved.</span>
        <span>Version 1.0.0</span>
      </div>
    </section>
  );
}

export default AuthHero;