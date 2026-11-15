import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/authApi", () => ({
  resendConfirmation: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  getOAuthUrl: vi.fn(),
}));

import * as authApi from "../../../api/authApi";
import { renderWithAuth } from "../../../test/renderWithAuth";
import { saveOAuthFlow } from "../pkce";
import AuthCallbackPage from "./AuthCallbackPage";
import ForgotPasswordPage from "./ForgotPasswordPage";
import LoginPage from "./LoginPage";
import RegisterPage from "./RegisterPage";
import ResetPasswordPage from "./ResetPasswordPage";

beforeEach(() => {
  vi.resetAllMocks();
});

const dest = [
  <Route key="dash" path="/dashboard" element={<p>DASHBOARD PAGE</p>} />,
  <Route key="login" path="/login" element={<p>LOGIN ROUTE</p>} />,
  <Route key="forgot" path="/forgot-password" element={<p>FORGOT ROUTE</p>} />,
];

describe("LoginPage", () => {
  async function fill(user, email = "a@b.com", password = "Secret123") {
    await user.type(screen.getByLabelText("Email Address"), email);
    await user.type(screen.getByLabelText("Password"), password);
  }

  it("offers Forgot Password, Google and GitHub, and no Microsoft", () => {
    renderWithAuth(<LoginPage />, { route: "/login", path: "/login" });

    expect(screen.getByRole("link", { name: "Forgot Password?" })).toHaveAttribute("href", "/forgot-password");
    expect(screen.getByRole("button", { name: /Continue with Google/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Continue with GitHub/ })).toBeEnabled();
    expect(screen.queryByText(/Microsoft/i)).not.toBeInTheDocument();
  });

  it("validates the email client-side without calling login", async () => {
    const login = vi.fn();
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />, { auth: { login }, route: "/login", path: "/login" });

    await fill(user, "not-an-email");
    await user.click(screen.getByRole("button", { name: /^Login/ }));

    expect(screen.getByRole("alert")).toHaveTextContent("valid email");
    expect(login).not.toHaveBeenCalled();
  });

  it("passes the Remember me choice to login and lands on the dashboard", async () => {
    const login = vi.fn().mockResolvedValue({ role: "business_analyst" });
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />, { auth: { login }, route: "/login", path: "/login", extraRoutes: dest });

    await fill(user);
    await user.click(screen.getByLabelText("Remember me"));
    await user.click(screen.getByRole("button", { name: /^Login/ }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("a@b.com", "Secret123", true));
    expect(await screen.findByText("DASHBOARD PAGE")).toBeInTheDocument();
  });

  it("without Remember me, login is session-only", async () => {
    const login = vi.fn().mockResolvedValue({ role: "business_analyst" });
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />, { auth: { login }, route: "/login", path: "/login", extraRoutes: dest });

    await fill(user);
    await user.click(screen.getByRole("button", { name: /^Login/ }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("a@b.com", "Secret123", false));
  });

  it("shows the generic backend error and keeps the form usable", async () => {
    const login = vi.fn().mockRejectedValue(Object.assign(new Error("Invalid email or password."), { status: 401 }));
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />, { auth: { login }, route: "/login", path: "/login" });

    await fill(user);
    await user.click(screen.getByRole("button", { name: /^Login/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(screen.getByRole("button", { name: /^Login/ })).toBeEnabled();
  });

  it("an unconfirmed account gets a resend-confirmation button", async () => {
    const login = vi.fn().mockRejectedValue(
      Object.assign(new Error("Please confirm your email address before signing in."), { status: 403, code: "email_not_confirmed" })
    );
    authApi.resendConfirmation.mockResolvedValue({ message: "A new confirmation link has been sent." });
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />, { auth: { login }, route: "/login", path: "/login" });

    await fill(user);
    await user.click(screen.getByRole("button", { name: /^Login/ }));
    await user.click(await screen.findByRole("button", { name: "Resend confirmation email" }));

    expect(authApi.resendConfirmation).toHaveBeenCalledWith("a@b.com");
    expect(await screen.findByRole("status")).toHaveTextContent("confirmation link");
  });

  it("shows the notice passed from the confirmation / reset pages", () => {
    renderWithAuth(<LoginPage />, {
      route: { pathname: "/login", state: { notice: "Email confirmed. You can now sign in." } },
      path: "/login",
    });

    expect(screen.getByRole("status")).toHaveTextContent("Email confirmed");
  });

  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />, { route: "/login", path: "/login" });

    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(input).toHaveAttribute("type", "text");
  });

  it("starts a PKCE OAuth flow without any secret and redirects to the provider URL", async () => {
    authApi.getOAuthUrl.mockResolvedValue({ url: "https://proj.supabase.co/auth/v1/authorize?provider=google" });
    const assign = vi.fn();
    const realLocation = window.location;

    // jsdom cannot navigate; swap in a stand-in and ALWAYS restore the real
    // location so later tests see the real URL.
    Object.defineProperty(window, "location", {
      value: { assign },
      writable: true,
      configurable: true,
    });

    try {
      const user = userEvent.setup();
      renderWithAuth(<LoginPage />, { route: "/login", path: "/login" });

      await user.click(screen.getByLabelText("Remember me"));
      await user.click(screen.getByRole("button", { name: /Continue with Google/ }));

      await waitFor(() => expect(assign).toHaveBeenCalled());
      const [provider, challenge] = authApi.getOAuthUrl.mock.calls[0];
      expect(provider).toBe("google");
      expect(challenge).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(assign).toHaveBeenCalledWith("https://proj.supabase.co/auth/v1/authorize?provider=google");

      const flow = JSON.parse(sessionStorage.getItem("reqintel_oauth_flow"));
      expect(flow.verifier).toMatch(/^[A-Za-z0-9_-]{64}$/);
      expect(flow.remember).toBe(true);
      expect(JSON.stringify(flow)).not.toMatch(/secret/i);
    } finally {
      Object.defineProperty(window, "location", {
        value: realLocation,
        writable: true,
        configurable: true,
      });
    }
  });
});

