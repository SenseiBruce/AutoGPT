"""Airtable webhook, OAuth, and base API helpers."""

import base64
from enum import Enum
from logging import getLogger
from typing import Any
from urllib.parse import quote, urlencode

from backend.sdk import BaseModel, Credentials, Requests

logger = getLogger(__name__)

from ._api_types import WebhookSpecification, _convert_bools

async def create_webhook(
    credentials: Credentials,
    base_id: str,
    webhook_specification: WebhookSpecification,
    notification_url: str | None = None,
) -> Any:

    params: dict[str, Any] = {
        "specification": {
            "options": {
                "filters": webhook_specification.filters.model_dump(exclude_unset=True),
            }
        },
    }
    if webhook_specification.includes:
        params["specification"]["options"]["includes"] = (
            webhook_specification.includes.model_dump(exclude_unset=True)
        )
    if notification_url:
        params["notificationUrl"] = notification_url

    response = await Requests().post(
        f"https://api.airtable.com/v0/bases/{base_id}/webhooks",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )
    return response.json()


async def delete_webhook(
    credentials: Credentials,
    base_id: str,
    webhook_id: str,
) -> Any:

    response = await Requests().delete(
        f"https://api.airtable.com/v0/bases/{base_id}/webhooks/{webhook_id}",
        headers={"Authorization": credentials.auth_header()},
    )
    return response.json()


async def list_webhook_payloads(
    credentials: Credentials,
    base_id: str,
    webhook_id: str,
    cursor: str | None = None,
    limit: int | None = None,
) -> ListWebhookPayloadsResponse:

    query_string = ""
    if cursor:
        query_string += f"cursor={cursor}"
    if limit:
        query_string += f"limit={limit}"

    if query_string:
        query_string = f"?{query_string}"

    response = await Requests().get(
        f"https://api.airtable.com/v0/bases/{base_id}/webhooks/{webhook_id}/payloads{query_string}",
        headers={"Authorization": credentials.auth_header()},
    )
    try:
        logger.info(f"Response: {response.json()}")
        return ListWebhookPayloadsResponse(
            payloads=response.json().get("payloads", []),
            cursor=response.json().get("cursor"),
            might_have_more=response.json().get("might_have_more") == "True",
            payloadFormat=response.json().get("payloadFormat", "v0"),
        )
    except Exception as e:
        raise ValueError(
            f"Failed to validate webhook payloads response: {e}\nResponse: {response.json()}"
        )


async def list_webhooks(
    credentials: Credentials,
    base_id: str,
) -> Any:

    response = await Requests().get(
        f"https://api.airtable.com/v0/bases/{base_id}/webhooks",
        headers={"Authorization": credentials.auth_header()},
    )
    return response.json()


class OAuthAuthorizeRequest(BaseModel):
    """OAuth authorization request parameters for Airtable.

    Parameters:
        client_id: An opaque string that identifies your integration with Airtable
        redirect_uri: The URI for the authorize response redirect. Must exactly match a redirect URI
            associated with your integration. HTTPS is required for any URI beside localhost.
        response_type: The string "code"
        scope: A space delimited list of unique scopes. All scopes must be valid Airtable defined scopes
            that have been selected for your integration. At least one scope is required.
        state: A cryptographically generated, opaque string for CSRF protection
        code_challenge: The base64 url-encoding of the sha256 of the code_verifier. Protects against
            man-in-the-middle grant code injection attacks. Part of the PKCE extension of OAuth.
        code_challenge_method: The string "S256"
    """

    client_id: str
    redirect_uri: str
    response_type: str = "code"
    scope: str
    state: str
    code_challenge: str
    code_challenge_method: str = "S256"


