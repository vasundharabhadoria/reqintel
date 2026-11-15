import { useCallback, useEffect, useState } from "react";

// Counts down from `start()` so "resend" buttons cannot be hammered.
export function useCooldown(seconds = 60) {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (remaining <= 0) {
      return undefined;
    }

    const timer = setTimeout(() => setRemaining((value) => value - 1), 1000);

    return () => clearTimeout(timer);
  }, [remaining]);

  const start = useCallback(
    (override) => setRemaining(override ?? seconds),
    [seconds]
  );

  return { remaining, start };
}
