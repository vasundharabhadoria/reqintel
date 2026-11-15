import { Check, Circle } from "lucide-react";

import { passwordChecks } from "../validation";

function PasswordChecklist({ password }) {
  return (
    <ul className="auth-password-checklist" aria-label="Password requirements">
      {passwordChecks(password).map((check) => (
        <li
          key={check.id}
          className={check.passed ? "auth-check-met" : "auth-check-unmet"}
        >
          {check.passed ? <Check size={13} /> : <Circle size={13} />}
          {check.label}
        </li>
      ))}
    </ul>
  );
}

export default PasswordChecklist;
