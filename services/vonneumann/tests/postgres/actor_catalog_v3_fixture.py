"""B1 owned fixture preparation draft, inert until explicit native-test opt-in.

Only the existing network-none, socket-only PostgreSQL harness is accepted.
Source expectations precede every installation query; source constructors are
separate from real installed objects. This helper is not a production installer.
"""
import hashlib
import json
from pathlib import Path
import re
import runpy
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres


ROOT = Path(__file__).resolve().parents[2]
SRC = runpy.run_path(str(ROOT / "db-contract/research/actor_catalog_v3_source.py"))
SQL = ROOT / "db-contract/research/jupiter_actor_catalog_v3.sql"
N, A, OWNER, ACTORS = (SRC[k] for k in ("NAMESPACE", "ANCHOR", "OWNER", "ACTORS"))
SOURCE_SHA256 = "84b3167c6626911fd231f2eeb337e1df4ab645a89c723017ecb169cdabf93cad"
POLICY_SHA256 = "2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06"
REPO_DIGEST = "public.ecr.aws/supabase/postgres@sha256:965e2dfb5a23a0d6541b6106541e777b303656ebabd4e878746b189d550c0a66"
IMAGE_TAG = "public.ecr.aws/supabase/postgres:17.6.1.095"
FAKE_SCOPES = tuple(tuple(str(UUID(int=i + shift)) for i in (1, 2, 3)) for shift in (0, 3))
SETTINGS_SQL = """SET DateStyle='ISO, YMD'; SET IntervalStyle='postgres'; SET TimeZone='UTC';
SET client_encoding='UTF8'; SET row_security='on'; SET search_path='pg_catalog','pg_temp';
SET standard_conforming_strings='on';\n"""
INTERNAL_METADATA_BYTES = 1048576


def literal(value):
    if type(value) is not str or "\x00" in value or len(value.encode()) > 131072:
        raise ValueError("b1_fixture_literal_refused")
    return "'" + value.replace("'", "''") + "'"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _table_projection(relation):
    if not re.fullmatch(r"(?:vn_jupiter_actor_catalog_research_v3|vn_jupiter_b1_fixture_anchor|pg_temp)\.[a-z_0-9]+", relation):
        raise ValueError("b1_constructor_identity_refused")
    oid = f"{literal(relation)}::pg_catalog.regclass"
    return f"""pg_catalog.jsonb_build_object(
      'columns',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('ordinal',a.attnum::text,'name',a.attname::text,'type',tn.nspname::text||'.'||t.typname::text,'typmod',a.atttypmod::text,'collation',co.collname::text,'not_null',a.attnotnull,'dropped',a.attisdropped,'identity',a.attidentity::text,'generated',a.attgenerated::text,'storage',a.attstorage::text,'compression',a.attcompression::text,'options',to_jsonb(a.attoptions),'fdw_options',to_jsonb(a.attfdwoptions),'default',CASE WHEN d.adbin IS NULL THEN NULL ELSE pg_catalog.pg_get_expr(d.adbin,d.adrelid,false) END) ORDER BY a.attnum)
       FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_type t ON t.oid=a.atttypid JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid={oid} AND a.attnum>0),
      'constraints',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',conname::text,'kind',contype::text,'deferrable',condeferrable,'deferred',condeferred,'validated',convalidated,'local',conislocal,'inherited',coninhcount::text,'no_inherit',connoinherit,'definition',pg_catalog.pg_get_constraintdef(oid,false)) ORDER BY conname COLLATE "C") FROM pg_catalog.pg_constraint WHERE conrelid={oid}),
      'indexes',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',c.relname::text,'am',am.amname::text,'keys',i.indkey::text,'opclasses',i.indclass::text,'collations',i.indcollation::text,'options',i.indoption::text,'unique',i.indisunique,'primary',i.indisprimary,'exclusion',i.indisexclusion,'immediate',i.indimmediate,'valid',i.indisvalid,'ready',i.indisready,'live',i.indislive,'nulls_not_distinct',i.indnullsnotdistinct,'expressions',CASE WHEN i.indexprs IS NULL THEN NULL ELSE pg_catalog.pg_get_expr(i.indexprs,i.indrelid,false) END,'predicate',CASE WHEN i.indpred IS NULL THEN NULL ELSE pg_catalog.pg_get_expr(i.indpred,i.indrelid,false) END) ORDER BY c.relname COLLATE "C") FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid JOIN pg_catalog.pg_am am ON am.oid=c.relam WHERE i.indrelid={oid}))"""


