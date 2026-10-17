from .log import get_logger

logger = get_logger("db")


def connect(url):
    logger.info(f"connecting to {url}")
    if url.startswith("sqlite"):
        return {"url": url, "connected": True}
    logger.error(f"unsupported database: {url}")
    return {"url": url, "connected": False}
