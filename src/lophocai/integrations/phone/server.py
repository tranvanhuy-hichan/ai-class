"""Máy chủ nhận hình từ điện thoại (dùng điện thoại làm camera).

Điện thoại quét mã QR, mở trang resources/phone/phone.html qua HTTPS (chứng chỉ tự ký, cổng 8443) rồi
gửi từng khung hình JPEG qua WebSocket. Mọi yêu cầu đều phải kèm mã bí mật ?k=... (đổi mỗi lần mở app);
máy chỉ gửi được hình lên, không xem được gì.
"""
import asyncio
import json
import secrets
import threading
import time

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from lophocai.storage.paths import res

from .certificates import make_cert
from .security import lan_ip

PORT = 8443
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


def create_phone_app(engine, phone_key):
    app = FastAPI(title="Camera điện thoại", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def require_key(request: Request, call_next):
        if request.query_params.get("k") != phone_key:
            return Response("Mã QR đã cũ (app vừa mở lại). Hãy quét lại mã QR mới.", status_code=403,
                            media_type="text/plain; charset=utf-8")
        return await call_next(request)

    @app.get("/phone")
    def phone_page():
        return FileResponse(res("resources/phone/phone.html"), headers=NO_CACHE)

    @app.websocket("/ws/phone")
    async def ws_phone(ws: WebSocket):
        await ws.accept()
        if ws.query_params.get("k") != phone_key:
            await ws.send_text(json.dumps({"error": "Mã QR đã cũ (app vừa mở lại). Hãy quét lại mã QR mới."},
                                          ensure_ascii=False))
            await ws.close()
            return
        phone_cam = next((c for c in engine.cameras.values() if c.source == "phone"), None)
        if phone_cam is None:   # chưa có camera điện thoại -> tự tạo
            phone_cam = engine.add_camera("Camera điện thoại", "phone")
        if not phone_cam.running:
            try:
                await asyncio.to_thread(phone_cam.start)
            except RuntimeError as e:
                await ws.send_text(json.dumps({"error": str(e)}, ensure_ascii=False))
                await ws.close()
                return
        try:
            while True:
                engine.phone.push_jpeg(await ws.receive_bytes())
                await ws.send_text(json.dumps({"announcements": phone_cam.status["announcements"]}, ensure_ascii=False))
        except WebSocketDisconnect:
            pass

    return app


class PhoneServer:
    """Chạy máy chủ HTTPS ở luồng nền. start() trả về URL cho mã QR, hoặc "" nếu không bật được
    (thiếu thư viện cryptography, hoặc cổng 8443 đang bị chiếm)."""

    def __init__(self, engine, data_dir):
        self.engine, self.data_dir = engine, data_dir
        self.key = secrets.token_urlsafe(8)
        self.url = ""
        self._server = None

    def start(self):
        ip = lan_ip()
        cert = make_cert(ip, self.data_dir)
        if not cert:
            return ""
        config = uvicorn.Config(create_phone_app(self.engine, self.key), host="0.0.0.0", port=PORT,
                                ssl_keyfile=cert[0], ssl_certfile=cert[1], log_level="warning",
                                timeout_graceful_shutdown=2)
        self._server = uvicorn.Server(config)
        threading.Thread(target=self._run, daemon=True).start()
        for _ in range(40):   # chờ tối đa ~4 giây cho máy chủ lên
            if self._server.started:
                self.url = f"https://{ip}:{PORT}/phone?k={self.key}"
                return self.url
            time.sleep(0.1)
        self._server.should_exit = True
        return ""

    def _run(self):
        try:
            self._server.run()
        except SystemExit:   # uvicorn thoát khi không mở được cổng
            pass

    def stop(self):
        if self._server is not None:
            self._server.should_exit = True