def compare_source_constructors(db, source):
    observations = []
    for serial, table in enumerate(source.tables()):
        original = table["namespace"] + "." + table["name"]
        temporary = "pg_temp.b1_constructor_" + str(serial)
        prefix = "CREATE TABLE " + original
        if not table["ddl"].startswith(prefix):
            raise RuntimeError("b1_constructor_source_refused")
        ddl = "CREATE TEMP TABLE " + temporary + table["ddl"][len(prefix):]
        # Both projections are read before removal in this same independent
        # bootstrap connection. No installed expression becomes expected gold.
        command = "BEGIN;\n" + SETTINGS_SQL + ddl + f"""
SELECT pg_catalog.jsonb_build_object('actual',{_table_projection(original)},'expected',{_table_projection(temporary)});
SELECT pg_catalog.jsonb_build_object('relations',(SELECT pg_catalog.jsonb_agg(c.oid::text ORDER BY c.oid) FROM pg_catalog.pg_class c WHERE c.oid={literal(temporary)}::regclass OR c.oid IN(SELECT reltoastrelid FROM pg_catalog.pg_class WHERE oid={literal(temporary)}::regclass) OR c.oid IN(SELECT indexrelid FROM pg_catalog.pg_index WHERE indrelid={literal(temporary)}::regclass OR indrelid IN(SELECT reltoastrelid FROM pg_catalog.pg_class WHERE oid={literal(temporary)}::regclass))),'types',(SELECT pg_catalog.jsonb_agg(t.oid::text ORDER BY t.oid) FROM pg_catalog.pg_type t WHERE t.typrelid={literal(temporary)}::regclass OR t.oid IN(SELECT typarray FROM pg_catalog.pg_type WHERE typrelid={literal(temporary)}::regclass)),'constraints',(SELECT pg_catalog.jsonb_agg(oid::text ORDER BY oid) FROM pg_catalog.pg_constraint WHERE conrelid={literal(temporary)}::regclass));
DROP TABLE {temporary};
SELECT (pg_catalog.to_regclass({literal(temporary)}) IS NULL)::text;
COMMIT;"""
        lines = db.scalar(command, timeout=30).splitlines()
        if len(lines) != 3 or lines[-1] != "true":
            raise RuntimeError("b1_constructor_cleanup_unresolved")
        pair, children = json.loads(lines[0]), json.loads(lines[1])
        if pair["actual"] != pair["expected"]:
            raise RuntimeError("b1_source_table_mismatch")
        # The finished connection destroys its temporary namespace. Verify all
        # originally observed child OIDs are absent, not just the parent name.
        for catalog, key in (("pg_class", "relations"), ("pg_type", "types"),
                             ("pg_constraint", "constraints")):
            ids = children[key]
            if type(ids) is not list or not ids or any(not re.fullmatch(r"[1-9][0-9]*", x) for x in ids):
                raise RuntimeError("b1_constructor_child_inventory_refused")
            if db.scalar(f"SELECT count(*) FROM pg_catalog.{catalog} WHERE oid IN({','.join(ids)});") != "0":
                raise RuntimeError("b1_constructor_child_cleanup_unresolved")
        observations.append({"table": original, "body_sha256": table["body_sha256"],
                             "relation_children": str(len(children["relations"])),
                             "type_children": str(len(children["types"])),
                             "constraint_children": str(len(children["constraints"])),
                             "cleanup_verified": True})
    return observations


