"""One pooled HTTP client per service process, created before protocol deadlines.

Loading the OS CA store for every request can exceed a teaching timeout on a
busy Windows machine, even though all actual requests are HTTP on loopback.
"""
import httpx

_client = None


def start():
    global _client
    _client = httpx.AsyncClient(timeout=10, trust_env=False,
                                limits=httpx.Limits(max_connections=30, max_keepalive_connections=20))


def client():
    if _client is None:
        raise RuntimeError("HTTP pool is not initialized")
    return _client


async def stop():
    global _client
    if _client:
        await _client.aclose()
    _client = None
