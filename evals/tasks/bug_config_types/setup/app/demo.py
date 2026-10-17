from .pagination import paginate
from .server import startup_messages

print(startup_messages())
print(paginate(list(range(100)), 2))
