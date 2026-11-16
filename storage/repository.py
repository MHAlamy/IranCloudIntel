"""Persistence API for collection runs and price observations.

Write rules:
- identity rows (providers/sources/offerings) are idempotent upserts;
- collection_runs records every attempt, success or failure;
- price_observations is append-only: valid observations INSERT, failures
  never touch existing rows (stale-marking happens at display time).
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from extractors.schema import LLMPlanRow, NormalizedPlanRow
from storage.db import connect, init_db, utc_now_iso


class Repository:
    def __init__(self, db_path: str | Path):
        init_db(db_path)
        self._connection = connect(db_path)
        for table in ('price_observations', 'os_observations', 'resource_rates', 'os_rates'):
            self._connection.execute(f"CREATE TEMP VIEW published_{table} AS SELECT t.* FROM main.{table} t JOIN collection_runs cr ON cr.id=t.run_id WHERE cr.status='success'")

    def close(self) -> None:
        self._connection.close()

    # -- identity rows (idempotent) ---------------------------------------

    def ensure_provider(self, slug: str, name: str, official_url: str) -> int:
        self._connection.execute(
            """INSERT INTO providers (slug, name, official_url) VALUES (?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET name=excluded.name, official_url=excluded.official_url""",
            (slug, name, official_url),
        )
        self._connection.commit()
        # lastrowid is unreliable after ON CONFLICT DO UPDATE; always SELECT.
        row = self._connection.execute("SELECT id FROM providers WHERE slug=?", (slug,)).fetchone()
        return int(row["id"])

    def ensure_source(
        self, provider_id: int, service_type: str, url: str,
        collection_method: str, region_scope: str = "",
    ) -> int:
        self._connection.execute(
            """INSERT INTO sources (provider_id, service_type, url, collection_method, region_scope)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(provider_id, service_type, url) DO UPDATE SET
                 collection_method=excluded.collection_method,
                 region_scope=excluded.region_scope""",
            (provider_id, service_type, url, collection_method, region_scope),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT id FROM sources WHERE provider_id=? AND service_type=? AND url=?",
            (provider_id, service_type, url),
        ).fetchone()
        return int(row["id"])

    def ensure_offering(
        self, provider_id: int, service_type: str, plan_name: str,
        product_family: str = "", provider_tier_raw: str = "", region: str = "",
    ) -> int:
        self._connection.execute(
            """INSERT INTO offerings (provider_id, service_type, product_family, plan_name,
                                      provider_tier_raw, region)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(provider_id, service_type, product_family, plan_name,
                           provider_tier_raw, region) DO NOTHING""",
            (provider_id, service_type, product_family, plan_name, provider_tier_raw, region),
        )
        self._connection.commit()
        row = self._connection.execute(
            """SELECT id FROM offerings WHERE provider_id=? AND service_type=?
               AND product_family=? AND plan_name=? AND provider_tier_raw=? AND region=?""",
            (provider_id, service_type, product_family, plan_name, provider_tier_raw, region),
        ).fetchone()
        return int(row["id"])

    # -- collection runs ---------------------------------------------------

    def start_run(self, source_id: int, started_at: str | None = None) -> int:
        cursor = self._connection.execute(
            "INSERT INTO collection_runs (source_id, started_at, status) VALUES (?, ?, 'running')",
            (source_id, started_at or utc_now_iso()),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    def _check_publication(self, run_id: int, content_hash: str | None) -> None:
        source = self._connection.execute('SELECT source_id FROM collection_runs WHERE id=?', (run_id,)).fetchone()[0]
        previous = self._connection.execute("SELECT id, content_hash FROM collection_runs WHERE source_id=? AND status='success' ORDER BY id DESC LIMIT 1", (source,)).fetchone()
        count = sum(self._connection.execute(f'SELECT COUNT(*) FROM main.{t} WHERE run_id=?', (run_id,)).fetchone()[0] for t in ('price_observations','os_observations','resource_rates','os_rates'))
        if not count:
            if previous and content_hash and previous['content_hash'] == content_hash:
                return  # successful unchanged recheck
            raise ValueError('empty collection cannot be published')
        # Missing previously accepted identities require review, not silent partial publication.
        for table, key in (('price_observations','offering_id'), ('os_observations','offering_id'), ('resource_rates',"category || ':' || unit || ':' || tier_label || ':' || region"), ('os_rates',"category || ':' || unit || ':' || tier_label || ':' || range_label || ':' || region")):
            old = {r[0] for r in self._connection.execute(f"SELECT {key} FROM main.{table} WHERE run_id IN (SELECT id FROM collection_runs WHERE source_id=? AND status='success')", (source,))}
            new = {r[0] for r in self._connection.execute(f'SELECT {key} FROM main.{table} WHERE run_id=?', (run_id,))}
            if old - new:
                raise ValueError(f'incomplete {table}: previously accepted identities missing; review required')

    def freshness(self, service: str, max_age_hours: int = 48) -> list[dict]:
        from datetime import datetime, timezone
        result = []
        for source in self.list_sources():
            if source['service_type'] != service:
                continue
            runs = self.source_runs(source['id'], limit=1)
            latest = runs[0] if runs else None
            accepted = self._connection.execute("SELECT * FROM collection_runs WHERE source_id=? AND status='success' ORDER BY id DESC LIMIT 1", (source['id'],)).fetchone()
            checked = accepted['finished_at'] if accepted else None
            stale = not checked or (datetime.now(timezone.utc)-datetime.fromisoformat(checked)).total_seconds() > max_age_hours*3600 or (latest is not None and latest['status'] != 'success')
            result.append(dict(provider=source['provider_name'], last_checked=latest['started_at'] if latest else None, last_verified=checked, stale=stale))
        return result

    def publish_run(self, run_id: int, status: str, **metadata) -> None:
        """Collector completion: validate before atomic visibility transition."""
        if status == 'success':
            self._check_publication(run_id, metadata.get('content_hash'))
        self.finish_run(run_id, status, **metadata)

    def finish_run(
        self, run_id: int, status: str, http_status: int | None = None,
        content_hash: str | None = None, extractor_config_hash: str | None = None,
        evidence_path: str | None = None, model: str | None = None,
        schema_version: str | None = None, prompt_tokens: int = 0,
        completion_tokens: int = 0, error: str | None = None,
    ) -> None:
        self._connection.execute(
            """UPDATE collection_runs SET finished_at=?, status=?, http_status=?, content_hash=?,
               extractor_config_hash=?, evidence_path=?, model=?, schema_version=?,
               prompt_tokens=?, completion_tokens=?, error=? WHERE id=?""",
            (
                utc_now_iso(), status, http_status, content_hash, extractor_config_hash,
                evidence_path, model, schema_version, prompt_tokens, completion_tokens,
                error, run_id,
            ),
        )
        self._connection.commit()

    # -- price observations --------------------------------------------------

    def record_observation(
        self, run_id: int, offering_id: int, raw: "LLMPlanRow",
        normalized: NormalizedPlanRow,
        observed_at: str | None = None, evidence: str | None = None,
    ) -> int:
        """Append one validated observation. Canonical unit: monthly Toman.

        The raw LLM row is stored verbatim (price/currency/period exactly as
        the source printed them) alongside the normalized values.
        """
        if normalized.validation_status != "valid":
            raise ValueError("only valid observations may be recorded; suspect rows go to review")
        price_in_toman = normalized.price_in_toman
        if price_in_toman is None:
            raise ValueError("price_in_toman is required for the canonical monthly-Toman unit")
        cursor = self._connection.execute(
            """INSERT INTO price_observations (
                   offering_id, run_id, observed_at, price_value, price_in_toman,
                   currency, billing_period, price_raw, currency_raw, billing_period_raw,
                   vcpu, ram_gb, disk_gb, disk_type, plan_url,
                   validation_status, validation_issues, evidence, conversion_hours)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                offering_id, run_id, observed_at or utc_now_iso(),
                str(normalized.price_value), str(price_in_toman),
                normalized.currency, normalized.billing_period,
                raw.price_raw, raw.currency_raw, raw.billing_period_raw,
                normalized.vcpu,
                str(normalized.ram_gb) if normalized.ram_gb is not None else None,
                str(normalized.disk_gb) if normalized.disk_gb is not None else None,
                normalized.disk_type, normalized.plan_url,
                normalized.validation_status,
                json.dumps(normalized.validation_issues, ensure_ascii=False),
                evidence or raw.evidence, normalized.conversion_hours,
            ),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    # -- read paths for the dashboard ----------------------------------------

    def latest_observations(
        self, service_type: str | None = None, provider_id: int | None = None,
    ) -> list[sqlite3.Row]:
        """Latest valid observation per offering, for dashboard tables."""
        query = """
            SELECT o.*, off.plan_name, off.region, off.provider_tier_raw,
                   off.product_family, off.provider_id, off.service_type,
                   p.slug AS provider_slug, p.name AS provider_name
            FROM offerings off
            JOIN providers p ON p.id = off.provider_id
            JOIN price_observations o ON o.id = (
                SELECT po.id FROM published_price_observations po
                WHERE po.offering_id = off.id AND po.validation_status = 'valid'
                ORDER BY po.observed_at DESC, po.id DESC LIMIT 1
            )
            WHERE (? IS NULL OR off.service_type = ?)
              AND (? IS NULL OR off.provider_id = ?)
            ORDER BY p.name, off.plan_name
        """
        return self._connection.execute(query, (service_type, service_type, provider_id, provider_id)).fetchall()

    def offering_history(self, offering_id: int) -> list[sqlite3.Row]:
        return self._connection.execute(
            """SELECT * FROM published_price_observations WHERE offering_id=?
               ORDER BY observed_at DESC, id DESC""",
            (offering_id,),
        ).fetchall()

    # -- resource rates ----------------------------------------------------

    def record_rates(
        self, run_id: int, provider_id: int, rates: list,
        observed_at: str | None = None,
    ) -> int:
        """Store parsed component rate rows (providers that publish them)."""
        count = 0
        for rate in rates:
            self._connection.execute(
                """INSERT INTO resource_rates (
                       provider_id, run_id, category, region, unit, tier_label,
                       amount_toman, billing_period, observed_at, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'monthly', ?, ?)""",
                (
                    provider_id, run_id, rate.category, rate.region, rate.unit,
                    rate.tier_label, rate.amount_toman, observed_at or utc_now_iso(),
                    rate.evidence,
                ),
            )
            count += 1
        self._connection.commit()
        return count

    def latest_rates(self, provider_id: int, region: str = "iran", staged_run_id: int | None = None) -> list[sqlite3.Row]:
        """Newest rate row per (category, unit, tier_label) for a provider/region."""
        if staged_run_id is not None:
            return self._connection.execute('SELECT * FROM main.resource_rates WHERE provider_id=? AND region=? AND run_id=?', (provider_id, region, staged_run_id)).fetchall()
        return self._connection.execute(
            """SELECT r.* FROM published_resource_rates r
               JOIN (
                   SELECT category, unit, tier_label, MAX(id) AS max_id
                   FROM published_resource_rates WHERE provider_id=? AND region=?
                   GROUP BY category, unit, tier_label
               ) latest ON r.id = latest.max_id
               ORDER BY r.category, r.tier_label""",
            (provider_id, region),
        ).fetchall()

    def set_rate_verification(self, observation_id: int, status: str, detail: str = "") -> None:
        self._connection.execute(
            "UPDATE price_observations SET rate_verification=?, rate_verification_detail=? WHERE id=?",
            (status, detail, observation_id),
        )
        self._connection.commit()

    # -- dashboard read helpers ------------------------------------------------

    def get_offering(self, offering_id: int) -> sqlite3.Row | None:
        return self._connection.execute(
            """SELECT off.*, p.slug AS provider_slug, p.name AS provider_name
               FROM offerings off JOIN providers p ON p.id = off.provider_id
               WHERE off.id=?""",
            (offering_id,),
        ).fetchone()

    def list_sources(self) -> list[sqlite3.Row]:
        return self._connection.execute(
            """SELECT s.*, p.slug AS provider_slug, p.name AS provider_name
               FROM sources s JOIN providers p ON p.id = s.provider_id
               ORDER BY p.slug, s.service_type"""
        ).fetchall()

    def source_runs(self, source_id: int, limit: int = 5) -> list[sqlite3.Row]:
        return self._connection.execute(
            """SELECT * FROM collection_runs WHERE source_id=?
               ORDER BY started_at DESC, id DESC LIMIT ?""",
            (source_id, limit),
        ).fetchall()

    def rate_count(self, provider_id: int) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS c FROM published_resource_rates WHERE provider_id=?", (provider_id,)
        ).fetchone()
        return int(row["c"])

    # -- skip-unchanged decision ----------------------------------------------

    def last_successful_extraction(self, source_id: int, extractor_config_hash: str) -> sqlite3.Row | None:
        """The newest successful run for this source under the same extractor config."""
        return self._connection.execute(
            """SELECT * FROM collection_runs
               WHERE source_id=? AND status='success' AND extractor_config_hash=?
               ORDER BY started_at DESC, id DESC LIMIT 1""",
            (source_id, extractor_config_hash),
        ).fetchone()

    def should_skip_extraction(
        self, source_id: int, content_hash: str, extractor_config_hash: str,
    ) -> bool:
        """True when identical content was already extracted under the same config."""
        last = self.last_successful_extraction(source_id, extractor_config_hash)
        return last is not None and last["content_hash"] == content_hash

    # -- object storage ----------------------------------------------------
    # Service-specific persistence (price_gathering_guide.md 7): OS pricing is
    # never forced into the VM-shaped columns of price_observations.

    def record_os_observation(
        self, run_id: int, offering_id: int, normalized, *,
        price_raw: str, currency_raw: str, billing_period_raw: str,
        evidence: str, overage_storage_toman_gb: str | None = None,
        overage_traffic_toman_gb: str | None = None, observed_at: str | None = None,
    ) -> int:
        """Append one validated Object Storage plan observation (append-only)."""
        if normalized.validation_status != "valid":
            raise ValueError("only valid observations may be recorded; suspect rows go to review")
        cursor = self._connection.execute(
            """INSERT INTO os_observations (
                   offering_id, run_id, observed_at, plan_status, price_value,
                   price_in_toman, currency, billing_period, price_raw, currency_raw,
                   billing_period_raw, storage_included_gb, traffic_included_gb,
                   requests_included, storage_unlimited, traffic_unlimited,
                   requests_unlimited, overage_storage_toman_gb,
                   overage_traffic_toman_gb, plan_url, validation_status,
                   validation_issues, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                offering_id, run_id, observed_at or utc_now_iso(),
                normalized.plan_status,
                str(normalized.price_value) if normalized.price_value is not None else None,
                str(normalized.price_in_toman) if normalized.price_in_toman is not None else None,
                normalized.currency, normalized.billing_period,
                price_raw, currency_raw, billing_period_raw,
                str(normalized.storage_included_gb) if normalized.storage_included_gb is not None else None,
                str(normalized.traffic_included_gb) if normalized.traffic_included_gb is not None else None,
                normalized.requests_included,
                int(normalized.storage_unlimited), int(normalized.traffic_unlimited),
                int(normalized.requests_unlimited),
                overage_storage_toman_gb, overage_traffic_toman_gb,
                normalized.plan_url, normalized.validation_status,
                json.dumps(normalized.validation_issues, ensure_ascii=False),
                evidence,
            ),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    def latest_os_observations(self, provider_id: int | None = None) -> list[sqlite3.Row]:
        """Latest valid OS observation per offering, joined with identity."""
        query = """
            SELECT o.*, off.plan_name, off.region, off.product_family,
                   off.provider_id, off.service_type,
                   p.slug AS provider_slug, p.name AS provider_name
            FROM offerings off
            JOIN providers p ON p.id = off.provider_id
            JOIN os_observations o ON o.id = (
                SELECT oo.id FROM published_os_observations oo
                WHERE oo.offering_id = off.id AND oo.validation_status = 'valid'
                ORDER BY oo.observed_at DESC, oo.id DESC LIMIT 1
            )
            WHERE off.service_type = 'object_storage'
              AND (? IS NULL OR off.provider_id = ?)
            ORDER BY p.name, off.plan_name
        """
        return self._connection.execute(query, (provider_id, provider_id)).fetchall()

    def record_os_rates(self, run_id: int, provider_id: int, rates: list) -> int:
        """Store parsed Object Storage PAYG/overage rate rows."""
        count = 0
        for rate in rates:
            self._connection.execute(
                """INSERT INTO os_rates (
                       provider_id, run_id, observed_at, category, unit, tier_label,
                       range_label, range_min_gb, range_max_gb, amount_toman, is_free,
                       region, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    provider_id, run_id, utc_now_iso(), rate.category, rate.unit,
                    rate.tier_label, rate.range_label, rate.range_min_gb,
                    rate.range_max_gb, rate.amount_toman, int(rate.is_free),
                    getattr(rate, "region", "iran") or "iran", rate.evidence,
                ),
            )
            count += 1
        self._connection.commit()
        return count

    def latest_os_rates(self, provider_id: int, region: str = "iran") -> list[sqlite3.Row]:
        """Newest OS rate row per (category, unit, tier_label, range_label)."""
        return self._connection.execute(
            """SELECT r.* FROM published_os_rates r
               JOIN (
                   SELECT category, unit, tier_label, range_label, MAX(id) AS max_id
                   FROM published_os_rates WHERE provider_id=? AND region=?
                   GROUP BY category, unit, tier_label, range_label
               ) latest ON r.id = latest.max_id
               ORDER BY r.category, r.tier_label, r.range_min_gb""",
            (provider_id, region),
        ).fetchall()
