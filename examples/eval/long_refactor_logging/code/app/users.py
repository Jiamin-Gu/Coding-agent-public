from .log import get_logger

logger = get_logger("users")


def create_user(db, name):
    logger.info(f"creating user {name}")
    if not name:
        logger.error("empty user name")
        return None
    if not db["connected"]:
        logger.warning("database offline, user kept in memory")
    print(f"已创建用户：{name}")
    return {"name": name}
