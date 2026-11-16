import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/profileApi", () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  deleteAccount: vi.fn(),
}));

import * as profileApi from "../../../api/profileApi";
import { renderWithAuth } from "../../../test/renderWithAuth";
import ProfilePage from "./ProfilePage";

const emailProfile = {
  id: "11111111-2222-3333-4444-555555555555",
  email: "asha@example.com",
  full_name: "Asha Verma",
  role: "business_analyst",
  is_active: true,
  created_at: "2026-03-14T10:00:00Z",
  last_login_at: null,
  auth_provider: "email",
  providers: ["email"],
  reauth_method: "password",
};

const googleProfile = {
  ...emailProfile,
  auth_provider: "google",
  providers: ["google"],
  reauth_method: "recent_login",
};

function LoginProbe() {
  const location = useLocation();
  return <p>LOGIN PAGE {location.state?.notice || ""}</p>;
}

const loginRoute = [<Route key="login" path="/login" element={<LoginProbe />} />];

let logout;
let endSession;

function renderPage(profile = emailProfile) {
  profileApi.getProfile.mockResolvedValue(profile);
  logout = vi.fn().mockResolvedValue(undefined);
  endSession = vi.fn();

  return renderWithAuth(<ProfilePage />, {
    auth: {
      user: { id: profile.id, email: profile.email, role: profile.role },
      isAuthenticated: true,
      logout,
      endSession,
    },
    route: "/profile",
    path: "/profile",
    extraRoutes: loginRoute,
  });
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("ProfilePage - display", () => {
  it("shows the real account details from the API", async () => {
    renderPage();

    expect(await screen.findByText("Asha Verma")).toBeInTheDocument();
    expect(screen.getByText("asha@example.com", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getAllByText("Business Analyst").length).toBeGreaterThan(0);
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(emailProfile.id)).toBeInTheDocument();
    expect(screen.getByText(/March 14, 2026|14 March 2026/)).toBeInTheDocument();
    expect(screen.getByText("Email & password")).toBeInTheDocument();
    expect(profileApi.getProfile).toHaveBeenCalledTimes(1);
  });

  it("shows an inactive status and the OAuth provider", async () => {
    renderPage({ ...googleProfile, is_active: false });

    expect(await screen.findByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("Google", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/managed by Google/)).toBeInTheDocument();
  });

  it("shows a loading state and then an error with a working retry", async () => {
    profileApi.getProfile
      .mockRejectedValueOnce(new Error("Unable to connect to the server."))
      .mockResolvedValueOnce(emailProfile);

    renderWithAuth(<ProfilePage />, {
      auth: { user: { email: "a@b.com", role: "business_analyst" }, isAuthenticated: true },
      route: "/profile",
      path: "/profile",
    });

    expect(screen.getByText("Loading your profile...")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to connect");

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Asha Verma")).toBeInTheDocument();
    expect(profileApi.getProfile).toHaveBeenCalledTimes(2);
  });
});

describe("ProfilePage - edit", () => {
  it("saves a trimmed full name and keeps the email read-only", async () => {
    const user = userEvent.setup();
    profileApi.updateProfile.mockResolvedValue({ ...emailProfile, full_name: "Asha K Verma" });
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Edit Profile/ }));

    // email is shown but is never an editable field
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getByText("asha@example.com")).toBeInTheDocument();

    const input = screen.getByLabelText("Full name");
    await user.clear(input);
    await user.type(input, "  Asha   K Verma ");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    // only the name is sent, normalised
    expect(profileApi.updateProfile).toHaveBeenCalledWith("Asha K Verma");
    expect(await screen.findByRole("status")).toHaveTextContent("Profile updated successfully.");
    expect(screen.getByText("Asha K Verma")).toBeInTheDocument();
  });

  it("rejects an invalid name without calling the API", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Edit Profile/ }));
    const input = screen.getByLabelText("Full name");
    await user.clear(input);
    await user.type(input, "A");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("at least 2 characters");
    expect(profileApi.updateProfile).not.toHaveBeenCalled();
  });

  it("keeps the form open and shows the server error when saving fails", async () => {
    const user = userEvent.setup();
    profileApi.updateProfile.mockRejectedValue(new Error("Full name contains invalid characters."));
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Edit Profile/ }));
    await user.type(screen.getByLabelText("Full name"), "x");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid characters");
    expect(screen.getByLabelText("Full name")).toBeInTheDocument();
    expect(screen.queryByText("Profile updated successfully.")).not.toBeInTheDocument();
  });

  it("cancel discards the edit", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Edit Profile/ }));
    await user.type(screen.getByLabelText("Full name"), " changed");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(profileApi.updateProfile).not.toHaveBeenCalled();
    expect(screen.getByText("Asha Verma")).toBeInTheDocument();
  });
});

