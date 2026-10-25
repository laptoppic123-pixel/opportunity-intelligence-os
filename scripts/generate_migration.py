"""Generate reviewable DDL only; this script never connects to a database."""

from pathlib import Path
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable, CreateIndex
from opportunity_intelligence.schema import metadata


def main():
    root = Path(__file__).resolve().parents[1]
    parts = [
        "-- Opportunity Intelligence OS V2. Generated schema. No seed data or production writes during BUILD.\nBEGIN;"
    ]
    for table in metadata.sorted_tables:
        parts.append(str(CreateTable(table, if_not_exists=True).compile(dialect=postgresql.dialect())) + ";")
        parts.extend(
            str(CreateIndex(index, if_not_exists=True).compile(dialect=postgresql.dialect())) + ";"
            for index in table.indexes
        )
        parts.append(
            f"ALTER TABLE public.{table.name} ENABLE ROW LEVEL SECURITY;\nALTER TABLE public.{table.name} FORCE ROW LEVEL SECURITY;\nREVOKE ALL ON TABLE public.{table.name} FROM PUBLIC, anon, authenticated;\nGRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table.name} TO service_role;"
        )
    parts.append(
        "-- No anon/authenticated policies: access is denied. Only the trusted server key accesses data.\nCOMMIT;\n"
    )
    target = root / "db/migrations/001_schema.sql"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(line.rstrip() for line in "\n\n".join(parts).splitlines()) + "\n", encoding="utf-8"
    )
    pairs = []
    for table in metadata.sorted_tables:
        if table.name == "job_locks":
            continue
        pairs.append(
            "'"
            + table.name
            + "', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public."
            + table.name
            + " WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb)"
        )
    snapshot = (
        """-- One SQL statement supplies a consistent owner snapshot for exports and encrypted backups.
BEGIN;
CREATE OR REPLACE FUNCTION public.oi_snapshot(p_owner text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public AS $$
SELECT jsonb_build_object(
"""
        + ",\n".join(pairs)
        + "\n);\n$$;\nREVOKE ALL ON FUNCTION public.oi_snapshot(text) FROM PUBLIC,anon,authenticated;\nGRANT EXECUTE ON FUNCTION public.oi_snapshot(text) TO service_role;\nCOMMIT;\n"
    )
    (root / "db/migrations/003_consistent_snapshot.sql").write_text(snapshot, encoding="utf-8")
    print("Generated", target.name, "for", len(metadata.tables), "tables. Not applied.")


if __name__ == "__main__":
    main()