def _source_function_rows(db, source, *, sealed):
    """Independent direct catalogs, before any installed verifier is trusted."""
    expected = source.functions()
    rows = json.loads(db.scalar(f"""SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
       'name',p.proname::text,'namespace',n.nspname::text,'owner',o.rolname::text,
       'arguments',(SELECT COALESCE(pg_catalog.jsonb_agg(tn.nspname::text||'.'||t.typname::text ORDER BY a.ord),'[]'::jsonb) FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY a(id,ord) JOIN pg_catalog.pg_type t ON t.oid=a.id JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace),
       'argument_names',to_jsonb(p.proargnames),'return',(SELECT tn.nspname::text||'.'||t.typname::text FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace WHERE t.oid=p.prorettype),
       'language',l.lanname::text,'kind',p.prokind::text,'definer',p.prosecdef,'strict',p.proisstrict,'volatile',p.provolatile::text,'parallel',p.proparallel::text,'leakproof',p.proleakproof,'set',p.proretset,'cost',p.procost::text,'rows',p.prorows::text,'support',p.prosupport::oid::text,'variadic',p.provariadic::text,'defaults',p.pronargdefaults::text,'all_types',to_jsonb(p.proallargtypes),'modes',to_jsonb(p.proargmodes),'transforms',to_jsonb(p.protrftypes),'binary',p.probin,'sql_body',p.prosqlbody::text,
       'settings',(SELECT to_jsonb(array_agg(v ORDER BY v COLLATE "C")) FROM unnest(p.proconfig) v),
       'body_sha256',pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p.prosrc,'UTF8')),'hex'),
       'acl',(SELECT jsonb_agg(jsonb_build_object('role',rr.rolname::text,'grantor',gr.rolname::text,'privilege',a.privilege_type,'grantable',a.is_grantable) ORDER BY rr.rolname COLLATE "C",gr.rolname COLLATE "C",a.privilege_type COLLATE "C",a.is_grantable) FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a LEFT JOIN pg_catalog.pg_roles rr ON rr.oid=a.grantee LEFT JOIN pg_catalog.pg_roles gr ON gr.oid=a.grantor)) ORDER BY p.proname COLLATE "C")
       FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles o ON o.oid=p.proowner JOIN pg_catalog.pg_language l ON l.oid=p.prolang WHERE n.nspname IN({literal(N)},{literal(A)});""", timeout=30))
    if type(rows) is not list or len(rows) != 8:
        raise RuntimeError("b1_source_function_inventory_mismatch")
    by_signature = {x["signature"]: x["spec"] for x in expected}
    mapping = {"argument_names": "argument_names", "return": "return_type_name", "language": "language",
               "kind": "kind", "definer": "security_definer", "strict": "strict", "volatile": "volatility",
               "parallel": "parallel", "leakproof": "leakproof", "set": "returns_set", "cost": "cost_text",
               "rows": "rows_text", "support": "support_oid_text", "variadic": "variadic_oid_text",
               "defaults": "default_argument_count_text", "all_types": "all_argument_types", "modes": "argument_modes",
               "transforms": "transform_types", "binary": "binary", "sql_body": "sql_body",
               "settings": "local_settings", "body_sha256": "body_sha256"}
    for row in rows:
        signature = row["namespace"] + "." + row["name"] + "(" + ",".join(row["arguments"]) + ")"
        spec = by_signature.pop(signature, None)
        owner = OWNER if sealed else "vn_jupiter_b1_installer"
        if spec is None or row["owner"] != owner or row["arguments"] != spec["argument_type_names"]:
            raise RuntimeError("b1_source_function_signature_mismatch")
        if any(row[actual] != spec[expected] for actual, expected in mapping.items()):
            raise RuntimeError("b1_source_function_definition_mismatch")
        roles = spec["execute_role_names"] if sealed else ["vn_jupiter_b1_installer"]
        if [x["role"] for x in row["acl"]] != roles or any(x["privilege"] != "EXECUTE" or x["grantable"] or x["grantor"] != owner for x in row["acl"]):
            raise RuntimeError("b1_source_function_acl_mismatch")
    if by_signature:
        raise RuntimeError("b1_source_function_missing")


