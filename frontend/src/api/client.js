import { getAccessToken } from "./tokenStorage";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function apiRequest(endpoint, options = {}) {
  const token = getAccessToken();
  const isFormData = options.body instanceof FormData;
  const expectBlob = options.responseType === "blob";

  let response;

  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Unable to connect to the server.");
  }

  if (expectBlob) {
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      let errorMessage = "Something went wrong. Please try again.";

      if (typeof data?.detail === "string") {
        errorMessage = data.detail;
      } else if (Array.isArray(data?.detail)) {
        errorMessage = data.detail.map((error) => error.msg).join(", ");
      }

      const error = new Error(errorMessage);
      error.status = response.status;
      throw error;
    }

    return await response.blob();
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    let errorMessage = "Something went wrong. Please try again.";

    if (typeof data?.detail === "string") {
      errorMessage = data.detail;
    } else if (Array.isArray(data?.detail)) {
      errorMessage = data.detail.map((error) => error.msg).join(", ");
    }

    const error = new Error(errorMessage);
    error.status = response.status;
    throw error;
  }

  return data;
}

