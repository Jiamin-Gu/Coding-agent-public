from .log import get_logger

log = get_logger("config")


def load_config(path):
    log.info(f"loading config from {path}")
    if not path.endswith(".ini"):
        log.warning(f"unusual config extension: {path}")
    return {"path": path, "debug": False}
