class SpekyError(Exception):
    """An error with a stable code and an actionable fix, reported as JSON by the CLI."""

    def __init__(self, code: str, message: str, fix: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix

    def to_dict(self) -> dict:
        error = {"code": self.code, "message": self.message}
        if self.fix:
            error["fix"] = self.fix
        return error
