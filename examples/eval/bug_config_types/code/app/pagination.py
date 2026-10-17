from . import settings


def paginate(items, page):
    size = settings.get("page_size")
    start = (page - 1) * size
    return items[start:start + size]