describe("RegisterPage", () => {
  async function fillValid(user, over = {}) {
    const v = { name: "Ada Lovelace", email: "ada@example.com", pw: "Longenough1", ...over };
    await user.type(screen.getByLabelText("Full Name"), v.name);
    await user.type(screen.getByLabelText("Email Address"), v.email);
    await user.type(screen.getByLabelText("Password"), v.pw);
    await user.type(screen.getByLabelText("Confirm Password"), over.confirm ?? v.pw);
    await user.click(screen.getByLabelText(/Terms and Conditions/));
  }

  it("limits the full name to the 150 characters the database allows", () => {
    renderWithAuth(<RegisterPage />, { route: "/register", path: "/register" });
    expect(screen.getByLabelText("Full Name")).toHaveAttribute("maxLength", "150");
  });

  it("blocks a weak password and never calls the API", async () => {
    const register = vi.fn();
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage />, { auth: { register }, route: "/register", path: "/register" });

    await fillValid(user, { pw: "alllowercase1" });
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/uppercase/i);
    expect(register).not.toHaveBeenCalled();
  });

  it("blocks mismatched passwords, invalid email and unchecked terms", async () => {
    const register = vi.fn();
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage />, { auth: { register }, route: "/register", path: "/register" });

    await fillValid(user, { confirm: "Different1x" });
    await user.click(screen.getByRole("button", { name: "Create Account" }));
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(register).not.toHaveBeenCalled();
  });

  it("shows live password requirements", async () => {
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage />, { route: "/register", path: "/register" });

    const list = screen.getByRole("list", { name: "Password requirements" });
    expect(list.querySelectorAll(".auth-check-met")).toHaveLength(0);

    await user.type(screen.getByLabelText("Password"), "Abcdefg1");
    expect(list.querySelectorAll(".auth-check-met")).toHaveLength(4);
  });

  it("success shows check-your-email (not 'redirecting'), never sends confirmPassword, and can resend", async () => {
    const register = vi.fn().mockResolvedValue({ message: "sent" });
    authApi.resendConfirmation.mockResolvedValue({ message: "A new confirmation link has been sent." });
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage />, { auth: { register }, route: "/register", path: "/register" });

    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(register).toHaveBeenCalledWith("Ada Lovelace", "ada@example.com", "Longenough1");
    expect(screen.getByRole("button", { name: /Resend available in/ })).toBeDisabled(); // cooldown
  });

  it("surfaces backend errors", async () => {
    const register = vi.fn().mockRejectedValue(Object.assign(new Error("Too many emails were requested."), { status: 429 }));
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage />, { auth: { register }, route: "/register", path: "/register" });

    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many emails");
  });
});

