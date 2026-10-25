-- One SQL statement supplies a consistent owner snapshot for exports and encrypted backups.
BEGIN;
CREATE OR REPLACE FUNCTION public.oi_snapshot(p_owner text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public AS $$
SELECT jsonb_build_object(
'budget_months', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.budget_months WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'problem_clusters', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.problem_clusters WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'queries', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.queries WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'research_runs', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.research_runs WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'source_registry', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.source_registry WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'opportunities', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.opportunities WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'provider_usage', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.provider_usage WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'raw_observations', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.raw_observations WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'source_quotas', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.source_quotas WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'system_alerts', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.system_alerts WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'cluster_observations', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.cluster_observations WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'competitors', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.competitors WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'opportunity_evidence', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.opportunity_evidence WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'owner_feedback', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.owner_feedback WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'research_queue', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.research_queue WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'score_history', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.score_history WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'scores', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.scores WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'spending_signals', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.spending_signals WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'validation_experiments', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.validation_experiments WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb),
'pricing_snapshots', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM (SELECT * FROM public.pricing_snapshots WHERE owner_id=p_owner ORDER BY created_at,id LIMIT 50001) t),'[]'::jsonb)
);
$$;
REVOKE ALL ON FUNCTION public.oi_snapshot(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.oi_snapshot(text) TO service_role;
COMMIT;
