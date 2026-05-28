import os

import httpx
from fastapi import HTTPException

from app.internal.dbapi import get_dbapi_client


def get_integration_access_token(
    *, provider_key: str, integration_id: str | None = None
) -> str:
    """
    Mints an access token for a given integration provider by calling the Databutton project API.

    Args:
        provider_key: The key of the provider (e.g., 'google', 'stripe').
        integration_id: Optional integration ID parameter.

    Returns:
        The minted access token.

    Raises:
        HTTPException: If the access token cannot be minted.
    """

    payload = {
        "providerKey": provider_key,
        "projectId": os.environ.get("DATABUTTON_PROJECT_ID"),
    }

    if integration_id is not None:
        payload["integrationId"] = integration_id

    client = get_dbapi_client()

    try:
        response = client.post("/integrations/mint-access-token", json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        # Assuming the response contains a JSON body with the access token
        response_data = response.json()

        access_token = response_data.get(
            "accessToken"
        )  # Adjusted to accessToken based on common conventions

        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="Access token not found in response from minting endpoint.",
            )

        return access_token

    except httpx.HTTPStatusError as e:
        detail = f"Failed to mint access token for '{provider_key}'. Status: {e.response.status_code}, Response: {e.response.text}"
        print(detail)
        raise HTTPException(status_code=e.response.status_code, detail=detail) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500, detail=f"A network error occurred: {e}"
        ) from e