describe("ForgotPasswordPage", () => {
  it("validates the email, then shows the generic confirmation", async () => {
    authApi.forgotPassword.mockResolvedValue({ message: "If an account exists for this email address, a password reset link has been sent." });
    const user = userEvent.setup();
    renderWithAuth(<ForgotPasswordPage />, { route: "/forgot-password", path: "/forgot-password" });

    await user.type(screen.getByLabelText("Email Address"), "nope");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByRole("alert")).toHaveTextContent("valid email");
    expect(authApi.forgotPassword).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Email Address"));
    await user.type(screen.getByLabelText("Email Address"), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(authApi.forgotPassword).toHaveBeenCalledWith("ada@example.com");
    expect(await screen.findByRole("status")).toHaveTextContent("If an account exists");
    expect(screen.getByRole("button", { name: /Send again in/ })).toBeDisabled();
  });
});

describe("ResetPasswordPage", () => {
  const withHash = (hash) => window.history.replaceState(null, "", `/reset-password${hash}`);

  it("without a recovery token it shows an invalid-link state", () => {
    renderWithAuth(<ResetPasswordPage />, { route: "/reset-password", path: "/reset-password" });

    expect(screen.getByRole("heading", { name: "Invalid reset link" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
  });

  it("an expired link (otp_expired) says so", () => {
    withHash("#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired");
    renderWithAuth(<ResetPasswordPage />, { route: "/reset-password", path: "/reset-password" });

    expect(screen.getByRole("heading", { name: "This link has expired" })).toBeInTheDocument();
  });

  it("a token that is not a recovery token is rejected", () => {
    withHash("#access_token=abc&type=signup");
    renderWithAuth(<ResetPasswordPage />, { route: "/reset-password", path: "/reset-password" });

    expect(screen.getByRole("heading", { name: "Invalid reset link" })).toBeInTheDocument();
  });

  it("valid link: strips the token from the URL, updates the password, then offers login", async () => {
    withHash("#access_token=recovery-jwt&refresh_token=x&type=recovery");
    authApi.resetPassword.mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    renderWithAuth(<ResetPasswordPage />, { route: "/reset-password", path: "/reset-password", extraRoutes: dest });

    expect(window.location.hash).toBe(""); // token removed from address bar

    await user.type(screen.getByLabelText("New Password"), "BrandNew1pass");
    await user.type(screen.getByLabelText("Confirm New Password"), "BrandNew1pass");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(authApi.resetPassword).toHaveBeenCalledWith("recovery-jwt", "BrandNew1pass");
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go to login" }));
    expect(await screen.findByText("LOGIN ROUTE")).toBeInTheDocument();
  });

  it("enforces the policy and matching passwords before calling the API", async () => {
    withHash("#access_token=recovery-jwt&type=recovery");
    const user = userEvent.setup();
    renderWithAuth(<ResetPasswordPage />, { route: "/reset-password", path: "/reset-password" });

    await user.type(screen.getByLabelText("New Password"), "weak");
    await user.type(screen.getByLabelText("Confirm New Password"), "weak");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("New Password"));
    await user.type(screen.getByLabelText("New Password"), "BrandNew1pass");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(authApi.resetPassword).not.toHaveBeenCalled();
  });

  it("shows the backend message when the link was already used", async () => {
    withHash("#access_token=used-jwt&type=recovery");
    authApi.resetPassword.mockRejectedValue(new Error("This reset link is invalid or has expired. Request a new one."));
    const user = userEvent.setup();
    renderWithAuth(<ResetPasswordPage />, { route: "/reset-password", path: "/reset-password" });

    await user.type(screen.getByLabelText("New Password"), "BrandNew1pass");
    await user.type(screen.getByLabelText("Confirm New Password"), "BrandNew1pass");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
  });
});

describe("AuthCallbackPage", () => {
  const open = (url) => window.history.replaceState(null, "", url);
  const render_ = (auth) => renderWithAuth(<AuthCallbackPage />, { auth, route: "/auth/callback", path: "/auth/callback", extraRoutes: dest });

  it("completes an OAuth sign-in with the stored PKCE verifier, once", async () => {
    open("/auth/callback?code=oauth-code");
    saveOAuthFlow({ verifier: "v".repeat(64), remember: true, provider: "github" });
    const loginWithOAuthCode = vi.fn().mockResolvedValue({ role: "business_analyst" });

    render_({ loginWithOAuthCode });

    expect(await screen.findByText("DASHBOARD PAGE")).toBeInTheDocument();
    expect(loginWithOAuthCode).toHaveBeenCalledTimes(1);
    expect(loginWithOAuthCode).toHaveBeenCalledWith("oauth-code", "v".repeat(64), true);
    expect(sessionStorage.getItem("reqintel_oauth_flow")).toBeNull(); // single use
    expect(window.location.search).toBe(""); // code removed from the URL
  });

  it("refuses a callback this browser did not start (no stored verifier)", async () => {
    open("/auth/callback?code=stolen-code");
    const loginWithOAuthCode = vi.fn();

    render_({ loginWithOAuthCode });

    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
    expect(loginWithOAuthCode).not.toHaveBeenCalled();
  });

  it("shows the backend message when the exchange fails", async () => {
    open("/auth/callback?code=c");
    saveOAuthFlow({ verifier: "v".repeat(64), remember: false, provider: "google" });
    const loginWithOAuthCode = vi.fn().mockRejectedValue(new Error("This account has been deactivated."));

    render_({ loginWithOAuthCode });

    expect(await screen.findByText("This account has been deactivated.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to login" })).toBeInTheDocument();
  });

  it("cancelled sign-in (access_denied) is explained", () => {
    open("/auth/callback?error=access_denied&error_description=User+denied");
    render_({});
    expect(screen.getByText(/cancelled/i)).toBeInTheDocument();
  });

  it("a provider account with no usable email (trigger failure) gets a clear hint", () => {
    open("/auth/callback?error=server_error&error_description=Database+error+saving+new+user");
    render_({});
    expect(screen.getByText(/verified email address/i)).toBeInTheDocument();
  });

  it("never displays arbitrary error text taken from the URL", () => {
    open("/auth/callback?error=weird&error_description=%3Cb%3Eclick+evil.example%3C%2Fb%3E");
    render_({});

    expect(screen.queryByText(/evil\.example/)).not.toBeInTheDocument();
    expect(screen.getByText(/could not be completed/i)).toBeInTheDocument();
  });

  it("email confirmation redirect: shows success and discards the tokens in the URL", () => {
    open("/auth/callback#access_token=confirm-jwt&refresh_token=r&type=signup");
    render_({});

    expect(screen.getByRole("heading", { name: "Email confirmed" })).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("access_token")).toBeNull();
  });

  it("expired confirmation link is explained", () => {
    open("/auth/callback#error=access_denied&error_code=otp_expired");
    render_({});
    expect(screen.getByText(/link has expired/i)).toBeInTheDocument();
  });

  it("opened with nothing to process, it goes to login", async () => {
    open("/auth/callback");
    render_({});
    expect(await screen.findByText("LOGIN ROUTE")).toBeInTheDocument();
  });

  it.each([
    ["bad_oauth_state", /invalid or expired/i],
    ["flow_state_expired", /expired/i],
    ["provider_email_needs_verification", /isn't verified/i],
    ["email_exists", /already registered with another sign-in method/i],
    ["signup_disabled", /disabled/i],
  ])("maps the provider/Supabase error code %s to a fixed, friendly message", (code, expected) => {
    open(`/auth/callback?error=server_error&error_code=${code}`);
    render_({});
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("GitHub account whose email could not be read gets the email hint", () => {
    open("/auth/callback?error=server_error&error_description=Error+getting+user+email+from+external+provider");
    render_({});
    expect(screen.getByText(/verified email address/i)).toBeInTheDocument();
    expect(screen.getByText(/primary email/i)).toBeInTheDocument();
  });
});
