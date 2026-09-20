"""Domain exceptions for MatterGen generation jobs."""


class GenerationError(Exception):
    """Base generation error with a stable API-facing error code."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class GenerationDisabledError(GenerationError):
    """Raised when MatterGen generation is disabled."""

    def __init__(self):
        super().__init__(
            "MATTERGEN_DISABLED",
            "MatterGen 生成功能当前已禁用。",
            status_code=503,
        )


class JobNotFoundError(GenerationError):
    """Raised when a generation job does not exist."""

    def __init__(self, job_id: str):
        super().__init__(
            "JOB_NOT_FOUND",
            f"生成任务不存在：{job_id}",
            status_code=404,
        )


class InvalidJobStateError(GenerationError):
    """Raised when an operation is invalid for the current job state."""

    def __init__(self, message: str):
        super().__init__("INVALID_JOB_STATE", message, status_code=409)

