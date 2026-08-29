from dataclasses import dataclass


@dataclass(slots=True)
class ServiceError(Exception):
    code: str
    message: str
    status_code: int
    retryable: bool = False


def not_found(entity: str, identifier: str) -> ServiceError:
    return ServiceError(
        code=f"{entity.upper()}_NOT_FOUND",
        message=f"{entity.title()} '{identifier}' was not found.",
        status_code=404,
    )
