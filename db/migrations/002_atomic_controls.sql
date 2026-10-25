-- Reviewed atomic lease and budget operations. Apply only during authorized phase 3.
BEGIN;
CREATE OR REPLACE FUNCTION public.oi_utc_now() RETURNS text
LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path = public
AS $$ SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00' $$;

CREATE OR REPLACE FUNCTION public.oi_acquire_lease(p_owner text,p_name text,p_holder text,p_seconds integer)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE affected integer;
BEGIN
 IF p_seconds < 1 OR p_seconds > 900 THEN RETURN false; END IF;
 INSERT INTO job_locks(id,owner_id,created_at,updated_at,name,holder,expires_at)
 VALUES(gen_random_uuid()::text,p_owner,oi_utc_now(),oi_utc_now(),p_name,p_holder,
    to_char((clock_timestamp()+make_interval(secs=>p_seconds)) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US')||'+00:00')
 ON CONFLICT(owner_id,name) DO UPDATE SET holder=excluded.holder,expires_at=excluded.expires_at,updated_at=excluded.updated_at
 WHERE job_locks.expires_at::timestamptz<=clock_timestamp();
 GET DIAGNOSTICS affected = ROW_COUNT;
 RETURN affected=1;
END $$;

CREATE OR REPLACE FUNCTION public.oi_release_lease(p_owner text,p_name text,p_holder text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN
 DELETE FROM job_locks WHERE owner_id=p_owner AND name=p_name AND holder=p_holder;
 RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.oi_reserve_request(p_owner text,p_source text,p_request text,p_estimate double precision,
 p_run text,p_limit double precision,p_stop double precision,p_daily integer,p_monthly integer,p_credit_type text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE b budget_months%ROWTYPE; s source_registry%ROWTYPE; q source_quotas%ROWTYPE;
 m text := to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM');
 d text := to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD');
 period_name text; quota_limit integer;
BEGIN
 IF p_estimate IS NULL OR p_estimate<0 OR p_estimate='Infinity'::float8 OR p_estimate='NaN'::float8
    OR p_limit IS NULL OR p_stop IS NULL OR p_limit<0 OR p_stop<0 THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM provider_usage WHERE owner_id=p_owner AND request_id=p_request) THEN RETURN false; END IF;
 INSERT INTO budget_months(id,owner_id,created_at,updated_at,month,spent,reserved,limit_usd,stop_usd)
 VALUES(gen_random_uuid()::text,p_owner,oi_utc_now(),oi_utc_now(),m,0,0,p_limit,p_stop) ON CONFLICT(owner_id,month) DO NOTHING;
 SELECT * INTO b FROM budget_months WHERE owner_id=p_owner AND month=m FOR UPDATE;
 IF b.spent+b.reserved+p_estimate>LEAST(b.limit_usd,b.stop_usd,p_limit,p_stop) THEN RETURN false; END IF;
 SELECT * INTO s FROM source_registry WHERE owner_id=p_owner AND id=p_source FOR UPDATE;
 IF NOT FOUND OR NOT s.enabled OR NOT s.current_terms_checked OR p_daily IS NULL OR p_monthly IS NULL
    OR s.daily_quota IS NULL OR s.monthly_quota IS NULL THEN RETURN false; END IF;
 -- Check both periods before incrementing either quota.
 FOREACH period_name IN ARRAY ARRAY[d,m] LOOP
   quota_limit:=CASE WHEN period_name=d THEN LEAST(p_daily,s.daily_quota) ELSE LEAST(p_monthly,s.monthly_quota) END;
   IF quota_limit<=0 THEN RETURN false; END IF;
   INSERT INTO source_quotas(id,owner_id,created_at,updated_at,source_id,period,used,limit_value)
   VALUES(gen_random_uuid()::text,p_owner,oi_utc_now(),oi_utc_now(),p_source,period_name,0,quota_limit)
   ON CONFLICT(owner_id,source_id,period) DO NOTHING;
   SELECT * INTO q FROM source_quotas WHERE owner_id=p_owner AND source_id=p_source AND period=period_name FOR UPDATE;
   IF q.used>=LEAST(q.limit_value,quota_limit) THEN RETURN false; END IF;
 END LOOP;
 UPDATE source_quotas SET used=used+1,updated_at=oi_utc_now() WHERE owner_id=p_owner AND source_id=p_source AND period IN(d,m);
 UPDATE budget_months SET reserved=reserved+p_estimate,updated_at=oi_utc_now() WHERE id=b.id;
 INSERT INTO provider_usage(id,owner_id,created_at,updated_at,source_id,run_id,request_id,month,status,estimated_cost,units,credit_type)
 VALUES(p_request,p_owner,oi_utc_now(),oi_utc_now(),p_source,p_run,p_request,m,'reserved',p_estimate,1,p_credit_type);
 RETURN true;
END $$;

CREATE OR REPLACE FUNCTION public.oi_settle_request(p_owner text,p_request text,p_actual double precision,p_tokens integer)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE u provider_usage%ROWTYPE;
BEGIN
 IF p_actual IS NULL OR p_actual<0 OR p_actual='Infinity'::float8 OR p_actual='NaN'::float8 THEN RETURN false; END IF;
 SELECT * INTO u FROM provider_usage WHERE id=p_request AND owner_id=p_owner FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF u.status='settled' THEN RETURN true; END IF;
 UPDATE budget_months SET spent=spent+p_actual,reserved=GREATEST(0,reserved-u.estimated_cost),updated_at=oi_utc_now()
 WHERE owner_id=p_owner AND month=u.month;
 UPDATE provider_usage SET actual_cost=p_actual,tokens=p_tokens,status='settled',updated_at=oi_utc_now() WHERE id=p_request;
 RETURN true;
END $$;

REVOKE ALL ON FUNCTION public.oi_utc_now() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.oi_acquire_lease(text,text,text,integer) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.oi_release_lease(text,text,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.oi_reserve_request(text,text,text,double precision,text,double precision,double precision,integer,integer,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.oi_settle_request(text,text,double precision,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.oi_utc_now() TO service_role;
GRANT EXECUTE ON FUNCTION public.oi_acquire_lease(text,text,text,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.oi_release_lease(text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.oi_reserve_request(text,text,text,double precision,text,double precision,double precision,integer,integer,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.oi_settle_request(text,text,double precision,integer) TO service_role;
COMMIT;
