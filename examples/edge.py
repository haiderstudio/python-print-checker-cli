# Edge cases: things that look like prints but are not calls.

# print("in a comment") is not a call.


def describe():
    """A docstring that says print("hello") is only text."""
    text = "pprint(user) inside a string is not a call"
    return text


class Logger:
    def print(self, message):
        self.lines.append(message)


def quiet():
    printer = print  # mentioning print without calling it
    return printer
