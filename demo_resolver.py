from cortex.resolver import DependencyResolver

resolver = DependencyResolver()

# Scenario 1: A standard conflict requiring an upgrade
conflict_1 = {
    "dependency": "requests",
    "package_a": {"name": "app-v1", "requires": "^2.31.0"},
    "package_b": {"name": "app-v2", "requires": "~2.28.0"},
}

# Scenario 2: An invalid version format (to show error handling)
conflict_2 = {
    "dependency": "lib-x",
    "package_a": {"name": "pkg-a", "requires": "not-a-version"},
    "package_b": {"name": "pkg-b", "requires": "1.0.0"},
}

print("--- Scenario 1: Valid Conflict ---")
for s in resolver.resolve(conflict_1):
    print(f"[{s['type']}] Action: {s['action']} | Risk: {s['risk']}")

print("\n--- Scenario 2: Error Handling ---")
for s in resolver.resolve(conflict_2):
    print(f"[{s['type']}] Action: {s['action']}")
