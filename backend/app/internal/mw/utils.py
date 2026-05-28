from starlette.requests import Request


def set_header(request: Request, header: str, value: str) -> None:
    """Adds the given Header to the available Request headers.

    If the Header already exists, its value is overwritten.
    """
    hkey = header.encode("latin-1")
    hval = value.encode("latin-1")
    request.scope["headers"] = [
        *(h for h in request.scope["headers"] if h[0] != hkey),
        (hkey, hval),
    ]


def remove_header(request: Request, header: str) -> None:
    """Removes the given Header from the available Request headers."""
    hkey = header.encode("latin-1")
    request.scope["headers"] = [h for h in request.scope["headers"] if h[0] != hkey]
