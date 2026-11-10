"""Chứng chỉ HTTPS tự ký để điện thoại được phép dùng camera trong trình duyệt."""
import ipaddress
from datetime import datetime, timedelta


def make_cert(ip, data_dir):
    cert_dir = data_dir / "certs"
    key_file, cert_file, ip_file = cert_dir / "key.pem", cert_dir / "cert.pem", cert_dir / "ip.txt"
    if key_file.exists() and cert_file.exists() and ip_file.exists() and ip_file.read_text() == ip:
        return str(key_file), str(cert_file)  # đổi mạng Wi-Fi (IP khác) thì tạo lại
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "khkt-lop-hoc")])
    alt = x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                       x509.IPAddress(ipaddress.ip_address(ip))])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now() - timedelta(days=1))
            .not_valid_after(datetime.now() + timedelta(days=3650))
            .add_extension(alt, critical=False).sign(key, hashes.SHA256()))
    cert_dir.mkdir(parents=True, exist_ok=True)
    ip_file.write_text(ip)
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(key_file), str(cert_file)
