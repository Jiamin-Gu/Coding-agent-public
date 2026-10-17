from .log import get_logger

log = get_logger("users")


def create_user(db, name):
    log.info(f"creating user {name}")
    if not name:
        log.error("empty user name")
        return None
    if not db["connected"]:
        log.warning("database offline, user kept in memory")
    print(f"已创建用户：{name}")
    return {"name": name}
