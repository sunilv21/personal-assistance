from .config import settings

session_memory = []

def add_to_memory(role, content):
    session_memory.append({"role": role, "content": content})

    if len(session_memory) > settings.MAX_CONTEXT_MESSAGES * 2:
        session_memory.pop(0)

def get_memory():
    return session_memory