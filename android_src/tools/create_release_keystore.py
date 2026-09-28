#!/usr/bin/env python3
"""Create the permanent PORTAL Android release PKCS12 keystore.

The password is entered locally with hidden input and is never printed.
Do not commit the generated .p12 file.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import serialize_key_and_certificates
from cryptography.x509.oid import NameOID


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Documents" / "PORTAL-Release-Prep" / "production-signing"),
        help="Каталог для portal-release.p12 и публичной информации о сертификате",
    )
    args = parser.parse_args()

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    p12_path = out / "portal-release.p12"
    if p12_path.exists():
        raise SystemExit("ОШИБКА: portal-release.p12 уже существует; перезапись запрещена.")

    password = getpass.getpass("Введите новый пароль постоянного PORTAL release-key: ")
    confirm = getpass.getpass("Повторите пароль: ")
    if password != confirm:
        raise SystemExit("ОШИБКА: пароли не совпадают.")
    if len(password) < 16:
        raise SystemExit("ОШИБКА: пароль должен содержать не менее 16 символов.")

    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "PORTAL Android Release"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PORTAL"),
        ]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * 30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    blob = serialize_key_and_certificates(
        name=b"portal-release",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    p12_path.write_bytes(blob)

    cert_der = cert.public_bytes(serialization.Encoding.DER)
    digest = hashlib.sha256(cert_der).hexdigest()
    (out / "CERT_SHA256.txt").write_text(digest + "\n", encoding="ascii")
    (out / "SIGNING_IDENTITY.txt").write_text(
        "alias=portal-release\n"
        "store_type=PKCS12\n"
        f"certificate_sha256={digest}\n"
        "subject=CN=PORTAL Android Release,O=PORTAL\n"
        "validity_years=30\n",
        encoding="utf-8",
    )

    print(f"Готово: {p12_path}")
    print(f"SHA-256 сертификата: {digest}")
    print("Пароль не сохранялся и не выводился.")
    print("Сделайте защищённую резервную копию .p12 до первого production-релиза.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
