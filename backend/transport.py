"""Deterministic application-level fault injection; every delivery is real HTTP."""
import asyncio
from uuid import uuid4

import httpx

from backend.config import NODES, TIMEOUT
from backend import http_local
from backend.storage import event


class DeliveryError(Exception):
    pass


class Transport:
    def __init__(self, run_id):
        self.run_id = run_id

    async def send(self, target, path, body, attempt=1, fault=None, source="Coordinator", delay_ms=0):
        mid = f"msg-{uuid4().hex[:8]}"
        common = {"message_id": mid, "operation_id": body.get("id"), "attempt": attempt, "path": path}
        event(self.run_id, source, target, "SEND", f"{path.upper()} · lần {attempt}", **common)
        try:
            async with asyncio.timeout(TIMEOUT):
                if delay_ms:
                    event(self.run_id, source, target, "DELAY", f"Trễ {delay_ms} ms trong transport", **common)
                    await asyncio.sleep(delay_ms / 1000)
                if fault == "drop_request":
                    event(self.run_id, source, target, "REQUEST_LOST", "Transport loại bỏ yêu cầu trước HTTP", **common)
                    await asyncio.sleep(TIMEOUT * 2)
                client = http_local.client()
                response = await client.post(NODES[target] + path, json=body, timeout=TIMEOUT)
                response.raise_for_status()
                result = response.json()
                event(self.run_id, target, source, "DELIVERED", "Node đã xử lý và lưu trạng thái", **common, response=result)
                if fault == "duplicate":
                    event(self.run_id, source, target, "DUPLICATE_SEND", "Gửi lại cùng operation ID qua HTTP", **common)
                    duplicate = await client.post(NODES[target] + path, json=body, timeout=TIMEOUT)
                    duplicate.raise_for_status()
                    result = duplicate.json()
                    event(self.run_id, target, source,
                          "DUPLICATE_SUPPRESSED" if result.get("duplicate") else "DUPLICATE_EXECUTED",
                          "Kết quả lần giao lặp", **common, response=result)
                if fault == "drop_response":
                    event(self.run_id, target, source, "RESPONSE_LOST", "Node đã thực thi; transport loại bỏ phản hồi", **common, response=result)
                    await asyncio.sleep(TIMEOUT * 2)
                event(self.run_id, target, source, "ACK", "Phản hồi HTTP đã đến bên gửi", **common, response=result)
                return result
        except (TimeoutError, httpx.TimeoutException) as exc:
            event(self.run_id, source, target, "TIMEOUT", f"Hết hạn {int(TIMEOUT * 1000)} ms", **common)
            raise DeliveryError("timeout") from exc
        except httpx.HTTPError as exc:
            event(self.run_id, source, target, "UNAVAILABLE", f"HTTP không khả dụng: {type(exc).__name__}", **common)
            raise DeliveryError("unavailable") from exc
