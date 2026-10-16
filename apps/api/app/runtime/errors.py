class ExecutionError(Exception):
    def __init__(self, code: str, message: str, *, status: str = "failed", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "status": self.status}
