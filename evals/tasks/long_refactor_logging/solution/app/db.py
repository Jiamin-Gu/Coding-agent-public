from .log import get_logger

log = get_logger("db")


def connect(url):
    log.info(f"connecting to {url}")
    if url.startswith("sqlite"):
        return {"url": url, "connected": True}
    log.error(f"unsupported database: {url}")
    return {"url": url, "connected": False}
