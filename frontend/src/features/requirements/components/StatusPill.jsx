function StatusPill({ status }) {
  return <span className={`req-status-pill req-status-${status}`}>{status}</span>;
}

export default StatusPill;