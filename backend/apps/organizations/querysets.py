def for_organization(queryset, organization):

    if organization is None:
        return queryset.none()

    return queryset.filter(
        organization_id=organization.pk
    )
    