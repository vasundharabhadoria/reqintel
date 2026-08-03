import { useState } from "react";
import { Eye, EyeOff, Lock } from "lucide-react";

function PasswordInput({
  id,
  label,
  value,
  onChange,
  placeholder,
  autoComplete = "current-password",
  minLength,
  maxLength,
}) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>

      <div className="auth-input-wrapper">
        <Lock size={18} className="auth-input-icon" />

        <input
          id={id}
          name={id}
          type={visible ? "text" : "password"}
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          required
          minLength={minLength}
          maxLength={maxLength}
          autoComplete={autoComplete}
        />

        <button
          type="button"
          className="auth-password-toggle"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>
    </div>
  );
}

export default PasswordInput;