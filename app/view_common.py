"""Shared identity lookups for dashboard view builders."""
from storage.repository import Repository
from comparison.matching import PlanView

def _provider_id(repo: Repository, slug: str) -> int | None:
    row = repo._connection.execute("SELECT id FROM providers WHERE slug=?", (slug,)).fetchone()
    return int(row["id"]) if row else None


def _offering_id(repo: Repository, slug: str, plan: PlanView) -> int | None:
    row = repo._connection.execute(
        """SELECT off.id FROM offerings off JOIN providers p ON p.id=off.provider_id
           WHERE p.slug=? AND off.plan_name=? AND off.region=?""",
        (slug, plan.plan_name, plan.region),
    ).fetchone()
    return int(row["id"]) if row else None


# -- Object Storage view (price_gathering_guide.md 7) -------------------------

