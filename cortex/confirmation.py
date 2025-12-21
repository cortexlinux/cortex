def confirm_plan(steps):
    print("\nProposed installation plan:\n")
    for step in steps:
        print(step)

    print("\nProceed?")
    print("[y] yes   [e] edit   [n] cancel")

    choice = input("> ").lower()

    return choice
