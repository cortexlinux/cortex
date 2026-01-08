import os

import yaml


class RoleNotFoundError(Exception):
    pass


def get_roles_dir():
    """
    Returns the directory where built-in roles are stored.
    """
    return os.path.dirname(__file__)


def load_role(role_name: str) -> dict:
    """
    Load a role YAML by name.
    Falls back to default if role not found.
    """
    roles_dir = get_roles_dir()
    role_file = os.path.join(roles_dir, f"{role_name}.yaml")

    if not os.path.exists(role_file):
        if role_name != "default":
            # Fallback to default role
            return load_role("default")
        raise RoleNotFoundError("Default role not found")

    with open(role_file, encoding="utf-8") as f:
        return yaml.safe_load(f)
