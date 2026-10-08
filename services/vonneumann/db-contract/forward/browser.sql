-- Curated authenticated discovery in the existing owner-scoped read schema.
-- PostgREST schema exposure is a separate exact-project A3 setting.
SET LOCAL ROLE vn_contract_owner;
CREATE INDEX runs_owner_discovery ON vn_durability.runs(user_id,id);
CREATE FUNCTION vn_read.discover(after_id uuid DEFAULT NULL, through_id uuid DEFAULT NULL,
 max_rows integer DEFAULT 100, max_bytes integer DEFAULT 65536) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=vn_identity.owner_id(); cutoff uuid; item record;
 result jsonb; candidate jsonb; records jsonb:='[]'::jsonb; more boolean:=false; cursor uuid;
BEGIN
 IF owner_id IS NULL OR max_rows IS NULL OR max_rows NOT BETWEEN 1 AND 100 OR
    max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN
  RAISE EXCEPTION 'invalid_discovery_page' USING ERRCODE='22023'; END IF;
 -- Discovery is a refreshable directory, not a cross-page ledger snapshot.
 -- Detail pages separately pin authoritative revision; UUID bounds bound work.
 SELECT id INTO cutoff FROM vn_durability.runs WHERE user_id=owner_id ORDER BY id DESC LIMIT 1;
 cutoff:=coalesce(through_id,cutoff);
 IF after_id IS NOT NULL AND (cutoff IS NULL OR after_id>cutoff) THEN
  RAISE EXCEPTION 'invalid_discovery_cursor' USING ERRCODE='22023'; END IF;
 result:=jsonb_build_object('version',1,'owner_id',owner_id,'through_id',cutoff,
  'records',records,'has_more',false,'next_id',NULL);
 FOR item IN SELECT r.id,r.revision,p.data,a.receipt FROM vn_durability.runs r
  JOIN LATERAL (SELECT data FROM vn_projection.runs WHERE user_id=owner_id AND run_id=r.id
   ORDER BY revision DESC LIMIT 1) p ON true
  LEFT JOIN vn_projection.archives a ON a.user_id=owner_id AND a.run_id=r.id
  WHERE r.user_id=owner_id AND r.id<=cutoff AND (after_id IS NULL OR r.id>after_id)
  ORDER BY r.id LIMIT max_rows+1 LOOP
  IF jsonb_array_length(records)=max_rows THEN more:=true; EXIT; END IF;
  candidate:=jsonb_set(result,'{records}',records||jsonb_build_array(jsonb_build_object(
   'run_id',item.id,'revision',item.revision,'data',item.data,'archive_receipt',item.receipt)));
  candidate:=jsonb_set(candidate,'{next_id}',to_jsonb(item.id));
  IF octet_length(candidate::text)>max_bytes THEN
   IF records='[]'::jsonb THEN RAISE EXCEPTION 'discovery_record_exceeds_page'; END IF;
   more:=true; EXIT; END IF;
  records:=candidate->'records'; result:=candidate;
 END LOOP;
 RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;
REVOKE ALL ON FUNCTION vn_read.discover(uuid,uuid,integer,integer)
 FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay,vn_legacy_attestor;
GRANT EXECUTE ON FUNCTION vn_read.discover(uuid,uuid,integer,integer) TO authenticated;
RESET ROLE;