describe("ProfilePage - sign out", () => {
  it("calls logout and returns to the login page", async () => {
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^Sign Out/ }));

    await waitFor(() => expect(screen.getByText(/LOGIN PAGE/)).toBeInTheDocument());
    expect(logout).toHaveBeenCalledTimes(1);
  });
});

describe("ProfilePage - delete account", () => {
  async function openDialog(profile) {
    const user = userEvent.setup();
    renderPage(profile);
    await user.click(await screen.findByRole("button", { name: "Delete Account" }));
    return { user, dialog: screen.getByRole("dialog") };
  }

  const finalButton = (dialog) =>
    within(dialog).getByRole("button", { name: /Permanently Delete Account/ });

  it("explains what is deleted and keeps the final button disabled", async () => {
    const { dialog } = await openDialog();

    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(within(dialog).getByText(/All projects you own/)).toBeInTheDocument();
    expect(within(dialog).getByText(/anonymised audit trail/)).toBeInTheDocument();
    expect(finalButton(dialog)).toBeDisabled();
  });

  it("requires the exact word DELETE and the password", async () => {
    const { user, dialog } = await openDialog();
    const word = within(dialog).getByLabelText(/Type/);
    const password = within(dialog).getByLabelText("Confirm your password");

    await user.type(password, "Secret123");
    await user.type(word, "delete");
    expect(finalButton(dialog)).toBeDisabled();

    await user.clear(word);
    await user.type(word, "DELETE");
    expect(finalButton(dialog)).toBeEnabled();

    await user.clear(password);
    expect(finalButton(dialog)).toBeDisabled();
  });

  it("cancelling deletes nothing and a reopened dialog starts empty", async () => {
    const { user, dialog } = await openDialog();

    await user.type(within(dialog).getByLabelText(/Type/), "DELETE");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(profileApi.deleteAccount).not.toHaveBeenCalled();
    expect(endSession).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete Account" }));
    expect(within(screen.getByRole("dialog")).getByLabelText(/Type/)).toHaveValue("");
  });

  it("deletes, clears the session and lands on login with a confirmation", async () => {
    profileApi.deleteAccount.mockResolvedValue({ projects_deleted: 2 });
    const { user, dialog } = await openDialog();

    await user.type(within(dialog).getByLabelText("Confirm your password"), "Secret123");
    await user.type(within(dialog).getByLabelText(/Type/), "DELETE");
    await user.click(finalButton(dialog));

    await waitFor(() =>
      expect(screen.getByText(/LOGIN PAGE/)).toHaveTextContent("permanently deleted")
    );
    expect(profileApi.deleteAccount).toHaveBeenCalledWith({ password: "Secret123" });
    expect(endSession).toHaveBeenCalledTimes(1);
    expect(logout).not.toHaveBeenCalled(); // the account is gone: nothing to revoke
  });

  it("shows the error, stays signed in and keeps the dialog on failure", async () => {
    profileApi.deleteAccount.mockRejectedValue(
      Object.assign(new Error("The password you entered is incorrect."), { code: "reauth_failed" })
    );
    const { user, dialog } = await openDialog();

    await user.type(within(dialog).getByLabelText("Confirm your password"), "wrong");
    await user.type(within(dialog).getByLabelText(/Type/), "DELETE");
    await user.click(finalButton(dialog));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("password you entered");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(endSession).not.toHaveBeenCalled();
    expect(screen.queryByText(/LOGIN PAGE/)).not.toBeInTheDocument();
    // the user can fix it and try again
    expect(finalButton(dialog)).toBeEnabled();
  });

  it("blocks double submission while the request is running", async () => {
    let resolve;
    profileApi.deleteAccount.mockReturnValue(new Promise((r) => (resolve = r)));
    const { user, dialog } = await openDialog();

    await user.type(within(dialog).getByLabelText("Confirm your password"), "Secret123");
    await user.type(within(dialog).getByLabelText(/Type/), "DELETE");
    await user.click(finalButton(dialog));

    expect(within(dialog).getByRole("button", { name: "Deleting..." })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(profileApi.deleteAccount).toHaveBeenCalledTimes(1);
    resolve({});
  });

  it("OAuth accounts: no password box, guidance shown, sign-in-again offered", async () => {
    profileApi.deleteAccount.mockRejectedValue(
      Object.assign(new Error("For your security, sign in again with Google."), {
        code: "reauth_required",
      })
    );
    const { user, dialog } = await openDialog(googleProfile);

    expect(within(dialog).queryByLabelText("Confirm your password")).not.toBeInTheDocument();
    expect(within(dialog).getByText(/signed in within the last 10 minutes/)).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText(/Type/), "DELETE");
    await user.click(finalButton(dialog));

    expect(profileApi.deleteAccount).toHaveBeenCalledWith({ password: undefined });

    await user.click(await within(dialog).findByRole("button", { name: /Sign out and sign in again/ }));
    await waitFor(() => expect(screen.getByText(/LOGIN PAGE/)).toBeInTheDocument());
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
