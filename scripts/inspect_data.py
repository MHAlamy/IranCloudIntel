"""Bounded, read-only SQLite inspection. Never migrates or collects."""
import argparse
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent.parent

QUERIES = {
    'summary': """SELECT p.slug, s.service_type, cr.status, COUNT(*) AS runs
        FROM collection_runs cr JOIN sources s ON s.id=cr.source_id
        JOIN providers p ON p.id=s.provider_id
        GROUP BY p.slug, s.service_type, cr.status ORDER BY p.slug, s.service_type""",
    'providers': """SELECT p.slug, s.service_type, s.url
        FROM sources s JOIN providers p ON p.id=s.provider_id ORDER BY p.slug""",
    'runs': """SELECT id, source_id, status, started_at, finished_at,
        prompt_tokens, completion_tokens, error
        FROM collection_runs ORDER BY id DESC""",
    'verification': """SELECT off.plan_name, po.rate_verification,
        po.rate_verification_detail FROM price_observations po
        JOIN offerings off ON off.id=po.offering_id
        JOIN collection_runs cr ON cr.id=po.run_id WHERE cr.status='success'
        ORDER BY po.id DESC""",
}


def inspect(db: Path, topic: str, limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 1000:
        raise ValueError('limit must be between 1 and 1000')
    # mode=ro rejects missing DBs instead of creating an empty database.
    connection = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        return [dict(row) for row in connection.execute(QUERIES[topic] + ' LIMIT ?', (limit,))]
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('topic', choices=QUERIES, nargs='?', default='summary')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'cloud_intel.db')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect(args.db, args.topic, args.limit), ensure_ascii=True, indent=2))
    except (sqlite3.Error, ValueError) as exc:
        parser.exit(1, f'Inspection failed: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
