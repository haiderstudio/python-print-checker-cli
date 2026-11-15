# A module with debug prints left in by mistake.

from pprint import pprint


def load_users(path):
    print("loading users from", path)
    with open(path) as handle:
        rows = handle.readlines()
    print("loaded", len(rows), "rows")
    return rows


def show_user(user):
    pprint(user)
    print("name:", user["name"])
    return user["name"]
