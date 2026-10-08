"""Secret-free, temporary SECURITY INVOKER adapter for bound issuance inputs.

The managed query API accepts parameters for one statement only. This adapter
reuses the reviewed limited-installer body; it grants no additional authority.
Issue while admission is closed. Exact-pair revocation remains available after
activation or retirement. Never interpolate usable credentials.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = 'dashboard_native_operator'
RELEASE = '6b9fceb02278ef9ca978743c43dd2d0dd2cacb49b310689c016fe58d65861fb1'


def sources():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    result = {}
    for name in ('boundary.sql', 'issue.sql', 'revoke.sql'):
        source = (HERE / name).read_text()
        if hashlib.sha256(source.encode()).hexdigest() != manifest['sources_sha256'][name]:
            raise ValueError('Reviewed native issuer source changed')
        result[name] = source
    return result


def function(name):
    reviewed = sources()
    template = reviewed[name + '.sql']
    declaration = """ owner_id_input uuid := (input->>'owner')::uuid;
 run_id_input uuid := (input->>'run')::uuid;
 names text[] := ARRAY[input->'names'->>0,input->'names'->>1];
 issuance_ids uuid[] := ARRAY[(input->'issuances'->>0)::uuid,(input->'issuances'->>1)::uuid];
 result jsonb;
"""
    validation = """
 IF jsonb_typeof(input) IS DISTINCT FROM 'object' OR octet_length(input::text)>8192 OR owner_id_input IS NULL OR run_id_input IS NULL OR
    jsonb_array_length(input->'names')<>2 OR jsonb_array_length(input->'issuances')<>2 OR
    names[1] IS NULL OR names[2] IS NULL OR names[1]=names[2] OR
    names[1]!~'^vn_native_[a-f0-9]{32}$' OR names[2]!~'^vn_native_[a-f0-9]{32}$' OR
    issuance_ids[1] IS NULL OR issuance_ids[2] IS NULL OR issuance_ids[1]=issuance_ids[2] THEN
  RAISE EXCEPTION 'invalid_native_scope' USING ERRCODE='22023';
 END IF;
"""
    if name == 'issue':
        declaration += """ verifiers text[] := ARRAY[input->'verifiers'->>0,input->'verifiers'->>1];
 write_seconds numeric := (input->>'write_seconds')::numeric;
 recovery_seconds numeric := (input->>'recovery_seconds')::numeric;
 delay_seconds numeric := (input->>'delay_seconds')::numeric;
"""
        validation += r"""
 IF jsonb_array_length(input->'verifiers')<>2 OR
    verifiers[1] IS NULL OR verifiers[2] IS NULL OR verifiers[1]=verifiers[2] OR
    verifiers[1]!~'^SCRAM-SHA-256\$4096:[A-Za-z0-9+/]{22}==\$[A-Za-z0-9+/]{43}=:[A-Za-z0-9+/]{43}=$' OR
    verifiers[2]!~'^SCRAM-SHA-256\$4096:[A-Za-z0-9+/]{22}==\$[A-Za-z0-9+/]{43}=:[A-Za-z0-9+/]{43}=$' OR
    write_seconds IS NULL OR recovery_seconds IS NULL OR delay_seconds IS NULL OR
    NOT(0<=delay_seconds AND delay_seconds<write_seconds AND write_seconds<=7200 AND
        write_seconds<=recovery_seconds AND recovery_seconds<=86400) THEN
  RAISE EXCEPTION 'invalid_native_lifetime_or_verifier' USING ERRCODE='22023';
 END IF;
"""
    elif name == 'revoke':
        declaration += " principal_oids oid[] := ARRAY[(input->'oids'->>0)::oid,(input->'oids'->>1)::oid];\n"
        validation += """
 IF jsonb_array_length(input->'oids')<>2 OR principal_oids[1] IS NULL OR principal_oids[2] IS NULL OR
    principal_oids[1]=0 OR principal_oids[2]=0 OR principal_oids[1]=principal_oids[2] THEN
  RAISE EXCEPTION 'invalid_native_oids' USING ERRCODE='22023';
 END IF;
"""
    else:
        raise ValueError('Exact native operation required')
    start, end = 'DO $issuer$\n', 'END $issuer$;'
    if template.count(start) != 1 or template.count(end) != 1:
        raise ValueError('Reviewed native template grammar changed')
    body = template.split(start)[1].split(end)[0]
    boundary = reviewed['boundary.sql']
    boundary = boundary.split("IF current_setting('server_version_num')", 1)[1]
    boundary = "IF current_setting('server_version_num')" + boundary
    for anchor, value in (('-- INPUT_DECLARATIONS', declaration), ('-- CHECK_LIMITED_ISSUER', boundary)):
        if body.count(anchor) != 1:
            raise ValueError('Reviewed native template anchor changed')
        body = body.replace(anchor, value)
    guard = """
 PERFORM set_config('search_path','pg_catalog,pg_temp',true);
 PERFORM set_config('lock_timeout','500ms',true);
 PERFORM set_config('statement_timeout','6s',true);
 PERFORM set_config('transaction_timeout','10s',true);
 PERFORM set_config('createrole_self_grant','',true);
 PERFORM set_config('password_encryption','scram-sha-256',true);
 IF session_user<>'postgres' OR current_user<>'postgres' OR
    current_setting('log_statement') NOT IN ('none','ddl') OR
    current_setting('pgaudit.log')<>'none' OR
    current_setting('log_parameter_max_length_on_error')<>'0' OR
    current_setting('log_min_duration_statement')<>'-1' OR
    current_setting('log_min_duration_sample')<>'-1' OR
    current_setting('log_transaction_sample_rate')<>'0' THEN
  RAISE EXCEPTION 'native_operator_or_logging_mismatch' USING ERRCODE='42501';
 END IF;
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 IF NOT EXISTS(SELECT 1 FROM vn_release.state WHERE singleton AND -- ADMISSION_GUARD
   AND release_sha256='-- RELEASE') THEN
  RAISE EXCEPTION 'closed_reviewed_release_required' USING ERRCODE='55000';
 END IF;
 EXECUTE 'RESET ROLE';
