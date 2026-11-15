"""Test doubles for the Supabase Auth client. No network is ever touched."""

import itertools
import uuid

from supabase_auth.errors import AuthApiError

import api.v1.auth as auth_api


def api_error(message: str, status: int, code: str) -> AuthApiError:
    return AuthApiError(message, status, code)


class _User:
    def __init__(self, email: str = "a@b.com", user_id: str | None = None) -> None:
        self.id = user_id or str(uuid.uuid4())
        self.email = email


class _Session:
    def __init__(self, access: str, refresh: str) -> None:
        self.access_token = access
        self.refresh_token = refresh


class _Result:
    def __init__(self, user=None, session=None) -> None:
        self.user = user
        self.session = session


class _Admin:
    def __init__(self, owner: "FakeAuthClient") -> None:
        self.owner = owner

    def sign_out(self, token, scope="local"):
        self.owner.signed_out.append((token, scope))


class _Auth:
    def __init__(self, owner: "FakeAuthClient") -> None:
        self.owner = owner
        self.admin = _Admin(owner)

    def sign_up(self, params):
        self.owner.calls.append(("sign_up", params))
        if self.owner.sign_up_error:
            raise self.owner.sign_up_error
        return _Result(user=_User(params["email"]))

    def sign_in_with_password(self, creds):
        self.owner.calls.append(("sign_in_with_password", creds))
        if self.owner.sign_in_error:
            raise self.owner.sign_in_error
        user = _User(creds["email"])
        return _Result(user=user, session=_Session(*self.owner.next_tokens()))

    def refresh_session(self, refresh_token):
        self.owner.calls.append(("refresh_session", refresh_token))
        if self.owner.refresh_error:
            raise self.owner.refresh_error
        if self.owner.valid_refresh_tokens is not None:
            if refresh_token not in self.owner.valid_refresh_tokens:
                raise api_error("Invalid Refresh Token: Already Used", 400, "refresh_token_already_used")
            self.owner.valid_refresh_tokens.discard(refresh_token)
        return _Result(user=_User(), session=_Session(*self.owner.next_tokens()))

    def reset_password_for_email(self, email, options=None):
        self.owner.calls.append(("reset_password_for_email", email, options))
        if self.owner.recover_error:
            raise self.owner.recover_error

    def resend(self, params):
        self.owner.calls.append(("resend", params))
        if self.owner.resend_error:
            raise self.owner.resend_error

    def exchange_code_for_session(self, params):
        self.owner.calls.append(("exchange_code_for_session", params))
        if self.owner.exchange_error:
            raise self.owner.exchange_error
        return _Result(user=_User("oauth@example.com"), session=_Session(*self.owner.next_tokens()))


class FakeAuthClient:
    _counter = itertools.count(1)

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.signed_out: list[tuple] = []
        self.sign_up_error = None
        self.sign_in_error = None
        self.refresh_error = None
        self.recover_error = None
        self.resend_error = None
        self.exchange_error = None
        # When set, refresh_session only accepts (and consumes) these tokens,
        # which simulates Supabase refresh-token rotation.
        self.valid_refresh_tokens: set[str] | None = None
        self.token_sequence = itertools.count(1)
        self.auth = _Auth(self)

    def next_tokens(self) -> tuple[str, str]:
        n = next(self.token_sequence)
        return ("acc" if n == 1 else f"acc{n}", "ref" if n == 1 else f"ref{n}")


def install_fake_auth(monkeypatch) -> FakeAuthClient:
    """Route the AuthService through ONE inspectable fake client."""
    fake = FakeAuthClient()
    monkeypatch.setattr(auth_api.auth_service, "client_factory", lambda: fake)
    return fake
