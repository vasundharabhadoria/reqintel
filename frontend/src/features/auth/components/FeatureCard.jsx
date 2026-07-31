function FeatureCard({ icon, title, description }) {
  return (
    <div className="auth-feature-card">
      <div className="auth-feature-icon">{icon}</div>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default FeatureCard;