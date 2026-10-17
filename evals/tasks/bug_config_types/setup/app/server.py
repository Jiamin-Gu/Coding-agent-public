from . import settings


def startup_messages():
    messages = ["server started"]
    if settings.get("debug"):
        messages.append("debug mode on")
    return messages
