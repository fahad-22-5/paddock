"""Local HTTPS certificates.

Safari only enables the Screen Wake Lock API, service workers and the async Clipboard
API on secure (HTTPS) origins. We create a private certificate authority once
(data/certs/ca.crt, valid 10 years) that you install and trust on the device, and use it
to sign a server certificate for this PC's LAN addresses. The server certificate is
reissued automatically when your IP changes or it nears expiry; the device keeps trusting
it because the CA stays the same.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .paths import CERT_DIR

log = logging.getLogger("paddock.certs")

CA_KEY = CERT_DIR / "ca.key"
CA_CERT = CERT_DIR / "ca.crt"
SERVER_KEY = CERT_DIR / "server.key"
SERVER_CERT = CERT_DIR / "server.crt"

LEAF_DAYS = 397
RENEW_BEFORE_DAYS = 30


def _cn(prefix: str, suffix: str = "") -> str:
    """A certificate common name with this PC's name, cut to fit X.509's 64-character limit
    (some Macs and CI machines have very long host names)."""
    host = socket.gethostname().removesuffix(".local")
    room = 64 - len(prefix) - len(suffix)
    return f"{prefix}{host[:room]}{suffix}"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _write_key(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )


def _ensure_ca():
    if CA_KEY.exists() and CA_CERT.exists():
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), None)
        return key, x509.load_pem_x509_certificate(CA_CERT.read_bytes())
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, _cn("PadDock Local CA (", ")")),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PadDock"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(days=1))
        .not_valid_after(_now() + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(CA_KEY, key)
    CA_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    log.info("Created a new local certificate authority: %s", CA_CERT)
    return key, cert


def _leaf_is_good(ips: list[str], names: list[str], ca_cert) -> bool:
    if not (SERVER_KEY.exists() and SERVER_CERT.exists()):
        return False
    try:
        cert = x509.load_pem_x509_certificate(SERVER_CERT.read_bytes())
        if cert.issuer != ca_cert.subject:
            return False
        if cert.not_valid_after_utc - _now() < dt.timedelta(days=RENEW_BEFORE_DAYS):
            return False
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        have_ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
        have_names = set(san.get_values_for_type(x509.DNSName))
        return set(ips) <= have_ips and set(names) <= have_names
    except Exception:
        return False


def ensure_certs(ips: list[str], extra_names: list[str] | tuple = ()) -> tuple[Path, Path]:
    """Make sure a valid server certificate exists. Returns (certfile, keyfile)."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ca_key, ca_cert = _ensure_ca()
    host = socket.gethostname().removesuffix(".local")
    names = sorted({"localhost", host, f"{host}.local", f"{host}.lan", *extra_names})
    ips = sorted(set(ips) | {"127.0.0.1"})
    if _leaf_is_good(ips, names, ca_cert):
        return SERVER_CERT, SERVER_KEY

    key = ec.generate_private_key(ec.SECP256R1())
    san = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _cn("PadDock on "))]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(days=1))
        .not_valid_after(_now() + dt.timedelta(days=LEAF_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=False, key_cert_sign=False, crl_sign=False,
                content_commitment=False, data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(SERVER_KEY, key)
    # Send the chain (leaf + CA) so clients can always build the path.
    SERVER_CERT.write_bytes(
        cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM)
    )
    log.info("Issued a server certificate for %s", ", ".join(ips + names))
    return SERVER_CERT, SERVER_KEY


def ca_cert_der() -> bytes:
    """The CA certificate in DER form, which iPhone and iPad install as a profile."""
    cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
    return cert.public_bytes(serialization.Encoding.DER)
