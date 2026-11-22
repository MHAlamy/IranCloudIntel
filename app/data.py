"""Compatibility exports. Implementation lives in service-specific view modules."""
from app.vm_view import (
    TIER_LABELS_FA, SIZE_LABELS_FA, BASIS_LABELS_FA, VERIFICATION_LABELS_FA,
    build_plan_views, build_vm_view,
)
from app.os_view import OS_BASIS_LABELS_FA, build_os_view
from app.paas_view import build_paas_view
from app.dbaas_view import build_dbaas_view
from app.status_view import build_status_view
from comparison.tariffs import tier_cost as _tier_cost
