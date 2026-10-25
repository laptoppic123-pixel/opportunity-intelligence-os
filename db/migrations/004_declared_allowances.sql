-- Owner-declared finite credits; no renewal or paid access implied. Existing tables and RLS are unchanged.
BEGIN;
CREATE OR REPLACE FUNCTION public.oi_reserve_request(p_owner text,p_source text,p_request text,p_estimate double precision,
 p_run text,p_limit double precision,p_stop double precision,p_daily integer,p_monthly integer,p_credit_type text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE b budget_months%ROWTYPE; s source_registry%ROWTYPE; q source_quotas%ROWTYPE;
 m text := to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM');
 d text := to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD');
 period_name text; quota_limit integer; allowance jsonb; allowance_used numeric; allowance_limit numeric; debit numeric;
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
 -- Serialize declared credit reservations under the same locked source row.
 allowance := s.config::jsonb->'allowance';
 IF allowance IS NOT NULL AND allowance <> 'null'::jsonb THEN
   IF COALESCE(allowance->>'basis','') <> 'owner_declared'
      OR NOT COALESCE(((s.name='exa' AND allowance->>'kind'='promotional_usd' AND p_credit_type='promotional')
           OR (s.name='tavily' AND allowance->>'kind'='free_credits' AND p_credit_type='owner_free_allowance')),false)
      OR NOT COALESCE((clock_timestamp() >= (allowance->>'starts_at')::timestamptz
          AND clock_timestamp() < (allowance->>'expires_at')::timestamptz),false) THEN RETURN false; END IF;
   allowance_limit := (allowance->>'limit')::numeric;
   IF allowance_limit IS NULL OR allowance_limit<=0 OR allowance_limit>COALESCE((allowance->>'declared_starting')::numeric,0)
      OR allowance_limit::text IN ('NaN','Infinity','-Infinity') THEN RETURN false; END IF;
   IF s.name='exa' THEN
     IF s.estimated_cost IS NULL OR s.estimated_cost<=0 OR p_estimate<s.estimated_cost THEN RETURN false; END IF;
     debit := p_estimate;
     SELECT COALESCE(sum(GREATEST(COALESCE(estimated_cost,0),COALESCE(actual_cost,0))),0)
       INTO allowance_used FROM provider_usage WHERE owner_id=p_owner AND source_id=p_source
       AND created_at::timestamptz >= (allowance->>'starts_at')::timestamptz;
   ELSE
     IF p_estimate<>0 THEN RETURN false; END IF;
     debit := 1;
     SELECT COALESCE(sum(COALESCE(units,1)),0) INTO allowance_used FROM provider_usage
       WHERE owner_id=p_owner AND source_id=p_source
       AND created_at::timestamptz >= (allowance->>'starts_at')::timestamptz;
   END IF;
   IF allowance_used+debit>allowance_limit THEN RETURN false; END IF;
 END IF;
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

REVOKE ALL ON FUNCTION public.oi_reserve_request(text,text,text,double precision,text,double precision,double precision,integer,integer,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.oi_reserve_request(text,text,text,double precision,text,double precision,double precision,integer,integer,text) TO service_role;
COMMIT;