class OAuthTokenRequest(BaseModel):
    """OAuth token request parameters for Airtable.

    These parameters must be formatted via application/x-www-form-urlencoded encoding.

    Parameters:
        code: The grant code generated during the authorization request. Can only be used once.
        client_id: The client_id used in the authorization request that generated the code.
            Optional if your integration has a client_secret. Used to prevent MITM attacks.
        redirect_uri: The redirect_uri used in the authorization request that generated the code.
            Used to prevent MITM attacks.
        grant_type: The string "authorization_code".
        code_verifier: A cryptographically generated, opaque string used to generate the
            code_challenge parameter in the authorization request that generated the code.
    """

    code: str
    client_id: str
    redirect_uri: str
    grant_type: str = "authorization_code"
    code_verifier: str


class OAuthRefreshTokenRequest(BaseModel):
    """OAuth token refresh request parameters for Airtable.

    These parameters must be formatted via application/x-www-form-urlencoded encoding.

    Parameters:
        refresh_token: The saved refresh token from the previous token grant.
        client_id: Required if your integration does not have a client_secret.
            Used to prevent MITM attacks.
        grant_type: The string "refresh_token".
        scope: If specified, a subset of the token's existing scopes. Optional.
    """

    refresh_token: str
    client_id: str | None = None
    grant_type: str = "refresh_token"
    scope: str | None = None


class OAuthTokenResponse(BaseModel):
    """OAuth token response from Airtable.

    Successful response has HTTP status code 200 (OK).

    Parameters:
        access_token: An opaque string. Can be used to make requests to the Airtable API on behalf
            of the user, and cannot be recovered if lost.
        refresh_token: An opaque string. Can be used to request a new access token after the current
            one expires.
        token_type: The string "Bearer " (space intentional)
        scope: A string that is a space delimited list of scopes granted to this access token. Can be
            recovered using the get userId and scopes endpoint.
        expires_in: An integer. Time in seconds until the access token expires (expected value is 60 minutes).
        refresh_expires_in: An integer. Time in seconds until the refresh token expires (expected value is 60 days).
    """

    access_token: str
    refresh_token: str
    token_type: str
    scope: str
    expires_in: int
    refresh_expires_in: int


def make_oauth_authorize_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    code_challenge: str,
) -> str:
    """
    Generate the OAuth authorization URL for Airtable.

    Args:
        client_id: An opaque string that identifies your integration with Airtable
        redirect_uri: The URI for the authorize response redirect
        scope: A space delimited list of unique scopes
        state: A cryptographically generated, opaque string for CSRF protection
        code_challenge: The base64 url-encoding of the sha256 of the code_verifier
        code_challenge_method: The string "S256" (default)
        response_type: The string "code" (default)

    Returns:
        The authorization URL that the user should visit
    """
    # Validate the request parameters
    request_params = OAuthAuthorizeRequest(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=" ".join(scopes),
        state=state,
        code_challenge=code_challenge,
    )

    # Build the authorization URL
    base_url = "https://airtable.com/oauth2/v1/authorize"
    query_string = urlencode(request_params.model_dump(exclude_none=True))

    return f"{base_url}?{query_string}"


async def oauth_exchange_code_for_tokens(
    client_id: str,
    code_verifier: bytes,
    code: str,
    redirect_uri: str,
    client_secret: str | None = None,
) -> OAuthTokenResponse:
    """
    Exchange an authorization code for access and refresh tokens.

    Args:
        client_id: The Airtable integration client ID.
        code_verifier: The original code_verifier (required for PKCE).
        code: The authorization code returned by Airtable.
        redirect_uri: The redirect URI used during authorization.
        client_secret: Integration client secret if available (optional).

    Returns:
        Parsed JSON response containing the access token, refresh token, scope, etc.
    """

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # Add Authorization header for confidential clients
    if client_secret:
        credentials_encoded = base64.urlsafe_b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {credentials_encoded}"

    data = OAuthTokenRequest(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        grant_type="authorization_code",
        code_verifier=code_verifier.decode("utf-8"),
    ).model_dump(exclude_none=True)

    response = await Requests().post(
        "https://airtable.com/oauth2/v1/token",
        headers=headers,
        data=data,
    )

    if response.ok:
        return OAuthTokenResponse.model_validate(response.json())
    raise ValueError(
        f"Failed to exchange code for tokens: {response.status} {response.text}"
    )


