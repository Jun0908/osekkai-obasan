"""Google Calendar OAuth state/PKCE and encrypted token persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.fernet import Fernet, InvalidToken

from osekkai_contracts import ContractError, require_uuid


CALENDAR_FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
STATE_TTL_MINUTES = 10


class GoogleCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "GoogleOAuthConfig":
        env = os.environ if environ is None else environ
        values = {
            "client_id": str(env.get("GOOGLE_CLIENT_ID", "")).strip(),
            "client_secret": str(env.get("GOOGLE_CLIENT_SECRET", "")).strip(),
            "redirect_uri": str(env.get("GOOGLE_REDIRECT_URI", "")).strip(),
        }
        missing = [name.upper() for name, value in values.items() if not value]
        if missing:
            raise GoogleCredentialError(f"Google OAuth configuration missing: {', '.join(missing)}")
        parsed = urllib.parse.urlparse(values["redirect_uri"])
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.fragment:
            raise GoogleCredentialError("GOOGLE_REDIRECT_URI is invalid")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise GoogleCredentialError("GOOGLE_REDIRECT_URI must use HTTPS outside localhost")
        return cls(**values)


def _root() -> Path:
    configured = os.environ.get("OSEKKAI_DATA_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[1] / "data" / "osekkai"


def _fernet(environ: Mapping[str, str] | None = None) -> tuple[Fernet, bytes]:
    env = os.environ if environ is None else environ
    configured = str(env.get("OSEKKAI_CREDENTIAL_ENCRYPTION_KEY", "")).strip()
    if len(configured.encode("utf-8")) < 32:
        raise GoogleCredentialError("OSEKKAI_CREDENTIAL_ENCRYPTION_KEY must contain at least 32 bytes")
    digest = hashlib.sha256(configured.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest)), digest


class GoogleCredentialStore:
    def __init__(self, root: Path | str | None = None, *, environ: Mapping[str, str] | None = None):
        self.root = Path(root).expanduser().resolve() if root else _root().resolve()
        self.directory = (self.root / "credentials").resolve()
        try:
            self.directory.relative_to(self.root)
        except ValueError as exc:
            raise GoogleCredentialError("credential path escapes OSEKKAI_DATA_ROOT") from exc
        self.directory.mkdir(parents=True, exist_ok=True)
        self._fernet, self._digest = _fernet(environ)

    def _user_key(self, user_id: str) -> str:
        require_uuid(user_id, "userId")
        return hmac.new(self._digest, user_id.encode("utf-8"), hashlib.sha256).hexdigest()

    def _token_path(self, user_id: str) -> Path:
        return self.directory / f"google-token-{self._user_key(user_id)}.enc"

    def _state_path(self, state: str) -> Path:
        if not re_fullmatch_state(state):
            raise GoogleCredentialError("OAuth state is malformed")
        return self.directory / f"google-state-{hashlib.sha256(state.encode('utf-8')).hexdigest()}.enc"

    def _write(self, path: Path, value: Mapping[str, Any]) -> None:
        encrypted = self._fernet.encrypt(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            decrypted = self._fernet.decrypt(path.read_bytes())
            value = json.loads(decrypted.decode("utf-8"))
        except (OSError, InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GoogleCredentialError("encrypted Google credential could not be read") from exc
        if not isinstance(value, dict):
            raise GoogleCredentialError("encrypted Google credential is malformed")
        return value

    def save_state(self, state: str, value: Mapping[str, Any]) -> None:
        self._write(self._state_path(state), value)

    def consume_state(self, state: str) -> dict[str, Any]:
        path = self._state_path(state)
        value = self._read(path)
        try:
            path.unlink()
        except OSError as exc:
            raise GoogleCredentialError("OAuth state could not be consumed") from exc
        return value

    def save_token(self, user_id: str, value: Mapping[str, Any]) -> None:
        self._write(self._token_path(user_id), value)

    def load_token(self, user_id: str) -> dict[str, Any] | None:
        path = self._token_path(user_id)
        if not path.exists():
            return None
        return self._read(path)

    def delete_user(self, user_id: str) -> bool:
        path = self._token_path(user_id)
        existed = path.exists()
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise GoogleCredentialError("Google credential could not be deleted") from exc
        # Pending states are encrypted; decrypt only bounded files and remove
        # states belonging to this anonymous session.
        for state_path in list(self.directory.glob("google-state-*.enc"))[:1000]:
            try:
                value = self._read(state_path)
                if value.get("userId") == user_id:
                    state_path.unlink(missing_ok=True)
            except GoogleCredentialError:
                continue
        return existed


def re_fullmatch_state(value: str) -> bool:
    return bool(value) and 32 <= len(value) <= 160 and all(character.isalnum() or character in "-_" for character in value)


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def create_authorization_request(
    user_id: str,
    *,
    now: datetime,
    config: GoogleOAuthConfig,
    store: GoogleCredentialStore,
) -> dict[str, Any]:
    require_uuid(user_id, "userId")
    if now.tzinfo is None:
        raise GoogleCredentialError("OAuth clock must be timezone-aware")
    state = "g" + secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    expires_at = now + timedelta(minutes=STATE_TTL_MINUTES)
    store.save_state(
        state,
        {
            "type": "google_oauth_state",
            "userId": user_id,
            "stateHash": hashlib.sha256(state.encode("utf-8")).hexdigest(),
            "codeVerifier": verifier,
            "redirectUri": config.redirect_uri,
            "expiresAt": expires_at.isoformat(),
        },
    )
    query = urllib.parse.urlencode(
        {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "scope": CALENDAR_FREEBUSY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return {"authorizationUrl": f"{AUTH_ENDPOINT}?{query}", "state": state, "expiresAt": expires_at.isoformat()}


def _post_form(url: str, form: Mapping[str, str], *, timeout: float = 15.0) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleCredentialError("Google OAuth token request failed") from exc
    if not isinstance(payload, dict):
        raise GoogleCredentialError("Google OAuth token response is malformed")
    return payload


def _token_record(payload: Mapping[str, Any], *, now: datetime, previous_refresh_token: str | None = None) -> dict[str, Any]:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token") or previous_refresh_token
    expires_in = payload.get("expires_in")
    scopes = set(str(payload.get("scope") or CALENDAR_FREEBUSY_SCOPE).split())
    if not isinstance(access_token, str) or not access_token or not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleCredentialError("Google OAuth response did not include durable credentials")
    if CALENDAR_FREEBUSY_SCOPE not in scopes or scopes - {CALENDAR_FREEBUSY_SCOPE}:
        raise GoogleCredentialError("Google OAuth granted scope differs from Calendar FreeBusy")
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or expires_in <= 0:
        raise GoogleCredentialError("Google OAuth expiration is invalid")
    return {
        "type": "google_calendar_freebusy_token",
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresAt": (now + timedelta(seconds=int(expires_in))).isoformat(),
        "scope": CALENDAR_FREEBUSY_SCOPE,
        "tokenType": str(payload.get("token_type") or "Bearer"),
        "updatedAt": now.isoformat(),
    }


def complete_authorization(
    user_id: str,
    *,
    state: str,
    code: str,
    now: datetime,
    config: GoogleOAuthConfig,
    store: GoogleCredentialStore,
    token_transport: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    require_uuid(user_id, "userId")
    if not code or len(code) > 4096:
        raise GoogleCredentialError("OAuth authorization code is invalid")
    saved = store.consume_state(state)
    if (
        saved.get("type") != "google_oauth_state"
        or saved.get("userId") != user_id
        or not hmac.compare_digest(str(saved.get("stateHash", "")), hashlib.sha256(state.encode("utf-8")).hexdigest())
        or saved.get("redirectUri") != config.redirect_uri
    ):
        raise GoogleCredentialError("OAuth state does not match the anonymous session")
    expires_at = datetime.fromisoformat(str(saved.get("expiresAt")))
    if expires_at <= now:
        raise GoogleCredentialError("OAuth state has expired")
    form = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "code": code,
        "code_verifier": str(saved["codeVerifier"]),
        "grant_type": "authorization_code",
        "redirect_uri": config.redirect_uri,
    }
    payload = dict(token_transport(TOKEN_ENDPOINT, form)) if token_transport else _post_form(TOKEN_ENDPOINT, form)
    record = _token_record(payload, now=now)
    store.save_token(user_id, record)
    return {"connected": True, "scope": CALENDAR_FREEBUSY_SCOPE, "expiresAt": record["expiresAt"]}


def access_token(
    user_id: str,
    *,
    now: datetime,
    config: GoogleOAuthConfig,
    store: GoogleCredentialStore,
    token_transport: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
) -> str:
    record = store.load_token(user_id)
    if record is None:
        raise GoogleCredentialError("Google Calendar is not connected")
    if record.get("type") != "google_calendar_freebusy_token" or record.get("scope") != CALENDAR_FREEBUSY_SCOPE:
        raise GoogleCredentialError("stored Google credential is invalid")
    expires_at = datetime.fromisoformat(str(record.get("expiresAt")))
    if expires_at > now + timedelta(minutes=5):
        return str(record["accessToken"])
    form = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "refresh_token": str(record["refreshToken"]),
        "grant_type": "refresh_token",
    }
    payload = dict(token_transport(TOKEN_ENDPOINT, form)) if token_transport else _post_form(TOKEN_ENDPOINT, form)
    refreshed = _token_record(payload, now=now, previous_refresh_token=str(record["refreshToken"]))
    store.save_token(user_id, refreshed)
    return str(refreshed["accessToken"])


def disconnect_google(user_id: str, store: GoogleCredentialStore) -> dict[str, Any]:
    store.delete_user(user_id)
    return {"disconnected": True}
