"""Explicit model availability boundary; no inference is implemented."""


class Brain:
    @property
    def connected(self) -> bool:
        return False
