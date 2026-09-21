"""Small, dependency-free settings and optional log storage for IRdisC."""
from __future__ import annotations

import json
import ipaddress
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Profile:
    name: str = "OFTC"
    host: str = "irc.oftc.net"
    port: int = 6697
    tls: bool = True
    nick: str = ""
    channel: str = ""
    sasl_account: str = ""


@dataclass
class Preferences:
    profile: Profile
    theme: str = "dark"
    logging: bool = False
    auto_reconnect: bool = False
    notifications: bool = False
    profiles: dict[str, dict] = field(default_factory=dict)


def validate_profile(profile, password='', *, connecting=False):
    """Return field-specific errors; never resolve hosts or expose secrets."""
    errors = {}
    host = profile.host
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.rstrip('.').split('.')
        if (not host or len(host) > 253 or
                any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                    for part in labels)):
            errors['host'] = 'Use a hostname or IP, not a channel/URL. Put the port in Port.'
    try:
        valid_port = 1 <= int(profile.port) <= 65535
    except (ValueError, TypeError):
        valid_port = False
    if not valid_port:
        errors['port'] = 'Port must be a number from 1 to 65535.'
    if not profile.name.strip() or any(not c.isprintable() for c in profile.name):
        errors['name'] = 'Enter a network name.'
    if not re.fullmatch(r'[A-Za-z_\[\]\\\\`^{}|][A-Za-z0-9_\[\]\\\\`^{}|\-]{0,29}', profile.nick):
        errors['nick'] = 'Enter a valid nickname (no spaces, maximum 30 characters).'
    channel = profile.channel
    if channel and (len(channel) < 2 or not channel.startswith(('#', '&')) or
                    any(c.isspace() or c in ',:\x00\x07' for c in channel)):
        errors['channel'] = 'Use #channel or &channel, or leave empty.'
    if profile.sasl_account and (not profile.tls or any(c.isspace() or not c.isprintable() for c in profile.sasl_account)):
        errors['sasl_account'] = 'SASL needs TLS and an account without spaces/control characters.'
    if connecting and profile.sasl_account and not password:
        errors['password'] = 'Enter the SASL password, or clear the account.'
    return errors


def config_dir() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    return Path(root) / "irdisc" if root else Path.home() / ".config" / "irdisc"


def state_dir() -> Path:
    root = os.environ.get("XDG_STATE_HOME")
    return Path(root) / "irdisc" if root else Path.home() / ".local" / "state" / "irdisc"


def default_preferences() -> Preferences:
    return Preferences(Profile(name='', host='', port='', channel=''))


def load_preferences(path: Path | None = None) -> Preferences:
    path = path or config_dir() / "config.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        profile = raw.get("profile", {})
        port = int(profile.get("port", 6697))
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
        host = str(profile.get("host", "irc.oftc.net")).strip()
        if not host or any(c.isspace() for c in host):
            raise ValueError("invalid host")
        saved_profiles = raw.get("profiles", {})
        if not isinstance(saved_profiles, dict):
            saved_profiles = {}
        saved_profiles = {str(key)[:40]: value for key, value in saved_profiles.items()
                          if isinstance(value, dict)}
        return Preferences(
            Profile(
                name=str(profile.get("name", "OFTC"))[:40],
                host=host[:253],
                port=port,
                tls=bool(profile.get("tls", True)),
                nick=str(profile.get("nick", ""))[:30],
                channel=str(profile.get("channel", ""))[:80],
                sasl_account=str(profile.get("sasl_account", ""))[:100],
            ),
            theme=str(raw.get("theme", "dark")) if raw.get("theme") in {"dark", "light", "mono"} else "dark",
            logging=bool(raw.get("logging", False)),
            auto_reconnect=bool(raw.get("auto_reconnect", False)),
            notifications=bool(raw.get("notifications", False)),
            profiles=saved_profiles,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default_preferences()


def save_preferences(prefs: Preferences, path: Path | None = None) -> Path:
    """Save non-secret settings atomically. SASL passwords are never accepted."""
    path = path or config_dir() / "config.json"
    prefs.profiles[prefs.profile.name] = asdict(prefs.profile)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(prefs), indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return path


def safe_log_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return (cleaned or "server")[:80]


def append_log(target: str, line: str, directory: Path | None = None) -> None:
    directory = directory or state_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{safe_log_name(target)}.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.replace("\r", " ").replace("\n", " ") + "\n")
    os.chmod(path, 0o600)
