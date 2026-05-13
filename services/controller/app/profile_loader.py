"""
Profile loader — imports a Python profile module from /app/profiles/<name>.py
"""
import importlib.util
import logging
import os
from app.base_profile import BaseProfile

log = logging.getLogger("controller.profile")

PROFILE_DIR = os.environ.get("PROFILE_DIR", "/app/profiles")


def load_profile(name: str) -> BaseProfile:
    path = os.path.join(PROFILE_DIR, f"{name}.py")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Profile not found: {path}")

    spec = importlib.util.spec_from_file_location(f"profiles.{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "Profile"):
        raise AttributeError(f"Profile module '{name}' must define a class named 'Profile'")

    profile: BaseProfile = module.Profile()
    log.info("Loaded profile: %s (%s)", name, type(profile).__name__)
    return profile