def actor_bindings_acl(db):
    """Direct stored ACL projection, independent of the installed K verifier."""
    return json.loads(db.scalar(f"""SELECT pg_catalog.jsonb_build_object(
      'owner',owner.rolname::text,'is_null',c.relacl IS NULL,
      'entries',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'grantor',grantor.rolname::text,'grantee',grantee.rolname::text,
        'privilege',a.privilege_type,'grantable',a.is_grantable)
        ORDER BY a.privilege_type COLLATE "C",a.grantor,a.grantee,a.is_grantable)
        FROM pg_catalog.aclexplode(c.relacl) a
        LEFT JOIN pg_catalog.pg_roles grantor ON grantor.oid=a.grantor
        LEFT JOIN pg_catalog.pg_roles grantee ON grantee.oid=a.grantee))
      FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles owner ON owner.oid=c.relowner
      WHERE c.oid={literal(N + '.actor_bindings')}::pg_catalog.regclass;"""))


def verify_sealed_privileges(db):
    """Independent actual ownership/access matrix, before K is accepted gold."""
    schemas = json.loads(db.scalar(f"SELECT json_agg(json_build_object('name',n.nspname::text,'owner',r.rolname::text) ORDER BY n.nspname) FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner WHERE n.nspname IN({literal(N)},{literal(A)});"))
    if schemas != [{"name": N, "owner": OWNER}, {"name": A, "owner": "postgres"}]:
        raise RuntimeError("b1_sealed_schema_owner_mismatch")
    for namespace, name in SRC["TABLES"]:
        relation = namespace + "." + name
        owner = OWNER if namespace == N else "postgres"
        actual = json.loads(db.scalar(f"SELECT json_build_object('owner',r.rolname::text,'kind',c.relkind::text,'persistent',c.relpersistence::text,'row_type_owner',(SELECT rr.rolname::text FROM pg_catalog.pg_type t JOIN pg_catalog.pg_roles rr ON rr.oid=t.typowner WHERE t.oid=c.reltype),'array_type_owner',(SELECT rr.rolname::text FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray JOIN pg_catalog.pg_roles rr ON rr.oid=a.typowner WHERE t.oid=c.reltype),'wrong_child_owner',(SELECT count(*) FROM pg_catalog.pg_class x WHERE (x.oid IN(SELECT indexrelid FROM pg_catalog.pg_index WHERE indrelid=c.oid OR indrelid=c.reltoastrelid) OR x.oid=c.reltoastrelid) AND x.relowner<>c.relowner)) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON r.oid=c.relowner WHERE c.oid={literal(relation)}::regclass;"))
        if actual != {"owner": owner, "kind": "r", "persistent": "p", "row_type_owner": owner,
                      "array_type_owner": owner, "wrong_child_owner": 0}:
            raise RuntimeError("b1_sealed_constructor_owner_mismatch")
    # K deliberately retains NULL-versus-explicit ACL representation. Materialize
    # and independently verify the intended owner-only representation before gold.
    projected_acl = actor_bindings_acl(db)
    expected_acl = {"owner": OWNER, "is_null": False, "entries": [
        {"grantor": OWNER, "grantee": OWNER, "privilege": privilege, "grantable": False}
        for privilege in sorted(("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE",
                                 "REFERENCES", "TRIGGER", "MAINTAIN"))]}
    if projected_acl != expected_acl or projected_acl["is_null"] is not False:
        raise RuntimeError("b1_actor_bindings_stored_acl_mismatch")
    # Privilege APIs evaluate inherited/PUBLIC privileges and actual array
    # element rights. Stored array ACL NULL is not a standalone default grant.
    for role in (*ACTORS, "vn_jupiter_b1_installer"):
        actor = role in ACTORS
        native = json.loads(db.scalar(f"SELECT json_build_object('usage',has_schema_privilege({literal(role)},{literal(N)},'USAGE'),'create',has_schema_privilege({literal(role)},{literal(N)},'CREATE'),'anchor_usage',has_schema_privilege({literal(role)},{literal(A)},'USAGE'),'anchor_create',has_schema_privilege({literal(role)},{literal(A)},'CREATE'));"))
        if native != {"usage": actor, "create": False, "anchor_usage": False, "anchor_create": False}:
            raise RuntimeError("b1_sealed_schema_grant_mismatch")
        for namespace, name in SRC["TABLES"]:
            table = namespace + "." + name
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"):
                if db.scalar(f"SELECT has_table_privilege({literal(role)},{literal(table)},{literal(privilege)});") != "f":
                    raise RuntimeError("b1_sealed_private_table_grant_mismatch")
            for typ in (table, namespace + "._" + name):
                if db.scalar(f"SELECT has_type_privilege({literal(role)},{literal(typ)},'USAGE');") != "f":
                    raise RuntimeError("b1_sealed_private_type_grant_mismatch")
        for name, args in SRC["FUNCTIONS"].items():
            sig = N + "." + name + "(" + ",".join("pg_catalog." + t for _, t in args) + ")"
            expected = actor and name in ("verify_scoped_actor", "get_scoped_binding")
            if db.scalar(f"SELECT has_function_privilege({literal(role)},{literal(sig)},'EXECUTE');") != ("t" if expected else "f"):
                raise RuntimeError("b1_sealed_function_grant_mismatch")
    rights = json.loads(db.scalar(f"SELECT json_build_object('usage',has_schema_privilege({literal(OWNER)},{literal(A)},'USAGE'),'create',has_schema_privilege({literal(OWNER)},{literal(A)},'CREATE'),'login',rolcanlogin,'super',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'replication',rolreplication,'bypassrls',rolbypassrls) FROM pg_catalog.pg_roles WHERE rolname={literal(OWNER)};"))
    if rights != {"usage": True, "create": False, "login": False, "super": False, "createdb": False,
                  "createrole": False, "replication": False, "bypassrls": False}:
        raise RuntimeError("b1_sealed_owner_privilege_mismatch")
    for table in (A + ".installer_reference", A + ".expected_functions"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"):
            if db.scalar(f"SELECT has_table_privilege({literal(OWNER)},{literal(table)},{literal(privilege)});") != ("t" if privilege == "SELECT" else "f"):
                raise RuntimeError("b1_sealed_anchor_grant_mismatch")
    if db.scalar(f"SELECT count(*) FROM pg_catalog.pg_auth_members WHERE roleid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname={literal(OWNER)}) OR member IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN({literal(OWNER)},'vn_jupiter_b1_installer')); ") != "0":
        raise RuntimeError("b1_sealed_membership_mismatch")


def original_bootstrap_preimage(db, helper):
    if helper not in ("_installation_preimage", "_role_closure", "_catalog_preimage"):
        raise RuntimeError("b1_bootstrap_helper_refused")
    command = SETTINGS_SQL + f"""WITH original AS MATERIALIZED (SELECT {N}.{helper}() AS value),
       frame AS MATERIALIZED (SELECT jsonb_build_object('preimage',value,'canonical_sha256',encode(sha256(convert_to({N}._c14n(value),'UTF8')),'hex'),'preimage_bytes',octet_length({N}._c14n(value))::text) AS value FROM original)
       SELECT CASE WHEN octet_length(value::text)<={INTERNAL_METADATA_BYTES} THEN value ELSE '{{"refused":true}}'::jsonb END FROM frame;"""
    # The server checks the whole serialized envelope before transmission; the
    # client checks its original received bytes too. This does not preempt CPU
    # or prove an RSS cap: constructing/hash checking the metadata allocates.
    wire = db.scalar(command, timeout=30).encode()
    if len(wire) > INTERNAL_METADATA_BYTES:
        raise RuntimeError("b1_internal_metadata_refused")
    frame = json.loads(wire)
    if set(frame) != {"preimage", "canonical_sha256", "preimage_bytes"}:
        raise RuntimeError("b1_internal_metadata_refused")
    original = canonical(frame["preimage"])
    digest = hashlib.sha256(original).hexdigest()
    if frame["canonical_sha256"] != digest or frame["preimage_bytes"] != str(len(original)):
        raise RuntimeError("b1_canonical_preimage_mismatch")
    return digest, {"helper": helper, "received_bytes": str(len(wire)),
                    "canonical_preimage_bytes": str(len(original)), "max_metadata_bytes": str(INTERNAL_METADATA_BYTES)}


def verify_owned_postgres_image(image, identity):
    """Fixture-only identity dispatch; never pull, retag or alter metadata."""
    try:
        if (type(image) is not dict or type(identity) is not dict
                or identity.get("image") != IMAGE_TAG
                or identity.get("postgres_version") != "17.6"
                or image.get("Id") != identity.get("image_id")
                or image.get("Os") != "linux"
                or type(image.get("RepoDigests")) is not list
                or any(type(value) is not str for value in image["RepoDigests"])):
            raise ValueError()
        if image.get("Architecture") == "amd64":
            # Reuse the accepted current-base original/mirror verifier without
            # changing its default architecture, PINS or repository aliases.
            policy = runpy.run_path(str(ROOT.parents[1] / "scripts/check-ci-images.py"))
            pin = next(pin for pin in policy["PINS"] if pin["tag"] == IMAGE_TAG)
            repositories = [pin["repository"]]
            mirror = policy["MIRRORS"].get(pin["repository"])
            if mirror is not None:
                repositories.append(mirror["repository"])
            for repository in repositories:
                try:
                    policy["verify_image"](image, pin, repository)
                except ValueError:
                    continue
                return
        elif image.get("Architecture") == "arm64":
            # Preserve only the actually observed original ARM index-store
            # identity. This is not a claim that Id is the ARM config digest,
            # and does not grant unmeasured ARM mirror/leaf-store support.
            if (REPO_DIGEST in image.get("RepoDigests", [])
                    and image["Id"] == REPO_DIGEST.rsplit("@", 1)[1]):
                return
        raise ValueError()
    except Exception:
        raise RuntimeError("b1_owned_image_pin_mismatch") from None


def prepare_actor_catalog(db):
    """Called only by the opt-in native case after concrete root review."""
    if not isinstance(db, IsolatedPostgres) or db.identity.get("network") != "none":
        raise RuntimeError("b1_owned_postgres_required")
    # A source mismatch refuses before the first role/schema/database write.
    source = SRC["extract_source"](SQL.read_bytes(), expected_package_sha256=SOURCE_SHA256,
                                  expected_policy_sha256=POLICY_SHA256)
    image = json.loads(db._command(["image", "inspect", db.identity["image_id"]]).stdout)[0]
    verify_owned_postgres_image(image, db.identity)
    roles = ["vn_jupiter_b1_installer", OWNER, *ACTORS]
    bootstrap = "".join(f"CREATE ROLE {role} {'NOLOGIN' if role==OWNER else 'LOGIN'} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;\n" for role in roles)
    bootstrap += f"CREATE SCHEMA {A} AUTHORIZATION postgres; CREATE SCHEMA {N} AUTHORIZATION vn_jupiter_b1_installer;\nREVOKE ALL ON SCHEMA {A},{N} FROM PUBLIC;\n" + source.anchor_sql
    db.sql(bootstrap, timeout=30)
    db.sql(source.installer_sql, role="vn_jupiter_b1_installer", timeout=30)
    _source_function_rows(db, source, sealed=False)
    constructors = compare_source_constructors(db, source)
    seal = "BEGIN;\n"
    for table in ("actor_bindings", "accepted_pins"):
        seal += f"ALTER TABLE {N}.{table} OWNER TO {OWNER};\n"
    # A later GRANT/REVOKE must restore the same explicit owner-only ACL, not
    # replace an accepted NULL with its merely permission-equivalent array.
    seal += f"REVOKE ALL ON TABLE {N}.actor_bindings FROM PUBLIC;\n"
    for row in source.functions():
        seal += f"ALTER FUNCTION {row['signature']} OWNER TO {OWNER};\n"
    seal += f"ALTER SCHEMA {N} OWNER TO {OWNER}; REVOKE ALL ON SCHEMA {N},{A} FROM vn_jupiter_b1_installer;\nGRANT USAGE ON SCHEMA {A} TO {OWNER}; GRANT SELECT ON {A}.installer_reference,{A}.expected_functions TO {OWNER};\n"
    for actor in ACTORS:
        seal += f"GRANT USAGE ON SCHEMA {N} TO {actor}; GRANT EXECUTE ON FUNCTION {N}.verify_scoped_actor(text,text,text,text),{N}.get_scoped_binding(text,text,text,text) TO {actor};\n"
    # PostgreSQL17 refuses direct GRANT/REVOKE on automatically generated array
    # types; array access is governed by the base element type's ACL instead.
    seal += "REVOKE ALL ON TYPE " + ",".join(ns + "." + name for ns, name in SRC["TABLES"]) + " FROM PUBLIC;\n"
    seal += "COMMIT;"
    db.sql(seal, timeout=30)
    _source_function_rows(db, source, sealed=True)
    verify_sealed_privileges(db)
    values = []
    for serial, actor in enumerate(ACTORS):
        scope = FAKE_SCOPES[serial // 4]
        profile = actor.rsplit("_", 1)[1]
        values.append("(" + ",".join((literal(str(UUID(int=101 + serial))),
            "(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=" + literal(actor) + ")",
            literal(actor), *(literal(x) for x in scope), literal(profile),
            "ARRAY['verify_actor','read_scoped_binding']::text[]", literal("0" * 64))) + ")")
    db.sql(f"INSERT INTO {N}.actor_bindings VALUES " + ",".join(values) + ";" +
           f"INSERT INTO {N}.accepted_pins VALUES(true,{literal(SOURCE_SHA256)},{literal('0'*64)},{literal('0'*64)},{literal('0'*64)});" +
           f"INSERT INTO {A}.installer_reference SELECT true,{literal(str(UUID(int=201)))},oid,datname,current_setting('server_version_num')::int,{literal(SOURCE_SHA256)},{literal('0'*64)},{literal('0'*64)},{literal('0'*64)} FROM pg_catalog.pg_database WHERE datname=current_database();" +
           f"INSERT INTO {A}.expected_functions VALUES " + ",".join("(" + literal(row["signature"]) + "," + literal(canonical(row["spec"]).decode()) + "::jsonb)" for row in source.functions()) + ";", timeout=30)
    observed, metadata_sizes = {}, []
    for key, helper in (("M", "_installation_preimage"), ("R", "_role_closure"), ("K", "_catalog_preimage")):
        observed[key], measured = original_bootstrap_preimage(db, helper)
        metadata_sizes.append(measured)
    db.sql(f"BEGIN; UPDATE {A}.installer_reference SET installation_manifest_sha256={literal(observed['M'])},catalog_manifest_sha256={literal(observed['K'])},role_closure_sha256={literal(observed['R'])}; UPDATE {N}.accepted_pins SET installation_manifest_sha256={literal(observed['M'])},catalog_manifest_sha256={literal(observed['K'])},role_closure_sha256={literal(observed['R'])}; UPDATE {N}.actor_bindings SET installation_manifest_sha256={literal(observed['M'])}; COMMIT;", timeout=30)
    return {"package_sha256": SOURCE_SHA256, "policy_sha256": POLICY_SHA256,
            "pins": observed, "constructors": constructors, "metadata_sizes": metadata_sizes,
            "native_source_or_runtime_authority": False}
