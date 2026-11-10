"""Khởi động nền tảng giám sát lớp học (máy chủ web + AI cho nhiều lớp).

  python web.py                 # mở http://localhost:8000
  python web.py --no-browser    # không tự mở trình duyệt (chạy làm máy chủ)

Lần đầu mở trang sẽ được yêu cầu tạo tài khoản quản trị viên.
Giáo viên trong trường dùng điện thoại/laptop cùng mạng mở địa chỉ "Mạng nội bộ" in bên dưới.
"""
import argparse
import asyncio
import socket
import sys
import threading
import webbrowser
from datetime import datetime, timedelta

import uvicorn

from core.paths import DATA
from core.pipeline import load_config
from server.app import Platform, create_app


def lan_ip():
    """Địa chỉ IP của máy trong mạng Wi-Fi/LAN (không gửi dữ liệu ra ngoài)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def make_cert(ip):
    """Chứng chỉ HTTPS tự ký: điện thoại chỉ được dùng camera trong trình duyệt qua HTTPS."""
    cert_dir = DATA / "certs"
    key_file, cert_file = cert_dir / "key.pem", cert_dir / "cert.pem"
    ip_file = cert_dir / "ip.txt"
    if key_file.exists() and cert_file.exists() and ip_file.exists() and ip_file.read_text() == ip:
        return str(key_file), str(cert_file)
    try:
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "lop-hoc-ai")])
    alt = x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address(ip))])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now() - timedelta(days=1))
            .not_valid_after(datetime.now() + timedelta(days=3650))
            .add_extension(alt, critical=False).sign(key, hashes.SHA256()))
    cert_dir.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    ip_file.write_text(ip)
    return str(key_file), str(cert_file)


def main():
    ap = argparse.ArgumentParser(description="Nền tảng giám sát hành vi lớp học")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https-port", type=int, default=8443)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    ip = lan_ip()
    cert = make_cert(ip)
    urls = {"local": f"http://localhost:{args.port}", "lan": f"http://{ip}:{args.port}",
            "https": f"https://{ip}:{args.https_port}" if cert else ""}

    print("Đang khởi động, vui lòng chờ...")
    platform = Platform(load_config(args.config), urls)
    app = create_app(platform)

    # Luồng video trực tiếp không bao giờ tự đóng, nên khi tắt chỉ chờ 2 giây rồi tắt hẳn
    opts = dict(host="0.0.0.0", log_level="warning", timeout_graceful_shutdown=2)
    servers = [uvicorn.Server(uvicorn.Config(app, port=args.port, **opts))]
    if cert:
        servers.append(uvicorn.Server(uvicorn.Config(app, port=args.https_port, ssl_keyfile=cert[0],
                                                     ssl_certfile=cert[1], **opts)))
    print("\n" + "=" * 64)
    print("  LỚP HỌC AI - HỆ THỐNG CẢNH BÁO HÀNH VI ĐANG CHẠY")
    print(f"   Trên máy này:   {urls['local']}")
    print(f"   Mạng nội bộ:    {urls['lan']}   (giáo viên mở trên điện thoại/laptop)")
    print(f"   Dữ liệu lưu ở:  {DATA}")
    print("  ĐỪNG TẮT CỬA SỔ NÀY khi đang giám sát. Nhấn Ctrl+C để tắt.")
    print("=" * 64 + "\n")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(urls["local"],)).start()

    async def serve():
        # Ctrl+C chỉ báo cho 1 server, nên khi 1 cái dừng thì dừng luôn cái còn lại
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for s in servers:
            s.should_exit = True
        await asyncio.gather(*pending)

    try:
        asyncio.run(serve())
    except OSError as e:
        print(f"\n[!] Không mở được cổng {args.port}: có thể app đang chạy ở cửa sổ khác. ({e})")
        if sys.stdin and sys.stdin.isatty():
            input("Nhấn Enter để thoát...")
    finally:
        platform.manager.stop()


if __name__ == "__main__":
    main()
