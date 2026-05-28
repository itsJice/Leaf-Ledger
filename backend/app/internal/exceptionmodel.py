import traceback
from pydantic import BaseModel
from typing import List, Sequence


class FrameDetail(BaseModel):
    filename: str
    frameName: str
    lineNumber: int | None
    codeLine: str | None


# NB! Duplicated in devx
class ExceptionModel(BaseModel):
    exceptionType: str
    message: str
    stackTrace: List[FrameDetail]


def exception_to_model(
    e: BaseException,
    root_dir: str | None = None,
    replace_paths: Sequence[tuple[str, str]] = (),
) -> ExceptionModel:
    """Convert exception to model.

    Optionally skip frames up to the first filename that lies in root_dir.
    If root_dir is not found, will return the entire stacktrace.
    """
    skip = root_dir is not None
    stackTrace: list[FrameDetail] = []
    for frame in traceback.extract_tb(e.__traceback__):
        # Skip until we find the first frame in the root dir
        if root_dir and frame.filename.startswith(root_dir):
            skip = False
        if skip:
            continue

        # Rewrite paths to be cleaner
        filename = frame.filename
        for old, new in replace_paths:
            if filename.startswith(old):
                filename = filename.replace(old, new)
                break

        stackTrace.append(
            FrameDetail(
                filename=filename,
                frameName=frame.name,
                lineNumber=frame.lineno,
                codeLine=frame.line,
            )
        )

    return ExceptionModel(
        exceptionType=type(e).__name__,
        message=str(e),
        stackTrace=stackTrace,
    )
