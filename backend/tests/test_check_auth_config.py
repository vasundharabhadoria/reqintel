"""The live-config checker, exercised against a mocked Supabase (no network)."""

import importlib.util
import json
from pathlib import Path

import httpx

SPEC = importlib.util.spec_from_file_location(
    "check_auth_config", Path(__file__).resolve().parent.parent / "scripts" / "check_auth_config.py"
)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

BASE = "https://proj.supabase.co"
CALLBACK = f"{BASE}/auth/v1/callback"


def make_client(external, *, autoconfirm=False, disable_signup=False, authorize=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/v1/settings":
            assert request.headers["apikey"] == "anon"
            return httpx.Response(200, json={
                "external": external, "mailer_autoconfirm": autoconfirm, "disable_signup": disable_signup,
            })
        if request.url.path == "/auth/v1/authorize":
            provider = request.url.params["provider"]
            return authorize(provider, request)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def good_authorize(provider, request):
    host = {"google": "https://accounts.google.com/o/oauth2/v2/auth", "github": "https://github.com/login/oauth/authorize"}[provider]
    return httpx.Response(302, headers={"location": f"{host}?client_id=1234567890abcdef-secretpart&redirect_uri={CALLBACK}&state=s"})


def results(client):
    return {r.name: r for r in check.run_checks(client, BASE, "anon", "http://localhost:5173")}


def test_everything_configured_passes():
    r = results(make_client({"email": True, "google": True, "github": True}, authorize=good_authorize))
    assert not [x for x in r.values() if x.status == "FAIL"]
    assert r["Google client ID configured"].detail == "1234567890ab..."  # truncated: never the full ID
    assert "secretpart" not in json.dumps({k: v.detail for k, v in r.items()})


def test_disabled_provider_is_reported_with_the_fix():
    r = results(make_client({"email": True, "google": False, "github": True}, authorize=good_authorize))
    assert r["Google provider enabled"].status == "FAIL"
    assert "turn 'Enable' ON" in r["Google provider enabled"].detail
    assert r["GitHub provider enabled"].status == "PASS"


def test_unsaved_client_id_is_detected():
    def no_client(provider, request):
        return httpx.Response(302, headers={"location": f"https://accounts.google.com/o?redirect_uri={CALLBACK}"})

    r = results(make_client({"email": True, "google": True, "github": False}, authorize=no_client))
    assert r["Google client ID configured"].status == "FAIL"


def test_wrong_redirect_uri_is_detected():
    def wrong(provider, request):
        return httpx.Response(302, headers={"location": "https://accounts.google.com/o?client_id=abcdefghijkl&redirect_uri=https://other.example/cb"})

    r = results(make_client({"email": True, "google": True, "github": False}, authorize=wrong))
    assert r["Google redirect URI sent to provider"].status == "FAIL"


def test_provider_error_page_is_reported():
    def err(provider, request):
        return httpx.Response(400, json={"msg": "Unsupported provider: provider is not enabled"})

    r = results(make_client({"email": True, "google": True, "github": False}, authorize=err))
    assert r["Google authorize endpoint"].status == "FAIL"
    assert "not enabled" in r["Google authorize endpoint"].detail


def test_confirm_email_off_and_signups_disabled_are_flagged():
    r = results(make_client({"email": True, "google": False, "github": False}, autoconfirm=True, disable_signup=True))
    assert r["Email confirmation required"].status == "FAIL"
    assert r["New sign-ups allowed"].status == "FAIL"


def test_unreachable_supabase_fails_cleanly():
    def boom(request):
        raise httpx.ConnectError("down")

    out = check.run_checks(httpx.Client(transport=httpx.MockTransport(boom)), BASE, "anon", "http://localhost:5173")
    assert len(out) == 1 and out[0].status == "FAIL"


def test_manual_items_list_the_exact_urls_to_register():
    r = results(make_client({"email": True, "google": True, "github": True}, authorize=good_authorize))
    assert CALLBACK in r["Google console: authorized redirect URI"].detail
    assert CALLBACK in r["GitHub app: authorization callback URL"].detail
    assert "http://localhost:5173/auth/callback" in r["Supabase > URL Configuration > Redirect URLs contain"].detail
