"""Things every route needs: the services, the caller's tenant and a permission check."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from mirrorguard.api.auth import Tenant
from mirrorguard.api.services import Services
from mirrorguard.tenancy.roles import Permission, allows


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


def require(permission: Permission):
    """A dependency that lets the request through only if the key's role allows it."""

    async def check(tenant: Annotated[Tenant, Depends(current_tenant)]) -> Tenant:
        if not allows(tenant.role, permission):
            raise HTTPException(
                403, f"This API key has the '{tenant.role}' role, which cannot do this."
            )
        return tenant

    return Depends(check)


ChatTenant = Annotated[Tenant, require(Permission.CHAT)]
ReadTenant = Annotated[Tenant, require(Permission.READ)]
ReviewTenant = Annotated[Tenant, require(Permission.REVIEW)]
ManageTenant = Annotated[Tenant, require(Permission.MANAGE)]