""".replace('-- RELEASE', RELEASE)
    guard = guard.replace('-- ADMISSION_GUARD',
        "state='closed'" if name == 'issue' else "state IN ('closed','open','retired')")
    if body.count('\nBEGIN\n') != 1:
        raise ValueError('Reviewed native body grammar changed')
    body = body.replace('\nBEGIN\n', '\nBEGIN\n' + guard + validation, 1)
    body += """
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 SELECT jsonb_agg(jsonb_build_object('issuance',b.issuance_id,'name',b.principal_name,'oid',b.principal_oid,
   'capability',b.capability,'owner',b.owner_id,'run',b.run_id,'issued_at',b.issued_at,
   'expires_at',b.expires_at,'recovery_until',b.recovery_until,'revoked',b.revoked_at,'login',r.rolcanlogin)
   ORDER BY b.capability) INTO result FROM vn_access.bindings b JOIN pg_roles r ON r.oid=b.principal_oid
   WHERE b.issuance_id=ANY(issuance_ids);
 EXECUTE 'RESET ROLE';
 RETURN result;
 EXCEPTION WHEN OTHERS OR query_canceled OR assert_failure THEN
  -- Discard nested SPI/context messages that might contain a verifier. The
  -- outer bound SELECT contains no literal input and error parameters are off.
  RAISE EXCEPTION 'native_operator_failed' USING ERRCODE='P0001';
END;
"""
    return (f'CREATE FUNCTION {SCHEMA}.{name}(input jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $operator$\n'
            + body + '$operator$;\n'
            + f'REVOKE ALL ON FUNCTION {SCHEMA}.{name}(jsonb) FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;\n')


def install():
    return ('BEGIN; SET LOCAL lock_timeout=\'500ms\'; SET LOCAL statement_timeout=\'6s\'; SET LOCAL transaction_timeout=\'10s\';\n'
            + f'CREATE SCHEMA {SCHEMA} AUTHORIZATION postgres;\n'
            + f'REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;\n'
            + function('issue') + function('revoke') + 'COMMIT;\n')


def remove():
    # RESTRICT deliberately refuses unexpected objects; never CASCADE.
    return ('BEGIN; SET LOCAL lock_timeout=\'500ms\'; SET LOCAL statement_timeout=\'6s\';\n'
            + f'DROP FUNCTION {SCHEMA}.issue(jsonb); DROP FUNCTION {SCHEMA}.revoke(jsonb);\n'
            + f'DROP SCHEMA {SCHEMA} RESTRICT; COMMIT;\n')


def quiescent_function():
    """A separate opt-in provisioner for a new run after terminal cleanup.

    Default closed issuance and its artifact digest remain unchanged. This
    function is temporary, unexposed, SECURITY INVOKER and postgres-only. The
    operator must additionally verify the exact worker is credential-free and
    closed; SQL serializes and independently proves database quiescence.
    """
    text = function('issue')
    guard = "state='closed'"
    anchor = "  RAISE EXCEPTION 'closed_reviewed_release_required' USING ERRCODE='55000';\n END IF;\n"
    if text.count(guard) != 1 or text.count(anchor) != 1:
        raise ValueError('Reviewed issuance guard changed')
    checks = """
 LOCK TABLE vn_access.bindings, vn_durability.runs IN SHARE ROW EXCLUSIVE MODE;
 IF EXISTS(SELECT 1 FROM vn_access.bindings b LEFT JOIN pg_roles r ON r.oid=b.principal_oid
     WHERE b.revoked_at IS NULL OR r.oid IS NULL OR r.rolcanlogin) OR
    EXISTS(SELECT 1 FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.member
     WHERE a.roleid IN ('vn_economic'::regrole,'vn_relay'::regrole) AND r.rolcanlogin
       AND r.oid<>'postgres'::regrole) OR
    EXISTS(SELECT 1 FROM vn_durability.runs WHERE status IN ('starting','running','risk_halted','paused')) OR
    EXISTS(SELECT 1 FROM vn_durability.runs WHERE id=run_id_input) OR
    EXISTS(SELECT 1 FROM vn_access.bindings WHERE run_id=run_id_input) THEN
  RAISE EXCEPTION 'quiescent_fresh_run_required' USING ERRCODE='55000';
 END IF;
"""
    return text.replace(f'{SCHEMA}.issue(', f'{SCHEMA}.issue_quiescent(').replace(
        guard, "state='open'").replace(anchor, anchor + checks)


def install_quiescent():
    """Install only the deliberate quiescent provisioner, never the default."""
    return ("BEGIN; SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='6s'; "
            "SET LOCAL transaction_timeout='10s';\n"
            + f'CREATE SCHEMA {SCHEMA} AUTHORIZATION postgres;\n'
            + f'REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;\n'
            + quiescent_function() + 'COMMIT;\n')


def remove_quiescent():
    return ("BEGIN; SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='6s';\n"
            + f'DROP FUNCTION {SCHEMA}.issue_quiescent(jsonb);\n'
            + f'DROP SCHEMA {SCHEMA} RESTRICT; COMMIT;\n')
