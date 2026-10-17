def load_config(path):
    print(f"[LOG] loading config from {path}")
    if not path.endswith(".ini"):
        print(f"[LOG][WARN] unusual config extension: {path}")
    return {"path": path, "debug": False}
