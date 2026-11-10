"""Kiểm tra yêu cầu đến từ máy đang chạy app hay từ điện thoại trong LAN có mã bí mật đúng."""
import ipaddress
import socket


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


def is_local(host):
    """Yêu cầu đến từ chính máy này?"""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"
