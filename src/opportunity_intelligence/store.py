from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
from uuid import uuid4, uuid5, NAMESPACE_URL
import httpx
from sqlalchemy import create_engine, select, and_, event
from sqlalchemy.pool import StaticPool
from .config import Settings
from .schema import TABLES, metadata, now


class Store:
    """Owner-scoped repository; SQLite exists only in explicitly selected demo/test mode."""

    def __init__(self, settings: Settings, *, memory=False):
        self.settings = settings
        self.owner = settings.namespace
        self._mutex = threading.RLock()
        self.engine = None
        if settings.demo:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(
                "sqlite://" if memory else "sqlite:///" + str(settings.data_dir / "demo.sqlite3"),
                connect_args={"check_same_thread": False},
                **({"poolclass": StaticPool} if memory else {}),
            )

            @event.listens_for(self.engine, "connect")
            def foreign_keys(connection, record):
                connection.execute("PRAGMA foreign_keys=ON")

            metadata.create_all(self.engine)
        else:
            settings.require_connection()

    def stable_id(self, *parts):
        return str(uuid5(NAMESPACE_URL, self.owner + ":" + ":".join(parts)))

    def _table(self, name):
        if name not in TABLES:
            raise ValueError("Unknown table")
        return TABLES[name]

    def _http(self, method, path, **kwargs):
        self.settings.require_live()
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            r = client.request(
                method,
                self.settings.supabase_url.rstrip("/") + "/rest/v1/" + path,
                headers={
                    "apikey": self.settings.secret_key,
                    "Authorization": "Bearer " + self.settings.secret_key,
                    "Prefer": "return=representation",
                },
                **kwargs,
            )
        if r.status_code >= 300:
            raise RuntimeError(
                f"Supabase request failed (HTTP {r.status_code}); run doctor after connection."
            )
        return r.json() if r.content else None

    def rpc(self, name, values):
        return self._http("POST", "rpc/" + name, json=values)

    def list(self, name, /, *, limit=500, offset=0, **filters):
        t = self._table(name)
        if not set(filters).issubset(t.c.keys()):
            raise ValueError("Unknown filter")
        if self.engine:
            q = select(t).where(t.c.owner_id == self.owner)
            for k, v in filters.items():
                q = q.where(t.c[k] == v)
            with self.engine.connect() as c:
                return [
                    dict(r)
                    for r in c.execute(
                        q.order_by(t.c.created_at, t.c.id).limit(limit).offset(offset)
                    ).mappings()
                ]
        return self._http(
            "GET",
            name,
            params={
                "owner_id": "eq." + self.owner,
                **{
                    k: "eq." + str(v).lower() if isinstance(v, bool) else "eq." + str(v)
                    for k, v in filters.items()
                },
                "order": "created_at.asc,id.asc",
                "limit": limit,
                "offset": offset,
            },
        )

    def all(self, name, /, **filters):
        rows = []
        for offset in range(0, 50000, 500):
            batch = self.list(name, offset=offset, **filters)
            rows.extend(batch)
            if len(batch) < 500:
                return rows
        raise RuntimeError("Export/read safety bound reached. Apply retention or narrow the query.")

    def get(self, name, identifier):
        rows = self.list(name, id=identifier, limit=1)
        return rows[0] if rows else None

    def add(self, name, values):
        t = self._table(name)
        row = {"id": str(uuid4()), "created_at": now(), "updated_at": now(), **values, "owner_id": self.owner}
        if not set(row).issubset(t.c.keys()):
            raise ValueError("Unknown column")
        if self.engine:
            with self._mutex, self.engine.begin() as c:
                c.execute(t.insert().values(**row))
            return row
        return self._http("POST", name, json=row)[0]

    def update(self, name, identifier, values):
        t = self._table(name)
        if set(values) & {"id", "owner_id", "created_at"}:
            raise ValueError("Immutable ownership")
        values = {**values, "updated_at": now()}
        if not set(values).issubset(t.c.keys()):
            raise ValueError("Unknown column")
        if self.engine:
            with self._mutex, self.engine.begin() as c:
                c.execute(t.update().where(t.c.id == identifier, t.c.owner_id == self.owner).values(**values))
            return self.get(name, identifier)
        result = self._http(
            "PATCH", name, params={"id": "eq." + identifier, "owner_id": "eq." + self.owner}, json=values
        )
        return result[0] if result else None

    def upsert(self, name, values, unique=("id",)):
        with self._mutex:
            existing = self.list(name, limit=1, **{k: values[k] for k in unique})
            if existing:
                return self.update(
                    name,
                    existing[0]["id"],
                    {k: v for k, v in values.items() if k not in {"id", "created_at", "owner_id"}},
                )
            return self.add(name, values)

    def alert(self, code, message, severity="warning", run_id=None):
        from .safety import redact

        return self.add(
            "system_alerts",
            {
                "code": code,
                "message": redact(message),
                "severity": severity,
                "run_id": run_id,
                "resolved": False,
            },
        )

    def snapshot(self):
        if not self.engine:
            result = self.rpc("oi_snapshot", {"p_owner": self.owner})
            if any(len(rows) > 50000 for rows in result.values()):
                raise RuntimeError("Snapshot bound reached; apply retention")
            return result
        with self._mutex, self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            try:
                result = {}
                for name, t in TABLES.items():
                    if name == "job_locks":
                        continue
                    rows = [
                        dict(r)
                        for r in connection.execute(
                            select(t)
                            .where(t.c.owner_id == self.owner)
                            .order_by(t.c.created_at, t.c.id)
                            .limit(50001)
                        ).mappings()
                    ]
                    if len(rows) > 50000:
                        raise RuntimeError("Snapshot bound reached; apply retention")
                    result[name] = rows
                return result
            finally:
                connection.rollback()

    @contextmanager
    def lease(self, name="global-worker", seconds=900):
        holder = str(uuid4())
        stamp = now()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        lock_id = self.stable_id("lease", name)
        if self.engine:
            from sqlalchemy.dialects.sqlite import insert

            t = TABLES["job_locks"]
            with self._mutex, self.engine.begin() as c:
                stmt = insert(t).values(
                    id=lock_id,
                    owner_id=self.owner,
                    created_at=stamp,
                    updated_at=stamp,
                    name=name,
                    holder=holder,
                    expires_at=expires,
                )
                result = c.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["owner_id", "name"],
                        set_={"holder": holder, "expires_at": expires, "updated_at": stamp},
                        where=t.c.expires_at <= stamp,
                    )
                )
                acquired = result.rowcount == 1
        else:
            acquired = self.rpc(
                "oi_acquire_lease",
                {"p_owner": self.owner, "p_name": name, "p_holder": holder, "p_seconds": seconds},
            )
        if not acquired:
            raise RuntimeError("Another worker owns the lease; this run is skipped.")
        try:
            yield holder
        finally:
            if self.engine:
                t = TABLES["job_locks"]
                with self._mutex, self.engine.begin() as c:
                    c.execute(
                        t.delete().where(t.c.owner_id == self.owner, t.c.name == name, t.c.holder == holder)
                    )
            else:
                self.rpc("oi_release_lease", {"p_owner": self.owner, "p_name": name, "p_holder": holder})

    def reserve(self, source, estimate, *, run_id=None, credit_type="free"):
        estimate = Decimal(str(estimate))
        month = now()[:7]
        day = now()[:10]
        request_id = str(uuid4())
        if estimate < 0:
            raise ValueError("Negative cost")
        args = {
            "p_owner": self.owner,
            "p_source": source["id"],
            "p_request": request_id,
            "p_estimate": float(estimate),
            "p_run": run_id,
            "p_limit": float(self.settings.monthly_limit),
            "p_stop": float(self.settings.paid_stop),
            "p_daily": source["daily_quota"],
            "p_monthly": source["monthly_quota"],
            "p_credit_type": credit_type,
        }
        if not self.engine:
            if not self.rpc("oi_reserve_request", args):
                raise PermissionError("Budget or source quota exhausted")
            return request_id
        with self._mutex, self.engine.begin() as c:
            from sqlalchemy.dialects.sqlite import insert

            b = TABLES["budget_months"]
            c.execute(
                insert(b)
                .values(
                    id=self.stable_id("budget", month),
                    owner_id=self.owner,
                    created_at=now(),
                    updated_at=now(),
                    month=month,
                    spent=0,
                    reserved=0,
                    limit_usd=float(self.settings.monthly_limit),
                    stop_usd=float(self.settings.paid_stop),
                )
                .on_conflict_do_nothing(index_elements=["owner_id", "month"])
            )
            budget = (
                c.execute(select(b).where(b.c.owner_id == self.owner, b.c.month == month)).mappings().one()
            )
            cap = min(
                self.settings.monthly_limit,
                self.settings.paid_stop,
                Decimal(str(budget["limit_usd"])),
                Decimal(str(budget["stop_usd"])),
            )
            if Decimal(str(budget["spent"])) + Decimal(str(budget["reserved"])) + estimate > cap:
                raise PermissionError("Budget stop reached")
            q = TABLES["source_quotas"]
            for period, quota in [(day, source["daily_quota"]), (month, source["monthly_quota"])]:
                if quota is None or quota <= 0:
                    raise PermissionError("Unknown or exhausted source quota")
                qid = self.stable_id("quota", source["id"], period)
                c.execute(
                    insert(q)
                    .values(
                        id=qid,
                        owner_id=self.owner,
                        created_at=now(),
                        updated_at=now(),
                        source_id=source["id"],
                        period=period,
                        used=0,
                        limit_value=quota,
                    )
                    .on_conflict_do_nothing(index_elements=["owner_id", "source_id", "period"])
                )
                row = c.execute(select(q).where(q.c.id == qid)).mappings().one()
                if row["used"] >= min(quota, row["limit_value"]):
                    raise PermissionError("Source quota exhausted")
                c.execute(q.update().where(q.c.id == qid).values(used=q.c.used + 1, updated_at=now()))
            c.execute(
                b.update()
                .where(b.c.id == budget["id"])
                .values(reserved=b.c.reserved + float(estimate), updated_at=now())
            )
            u = TABLES["provider_usage"]
            c.execute(
                u.insert().values(
                    id=request_id,
                    owner_id=self.owner,
                    created_at=now(),
                    updated_at=now(),
                    source_id=source["id"],
                    run_id=run_id,
                    request_id=request_id,
                    month=month,
                    status="reserved",
                    estimated_cost=float(estimate),
                    actual_cost=None,
                    units=1,
                    tokens=None,
                    credit_type=credit_type,
                )
            )
        return request_id

    def settle(self, request_id, actual, *, tokens=None):
        if actual is None:
            self.update("provider_usage", request_id, {"status": "unknown_charge"})
            self.alert("unknown_charge", "Request cost is unknown; its worst-case reservation remains held.")
            return
        actual = Decimal(str(actual))
        if actual < 0:
            raise ValueError("Negative cost")
        if not self.engine:
            self.rpc(
                "oi_settle_request",
                {
                    "p_owner": self.owner,
                    "p_request": request_id,
                    "p_actual": float(actual),
                    "p_tokens": tokens,
                },
            )
            return
        with self._mutex, self.engine.begin() as c:
            u = TABLES["provider_usage"]
            b = TABLES["budget_months"]
            row = (
                c.execute(select(u).where(u.c.owner_id == self.owner, u.c.id == request_id)).mappings().one()
            )
            if row["status"] == "settled":
                return
            c.execute(
                b.update()
                .where(b.c.owner_id == self.owner, b.c.month == row["month"])
                .values(
                    spent=b.c.spent + float(actual),
                    reserved=b.c.reserved - row["estimated_cost"],
                    updated_at=now(),
                )
            )
            c.execute(
                u.update()
                .where(u.c.id == request_id)
                .values(actual_cost=float(actual), tokens=tokens, status="settled", updated_at=now())
            )
        if actual > Decimal(str(row["estimated_cost"])):
            self.alert("estimate_exceeded", "Actual vendor cost exceeded reservation.", "error")
