const STATUS_LABELS = {
  active: "Active",
  archived: "Archived",
  suspended: "Suspended",
};

function StatusBadge({ status }) {
  return (
    <span className={`status-badge status-badge-${status}`}>
      <span className="status-badge-dot" />
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export default StatusBadge;