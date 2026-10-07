"""Things every route needs: the services and the caller's tenant."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from mirrorguard.api.auth import Tenant
from mirrorguard.api.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


async def current_tenant(
    services: ServicesDep, authorization: Annotated[str | None, Header()] = None
) -> Tenant:
    scheme, _, key = (authorization or "").partition(" ")
    key = key.strip()
    tenant = None
    if scheme.lower() == "bearer" and key:
        tenant = await services.authenticator.authenticate(key)
    if tenant is None:
        raise HTTPException(401, "Missing or invalid API key.")
    if not await services.rate_limiter.allow(tenant.id):
        raise HTTPException(429, "Rate limit reached. Try again in a minute.")
    return tenant


TenantDep = Annotated[Tenant, Depends(current_tenant)]
