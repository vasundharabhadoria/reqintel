import {
  FileText,
  Clock3,
  CheckCircle2,
  XCircle,
  Sparkles,
  AlertTriangle,
} from "lucide-react";

function RuleStatsCards({ stats }) {
  const cards = [
    {
      label: "Total Requirements",
      value: stats.total,
      icon: FileText,
      color: "purple",
    },
    {
      label: "Pending Review",
      value: stats.pending,
      note:
        stats.drafts > 0
          ? `${stats.drafts} draft${stats.drafts === 1 ? "" : "s"} awaiting analysis`
          : null,
      icon: Clock3,
      color: "orange",
    },
    {
      label: "Approved",
      value: stats.approved,
      icon: CheckCircle2,
      color: "green",
    },
    {
      label: "Rejected",
      value: stats.rejected,
      icon: XCircle,
      color: "red",
    },
    {
      label: "AI Suggestions",
      value: stats.aiSuggestions,
      icon: Sparkles,
      color: "blue",
    },
    {
      label: "Issues Found",
      value: stats.issues,
      icon: AlertTriangle,
      color: "cyan",
    },
  ];

  return (
    <div className="rule-stats-grid">
      {cards.map((card) => {
        const Icon = card.icon;

        return (
          <div
            className={`rule-stat-card rule-stat-card-${card.color}`}
            key={card.label}
          >
            <div className="rule-stat-icon">
              <Icon size={21} />
            </div>

            <div className="rule-stat-info">
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              {card.note && (
                <small className="rule-stat-note">{card.note}</small>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default RuleStatsCards;