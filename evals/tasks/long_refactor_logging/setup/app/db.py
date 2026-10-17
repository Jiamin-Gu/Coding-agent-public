def connect(url):
    print(f"[LOG] connecting to {url}")
    if url.startswith("sqlite"):
        return {"url": url, "connected": True}
    print(f"[LOG][ERROR] unsupported database: {url}")
    return {"url": url, "connected": False}
