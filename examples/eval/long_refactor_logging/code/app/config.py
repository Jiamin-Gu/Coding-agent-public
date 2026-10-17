from .log import get_logger

logger = get_logger("config")


def load_config(path):
    logger.info(f"loading config from {path}")
    if not path.endswith(".ini"):
        logger.warning(f"unusual config extension: {path}")
    return {"path": path, "debug": False}
