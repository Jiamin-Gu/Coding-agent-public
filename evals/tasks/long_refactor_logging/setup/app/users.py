def create_user(db, name):
    print(f"[LOG] creating user {name}")
    if not name:
        print("[LOG][ERROR] empty user name")
        return None
    if not db["connected"]:
        print("[LOG][WARN] database offline, user kept in memory")
    print(f"已创建用户：{name}")
    return {"name": name}
