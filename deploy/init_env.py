#!/usr/bin/env python3
"""Create private first-install configuration without printing or reusing secrets."""

import argparse
import base64
import os
from pathlib import Path
import re
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost", help="Public DNS name or IPv4 address")
    parser.add_argument("--https-port", type=int, default=18443)
    parser.add_argument("--http-port", type=int, default=18080)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", args.host):
        parser.error("host must be a DNS name or IPv4 address, without scheme or port")
    if any(not 1 <= p <= 65535 for p in (args.https_port, args.http_port)):
        parser.error("ports must be between 1 and 65535")
    if args.https_port == args.http_port:
        parser.error("HTTP and HTTPS need different ports")
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    password_file = root / "secrets" / "db_password.txt"
    if env_file.exists() or password_file.exists():
        parser.error("Existing configuration found; initialization never overwrites credentials")
    values = {}
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    hosts = list(dict.fromkeys([args.host, "localhost", "127.0.0.1"]))
    values.update(
        APP_PUBLIC_HOST=args.host,
        APP_PORT=str(args.http_port),
        APP_TLS_PORT=str(args.https_port),
        POSTGRES_PASSWORD=secrets.token_hex(32),
        DJANGO_SECRET_KEY=secrets.token_urlsafe(64),
        SIGNING_MASTER_KEY=base64.b64encode(secrets.token_bytes(32)).decode(),
        SIGNING_KEY_PASSWORD=secrets.token_urlsafe(48),
        INITIAL_ADMIN_PASSWORD=secrets.token_urlsafe(32),
        DJANGO_ALLOWED_HOSTS=",".join(hosts),
        DJANGO_CSRF_TRUSTED_ORIGINS=",".join(f"https://{h}:{args.https_port}" for h in hosts),
    )
    os.umask(0o077)
    password_file.parent.mkdir(exist_ok=True, mode=0o700)
    with password_file.open("x", encoding="utf-8") as stream:
        stream.write(values["POSTGRES_PASSWORD"] + "\n")
    try:
        with env_file.open("x", encoding="utf-8") as stream:
            stream.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
    except Exception:
        password_file.unlink()
        raise
    print(f"Private configuration created. Open https://{args.host}:{args.https_port} after startup.")
    print("Create your administrator with: docker compose exec api python manage.py createsuperuser")
    print("Keep .env and secrets/ private and include them in an encrypted backup.")


if __name__ == "__main__":
    main()
