import { useCallback, useState } from "react";
import { CheckCircle2, X, XCircle } from "lucide-react";

import { ToastContext } from "./ToastContextObject";
import "../components/common/toast.css";

let idCounter = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismissToast = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message, type = "success") => {
      const id = ++idCounter;
      setToasts((current) => [...current, { id, message, type }]);
      setTimeout(() => dismissToast(id), 4000);
    },
    [dismissToast]
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}

      <div className="toast-viewport">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.type}`}>
            {toast.type === "error" ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
            <span>{toast.message}</span>
            <button
              type="button"
              className="toast-close"
              onClick={() => dismissToast(toast.id)}
              aria-label="Dismiss notification"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}