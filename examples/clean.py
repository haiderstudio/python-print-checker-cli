# A small module with no leftover prints — it passes.
# A comment that mentions print("hello") is not a call.

import logging

logger = logging.getLogger(__name__)


def greet(name):
    """Return a greeting. The print inside this string is not a call."""
    message = "print('hello') is only text here"
    logger.debug("greeting %s", name)
    return "Hello, " + name + " — " + message


def total(numbers):
    return sum(numbers)
