from django.db import transaction

from .models import Organization, Membership


@transaction.atomic
def create_organization(
    *,
    name,
    slug,
    created_by,
    description=""
):

    organization = Organization.objects.create(
        name=name,
        slug=slug,
        description=description,
        created_by=created_by
    )

    Membership.objects.create(
        organization=organization,
        user=created_by,
        role=Membership.Role.OWNER,
        status=Membership.Status.ACTIVE
    )

    return organization