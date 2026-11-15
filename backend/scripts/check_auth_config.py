"""
Live check of the Supabase Auth configuration ReqIntel depends on.

Run from the backend folder (reads backend/.env, never prints secrets):

    python scripts/check_auth_config.py

It only performs read-only requests: Supabase's public settings endpoint and
the public OAuth authorize endpoint (redirects are NOT followed, so nothing is
sent to Google/GitHub and no login happens). Each line is PASS, FAIL or MANUAL
(something this script cannot see and you must confirm in a dashboard).
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROVIDERS = {
    "google": ("Google", "accounts.google.com"),
    "github": ("GitHub", "github.com"),
}
# base64url(SHA-256("x" * 64)): any valid 43-char S256 challenge works here.
SAMPLE_CHALLENGE = "A" * 43


@dataclass
class Result:
    status: str  # PASS | FAIL | MANUAL
    name: str
    detail: str = ""


def run_checks(client: httpx.Client, supabase_url: str, anon_key: str, frontend_url: str) -> list[Result]:
    base = supabase_url.rstrip("/")
    callback = f"{base}/auth/v1/callback"
    results: list[Result] = []

    try:
        response = client.get(f"{base}/auth/v1/settings", headers={"apikey": anon_key})
        response.raise_for_status()
        auth_settings = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return [Result("FAIL", "Reach Supabase Auth", f"{type(exc).__name__}: check SUPABASE_URL / SUPABASE_ANON_KEY")]

    results.append(Result("PASS", "Reach Supabase Auth", base))

    external = auth_settings.get("external") or {}

    results.append(
        Result(
            "PASS" if external.get("email") else "FAIL",
            "Email sign-in enabled",
        )
    )
    results.append(
        Result(
            "PASS" if not auth_settings.get("mailer_autoconfirm") else "FAIL",
            "Email confirmation required",
            "" if not auth_settings.get("mailer_autoconfirm") else "'Confirm email' is OFF: users are confirmed automatically",
        )
    )
    results.append(
        Result(
            "PASS" if not auth_settings.get("disable_signup") else "FAIL",
            "New sign-ups allowed",
        )
    )

    for key, (label, expected_host) in PROVIDERS.items():
        if not external.get(key):
            results.append(
                Result("FAIL", f"{label} provider enabled", "OFF: Supabase > Authentication > Sign In / Providers > "
                       f"{label} > turn 'Enable' ON and Save")
            )
            continue

        results.append(Result("PASS", f"{label} provider enabled"))

        try:
            authorize = client.get(
                f"{base}/auth/v1/authorize",
                params={
                    "provider": key,
                    "redirect_to": f"{frontend_url.rstrip('/')}/auth/callback",
                    "code_challenge": SAMPLE_CHALLENGE,
                    "code_challenge_method": "s256",
                },
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            results.append(Result("FAIL", f"{label} authorize endpoint", type(exc).__name__))
            continue

        location = authorize.headers.get("location", "")

        if authorize.status_code in (301, 302, 303, 307) and expected_host in location:
            query = parse_qs(urlparse(location).query)
            client_id = (query.get("client_id") or [""])[0]
            redirect_uri = (query.get("redirect_uri") or [""])[0]
            shown_id = (client_id[:12] + "...") if client_id else "(missing: client ID not saved in Supabase)"

            results.append(Result("PASS" if client_id else "FAIL", f"{label} client ID configured", shown_id))
            results.append(
                Result(
                    "PASS" if redirect_uri == callback else "FAIL",
                    f"{label} redirect URI sent to provider",
                    f"{redirect_uri} (must be registered EXACTLY in the {label} console)",
                )
            )
        else:
            detail = authorize.text[:160].replace("\n", " ")
            results.append(Result("FAIL", f"{label} authorize endpoint", f"HTTP {authorize.status_code}: {detail}"))

    results.append(
        Result(
            "MANUAL",
            "Supabase > URL Configuration > Redirect URLs contain",
            f"{frontend_url.rstrip('/')}/auth/callback  and  {frontend_url.rstrip('/')}/reset-password",
        )
    )
    results.append(
        Result("MANUAL", "Google console: authorized redirect URI", callback)
    )
    results.append(
        Result("MANUAL", "GitHub app: authorization callback URL", callback)
    )
    results.append(
        Result(
            "MANUAL",
            "Google consent screen in 'Testing' mode",
            "add every tester's Gmail under 'Test users', otherwise Google answers access_denied",
        )
    )
    results.append(
        Result(
            "MANUAL",
            "GitHub: app type",
            "a classic OAuth App works as-is. If this is a GitHub *App*, grant Account permissions > "
            "Email addresses = Read-only, or users without a public email cannot sign in",
        )
    )

    return results


def main() -> int:
    from core.config import settings

    with httpx.Client(timeout=10) as client:
        results = run_checks(client, settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY, settings.frontend_url)

    width = max(len(r.name) for r in results)

    for r in results:
        print(f"[{r.status:6}] {r.name.ljust(width)}  {r.detail}".rstrip())

    failed = [r for r in results if r.status == "FAIL"]
    print(f"\n{len(failed)} failing check(s)." if failed else "\nNo failing checks. Review the MANUAL items.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