# NEW helper for refreshing tokens
async def oauth_refresh_tokens(
    client_id: str,
    refresh_token: str,
    client_secret: str | None = None,
) -> OAuthTokenResponse:
    """
    Refresh an expired (or soon-to-expire) access token.

    Args:
        client_id: The Airtable integration client ID.
        refresh_token: The refresh token previously issued by Airtable.
        client_secret: Integration client secret if available (optional).

    Returns:
        Parsed JSON response containing the new tokens and metadata.
        https://airtable.com/oauth2/v1/authorize?client_id=7642abbb-8fbc-494c-b6e0-58484364e28c&redirect_uri=https%3A%2F%2Fdev-builder.agpt.co%2Fauth%2Fintegrations%2Foauth_callback&response_type=code&scope=&state=OcmqX6Y5MTkhHLc6vkbR6uEtSiZHawzEUcxDscqkWRk&code_challenge=v2Ly1CcG8UkCXJ2n--TEKZc6HeKaN1wrZLgIr_qVnJ8&code_challenge_method=S256
    """

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    if client_secret:
        credentials_encoded = base64.urlsafe_b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {credentials_encoded}"

    data = OAuthRefreshTokenRequest(
        refresh_token=refresh_token,
        client_id=client_id,
        grant_type="refresh_token",
    ).model_dump(exclude_none=True)

    response = await Requests().post(
        "https://airtable.com/oauth2/v1/token",
        headers=headers,
        data=data,
    )

    if response.ok:
        return OAuthTokenResponse.model_validate(response.json())
    raise ValueError(f"Failed to refresh tokens: {response.status} {response.text}")


#################################################################
# Base Management
#################################################################


async def create_base(
    credentials: Credentials,
    workspace_id: str,
    name: str,
    tables: list[dict] = [
        {
            "description": "Default table",
            "name": "Default table",
            "fields": [
                {
                    "name": "ID",
                    "type": "number",
                    "description": "Auto-incrementing ID field",
                    "options": {"precision": 0},
                }
            ],
        }
    ],
) -> dict:
    """
    Create a new base in Airtable.

    Args:
        credentials: Airtable API credentials
        workspace_id: The workspace ID where the base will be created
        name: The name of the new base
        tables: Optional list of table objects to create in the base

    Returns:
        dict: Response containing the created base information
    """
    params: dict[str, Any] = {
        "name": name,
        "workspaceId": workspace_id,
    }

    if tables:
        params["tables"] = tables

    print(params)

    response = await Requests().post(
        "https://api.airtable.com/v0/meta/bases",
        headers={
            "Authorization": credentials.auth_header(),
            "Content-Type": "application/json",
        },
        json=_convert_bools(params),
    )

    return response.json()


async def list_bases(
    credentials: Credentials,
    offset: str | None = None,
) -> dict:
    """
    List all bases that the authenticated user has access to.

    Args:
        credentials: Airtable API credentials
        offset: Optional pagination offset

    Returns:
        dict: Response containing the list of bases
    """
    params = {}
    if offset:
        params["offset"] = offset

    response = await Requests().get(
        "https://api.airtable.com/v0/meta/bases",
        headers={"Authorization": credentials.auth_header()},
        params=params,
    )

    return response.json()


async def get_base_tables(
    credentials: Credentials,
    base_id: str,
) -> list[dict]:
    """
    Get all tables for a specific base.

    Args:
        credentials: Airtable API credentials
        base_id: The ID of the base

    Returns:
        list[dict]: List of table objects with their schemas
    """
    response = await Requests().get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers={"Authorization": credentials.auth_header()},
    )

    data = response.json()
    return data.get("tables", [])
