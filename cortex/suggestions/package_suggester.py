from typing import List


def suggest_alternatives(package: str) -> List[str]:
    """
    Suggest alternative packages when a requested package is unavailable.
    """
    known_packages = {
        "apache": ["apache2", "httpd", "nginx"],
        "apache-server": ["apache2", "httpd", "nginx"],
        "web-server": ["nginx", "apache2", "caddy"],
        "docker": ["podman", "containerd"],
    }

    package = package.lower()

    for key, alternatives in known_packages.items():
        if key in package:
            return alternatives

    return []
