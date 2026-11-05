import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.manager:app", host="127.0.0.1", port=int(os.environ.get("LAB_PORT", "8000")),
                log_level="info", access_log=False, timeout_graceful_shutdown=3)
