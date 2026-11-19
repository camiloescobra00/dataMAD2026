"""Configuración del servidor y secretos opcionales."""
import os


def ai_settings(secrets):
    def setting(name, default=""):
        env = os.getenv(name)
        if env is not None:
            return env
        try:
            return str(secrets.get(name, default))
        except (FileNotFoundError, KeyError):
            return default
    return setting("OPENAI_API_KEY"), setting("MDE_AI_MODEL", "gpt-4.1-mini"), setting("MDE_AI_BASE_URL")
