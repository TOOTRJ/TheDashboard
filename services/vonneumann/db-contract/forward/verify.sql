BEGIN READ ONLY;
SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='8s';
SET LOCAL ROLE vn_contract_owner;
DO $$ DECLARE item record; api record; legacy_expected jsonb; BEGIN
 FOR item IN SELECT * FROM (VALUES
('vn_access.immutable_binding()','4c177aea6ee3f5555205ded67fcf3ca71e44dd53d4113ab918da9889aab1f401','vn_contract_owner',NULL,false),
('vn_access.require_actor(uuid,uuid,text,text)','07a4ff07b9e5e8f618d353efd3a8d8266a2b896dfd6aba976ccfba0f548e5644','vn_contract_owner',NULL,false),
('vn_durability.acknowledge_event(uuid,uuid,uuid,integer)','684f34264ddcea3f266c46a9b42ad04b15047306c5ff02b176b930fb7e727b2d','vn_contract_owner','vn_relay',true),
('vn_durability.canonical_id(jsonb)','f841db557e13b418b24ff443d158db0f98541e5aa92c51d92d518cf8d42f2352','vn_contract_owner',NULL,false),
('vn_durability.commit_command(uuid,uuid,uuid,bigint,bigint,uuid,jsonb)','046409843af86eebda3eb56735efac10fe489cfc7be383aff8ffe545e785302a','vn_contract_owner','vn_economic',true),
('vn_durability.create_run(uuid,uuid,uuid,uuid,jsonb,text,integer)','7538142f800374a961fe64978608987536883cad96f089b1445eb470ada6055d','vn_contract_owner','vn_economic',true),
('vn_durability.decimal_text(numeric,integer)','e7974c191c93db5db5dfea0c0e1d556a75fe4fb97b12d62a999cbaebc7f47670','vn_contract_owner',NULL,false),
('vn_durability.decimal_units(jsonb,integer)','0ce52862453a84b6f684e7519fc12b6b27e85a28908f5528d983ee849fa04699','vn_contract_owner',NULL,false),
('vn_durability.entry_evidence(jsonb)','85d73cb1e26e692b7728ef91537001fa005651d3c142b477591d583c4e168534','vn_contract_owner',NULL,false),
('vn_durability.exact_keys(jsonb,text[])','d9f3b2ca5568583c5605af160a3b5ca396ad192b80ef01265cc385fa16ed1f8f','vn_contract_owner',NULL,false),
('vn_durability.execution_config(jsonb)','80b54a747f7720ade400db09a5a2bafffdec33e67e4907feddda2f2b7974fb6d','vn_contract_owner',NULL,false),
('vn_durability.execution_policy(jsonb)','3eeea7c4a832b72adf347f487a9e3fda40bccdd2d6d883cd46b0b32370ef2f02','vn_contract_owner',NULL,false),
('vn_durability.exit_evidence(jsonb,jsonb)','e0e6c4c055ac82779b4b4eeb6d795211e0d67ca2b3bdd9ae8702e9a2ca46f15c','vn_contract_owner',NULL,false),
('vn_durability.get_command(uuid,uuid,uuid)','605da54c2b1142258048dc0ad170d5a706dd7f9293c0467906dee38415807dd7','vn_contract_owner','vn_economic',true),
('vn_durability.heartbeat(uuid,uuid,uuid,bigint,integer)','dfb1c63291568235e71c0471829ab2ce094e3441d104f11684876c6fa42384e4','vn_contract_owner','vn_economic',true),
('vn_durability.interrupt_expired(uuid,uuid,bigint,uuid)','970f44076e4e136cc87dbe39ec5d1493e1c9f9ef4a2221709be8a3e25ad670a2','vn_contract_owner','vn_economic',true),
('vn_durability.lifecycle_actions(vn_durability.runs,jsonb,boolean,boolean,numeric,numeric)','a515a79debe84a5d53576fa43866b483ec45f97f78e19302f5536d20e4ad39da','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_amount(jsonb,integer)','177ecae6dab17599eede21367256cb991950d69cb1a29495d1f3aea6133e14f0','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_candles(jsonb,jsonb,jsonb,boolean)','51f61658f76d6e2bbab0bcfca2f322b0ca59c6fdc4d696a3157e8dc9c5cd006b','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_cohort(vn_durability.runs,jsonb,integer)','1a6ad24244f8fd78488d148333524d6e6f7315771f252a6440a86c8b9634fc0d','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_cohort_continuation(vn_durability.runs,jsonb,boolean,boolean,boolean,boolean,numeric)','4805a3775a8bf98bee83b951b0db2c2bcd483a5bca394811b80ae74ce310f2a7','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_config(jsonb)','6ae08ef5ef63ea2b9c4a3ea8198986898a1fdc2463e556d17e8d28361655dcf2','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_equity(uuid,numeric,jsonb)','17de133d73ced5e0333feecf11c173ea4044a2ab275d7e47a57dcd18aa5a7d10','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_member_metrics(vn_durability.runs,jsonb,jsonb,jsonb)','a8244e31f5a3baeffe30428b2ce52729895d054d9b3aeb46ad73123b4fa0b4c8','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_optimizer_mirror(jsonb)','972f2c381ba17963cfe8c4645e1f6d16ae9c61d1a9889251b29e913b834a4d2f','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_optimizer_view(jsonb,jsonb,jsonb,jsonb,integer)','be81cebeda3af4504fc0589f2e77e36be5098ee7b3eba0569d3d7eceadb39049','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_optimizer_views(jsonb)','bad4b3f57ceff48a662b09c48b374f7121c120ea1e992e943e57f18e7a7d733c','vn_contract_owner',NULL,false),
('vn_durability.lifecycle_state(vn_durability.runs,jsonb,numeric)','0e31231118ad0cf7e754236200c9d073f2740ca95bcbcd3e10b128e57e04f51d','vn_contract_owner',NULL,false),
('vn_durability.money(jsonb)','3f7ff844afb4adc7af6c4e3f41a58bb89454ef2e61b1420937f365096e5fd70f','vn_contract_owner',NULL,false),
('vn_durability.optimizer_array(jsonb)','93c82847ef5f72408604d0b37ab11497e3a3baa47dab6ba54d0b9de168189877','vn_contract_owner',NULL,false),
('vn_durability.optimizer_array_shape(jsonb)','ac6f536740f9fcd1a698a011d7cb284a4a231e01af4181aefe39f063a083fd93','vn_contract_owner',NULL,false),
('vn_durability.optimizer_bytes(jsonb,integer)','b7df16fdc0dd4bcf969c72c5577f9cb55a13b8aed614c3a565e007b6f8e89dc8','vn_contract_owner',NULL,false),
('vn_durability.optimizer_class_fields(text)','f279f51df2c8eac7247c5f4a496528213a77f971005a7e7a9f2681b2a1cd0b4d','vn_contract_owner',NULL,false),
('vn_durability.optimizer_decimal(jsonb)','94d790efbeed8df37ae7eeb424f7f0a1d6d07b63bab612012d2a3b82d2e5bf83','vn_contract_owner',NULL,false),
('vn_durability.optimizer_evidence(jsonb,text)','6bcd98f371911317b75a6b99a203836e4e8bbf698007bc937969171688204946','vn_contract_owner',NULL,false),
('vn_durability.optimizer_history(jsonb,jsonb)','00abd5daa5d7ee7dc0e8ba8c147f04d8dc73015a91ff2a20f5725996948b3eb3','vn_contract_owner',NULL,false),
('vn_durability.optimizer_integer(jsonb,numeric,numeric)','33139f5b727aaf975ebba661cb296f748743dd3ccd52f512f82ba11f59f426bf','vn_contract_owner',NULL,false),
('vn_durability.optimizer_node(jsonb,jsonb,integer)','e10a9b16f4d82fc01b14a83fa24c569d0c89850560e9fed232536e1fbe7d7157','vn_contract_owner',NULL,false),
('vn_durability.optimizer_role(jsonb,jsonb,text,boolean)','36054a5a5c3fbbf4b9095aa6408db27550a249d5cb2bc74b45fe36b536056773','vn_contract_owner',NULL,false),
('vn_durability.provider_bars(jsonb)','a0fe1c55e55e4b8121114a96f0fe8bc27c0f19e5c61da96a8326348ef8019ae1','vn_contract_owner',NULL,false),
('vn_durability.provider_before(vn_durability.runs,jsonb)','44bc3ad213897b957e4becebfea58e1726206360d0f6dd721d43bdbaf7c668ba','vn_contract_owner',NULL,false),
('vn_durability.provider_config(jsonb)','4ca462749d55a5bef50a8976448c3196a3670120e7178f0afb934100a0f03c9f','vn_contract_owner',NULL,false),
('vn_durability.provider_document(jsonb,text)','24e33789555de3ad6855fd09b7463240268f23be10efa93d6a8bb1f61ddc0e68','vn_contract_owner',NULL,false),
('vn_durability.provider_frame(jsonb)','f872b47417472271e3bb55e3b2565fd9a4bc34d29a32e3fc5f51922c88b3b8bd','vn_contract_owner',NULL,false),
('vn_durability.provider_fresh_frame(jsonb,numeric,numeric,boolean)','932fd091ae3cf28fac9653c195a91413771fd9a5b980289a65bb708951245b53','vn_contract_owner',NULL,false),
('vn_durability.provider_hex_us(jsonb)','2235960be55c6c159d4af4e4e00ce7d731ab396042e785564b9cf4ec0ff55351','vn_contract_owner',NULL,false),
('vn_durability.provider_history(jsonb,jsonb,boolean,numeric,numeric)','ae4f3e4c4b06e7419b4b07c7fb2530bcaba4bcbb8e9240c11b0d3d878a5401a8','vn_contract_owner',NULL,false),
('vn_durability.provider_mint(text)','ad0941ec5063c227d792902263dc51a5ed63146ecbb1736f10b278c2cba77347','vn_contract_owner',NULL,false),
('vn_durability.provider_model_payload(jsonb)','2e8e6ce05a1138b93a54d435afaeb86eb561722da149520f793e8db32980331f','vn_contract_owner',NULL,false),
('vn_durability.provider_model_run(vn_durability.runs)','8a23c995a3c862c688024eeb1381d6d1a72805ebefccb70f5d25d9806df5fd93','vn_contract_owner',NULL,false),
('vn_durability.provider_receipt(jsonb,numeric,numeric,boolean)','e6f23abfc1c30f9b0426962573662bad9f1310a381420c213ceb5f293f345bff','vn_contract_owner',NULL,false),
('vn_durability.provider_server_fresh(jsonb)','d9a9c0d9bade76a5d47709fba4abcf8cca6f136f7b7763f7f030bd754e190ea7','vn_contract_owner',NULL,false),
('vn_durability.provider_state(jsonb,jsonb)','9c689699f394185714256b919577c8c98b78cb1d9793a38bb8af50b1199df9a6','vn_contract_owner',NULL,false),
('vn_durability.provider_us(jsonb)','e19eba145fc166706658fc40f84b3a59dc2c162d685ccc025c333ef491a6ba29','vn_contract_owner',NULL,false),
('vn_durability.read_outbox(uuid,uuid,bigint,integer,integer)','374ddc0e4fc587b008d7f28308528d4cb860fd0e4477af3f75fb144d39b53a13','vn_contract_owner','vn_relay',true),
('vn_durability.record_command(uuid,uuid,uuid,bigint,text,jsonb,jsonb)','4596980944508c01c791167808a38f7b860baed7783bd21340501c35c5c1f823','vn_contract_owner',NULL,false),
('vn_durability.record_distribution(uuid,uuid,jsonb)','bbfbc6765ad815f18cd1c64fe0692af180e0a3f1a975189e4a8563ec7be8b745','vn_contract_owner',NULL,false),
('vn_durability.record_lineage(uuid,uuid,uuid,jsonb)','7e90095c05fc8faeddbb602a83fa0ab1e8efb066a89f1b772bed303fa3eed990','vn_contract_owner',NULL,false),
('vn_durability.record_restart_lineage(uuid,uuid,uuid,jsonb)','50a23b77010dbcb01b10de4d1edb8d84057d6632755c01478a304913b6a73e83','vn_contract_owner',NULL,false),
('vn_durability.rehearsal_hex(jsonb)','f94f88a3ffe6f7d1608333b90d4cce84e33a040314f7d34926549b658ec771b9','vn_contract_owner',NULL,false),
('vn_durability.rehearsal_integer(jsonb,numeric,numeric)','52e9fbbea1e0862199aa733051506954fda518d6d0975ac919ac99b8d04bab86','vn_contract_owner',NULL,false),
('vn_durability.rehearsal_integer_hex(integer)','f67b881a39b82f0a18a4e8cb26ae21b55ed1d26c2a8a30b0488b08c61ba03267','vn_contract_owner',NULL,false),
('vn_durability.rehearsal_json(jsonb,integer)','618390b76556aae45d4f6a4175bcc9cdd39ad9e6c46cc6704f769898b1310599','vn_contract_owner',NULL,false),
('vn_durability.rehearsal_view_time(jsonb)','0ad92b290b7fba263986d49766eefb9df746bf724b2b7690072351bdb97e1d98','vn_contract_owner',NULL,false),
('vn_durability.valid_iteration(jsonb)','02f87309967b95c8df87faa027469e7612d79ceffa1a0b46a9f10f8f81cd01a0','vn_contract_owner',NULL,false),
('vn_durability.validate_lifecycle_after(vn_durability.runs,jsonb,numeric)','ef4742d30c93cf1f04eead80a841ed15d56dce33d7faf561cd84b3f5f4cb3c7d','vn_contract_owner',NULL,false),
('vn_durability.validate_lifecycle_before(vn_durability.runs,jsonb)','b1722f24ba94fe65a01cac5b1e083dfaf47c54458a0b2f2b2b4ec50040a0f294','vn_contract_owner',NULL,false),
('vn_identity.legacy_rows(uuid,uuid)','217d96c2396fe92da9b450ec116d75f43a4c87718137bb2688cec72d910668bd','postgres','vn_contract_owner',true),
('vn_identity.lock_legacy_evidence()','6b60468959dc43fe668468bc19ae4a4b2968343bc948f35374f55f0cd96fe7a4','postgres','vn_contract_owner',true),
('vn_identity.owner_id()','c628b78ce1d2a3b15ddbaf7b0a5838fa26c925d332103e53f34ba73b9b227604','postgres','vn_contract_owner',true),
('vn_legacy.classify_run(uuid)','34bc30745e0ea4ed378b31783765eaca435be545cf70c037baa332e1ebf8680d','postgres','authenticated',true),
('vn_legacy_evidence.archive(uuid,uuid,uuid)','9d7bc8150c397904b4c02a9e7457711330c5778d436a046161cda679c405b3f5','vn_contract_owner','authenticated',true),
('vn_legacy_evidence.attest(uuid,uuid,uuid,jsonb,jsonb)','c2b7973df52d7ea5013777863d9ededef62aeb79c39cfb3915b686827fdb6bb5','vn_contract_owner','vn_legacy_attestor',true),
('vn_legacy_evidence.attestor_guard()','3a6f5543002f5eac3252adce639d0d54c69709c46ef1b45288001251a1935c90','vn_contract_owner',NULL,true),
('vn_legacy_evidence.bump()','40df1a1352170eab5e1d28a5aed66cb164377151bedecd905bd593cd00639839','vn_contract_owner',NULL,true),
('vn_legacy_evidence.capture(uuid,uuid)','a3f89497d5fa02dad3fe1a0a70faa1b98e55f4871f1845a8931c8ffe444745b9','vn_contract_owner','vn_legacy_attestor',true),
('vn_legacy_evidence.catalog()','b2fe5ab7a3cbe40e16a71b5cf77b50d3495df76c51c619b546e421538e2c9c86','vn_contract_owner',NULL,false),
('vn_legacy_evidence.current_catalog()','f74badb07930c68c283fafa56a9fcd76084c241dbf14535cd64404321d00ac8c','vn_contract_owner',NULL,false),
('vn_legacy_evidence.hash_ok(jsonb)','616b439bcd15022823c14b653d98e6e6fb397fe352dfc57652f50360cba0c31c','vn_contract_owner',NULL,false),
('vn_legacy_evidence.history(uuid,bigint,integer)','81e5784ac4d17c1a3020772fccf9f8c59fe6997793d770f0c1e434dff3489cbf','vn_contract_owner','authenticated',true),
('vn_legacy_evidence.invalidate(uuid,uuid,text)','d740493859f1b870eca8fac9c4a19089dfaf8b73d65f21481ea6a4bacb6552a6','vn_contract_owner','vn_legacy_attestor',true),
('vn_legacy_evidence.keys(jsonb,text[])','dddd0ce4d87e28c12f4201807fcc18bb12e0826d5a32fb3f5fdfc23c92f08ca3','vn_contract_owner',NULL,false),
('vn_legacy_evidence.review_status(uuid,jsonb)','d2925132c027e252851355c7b5d459c6935ed5f23dd5351151d6421c48a21446','vn_contract_owner',NULL,false),
('vn_legacy_evidence.snapshot(uuid,uuid)','78c97371e3f5b79f7559fbeaa09bc6f8cad440e81e3b486e53efd97a2cf8c0eb','vn_contract_owner',NULL,true),
('vn_legacy_evidence.status(uuid)','97717e9d6e5fec8b2f9695f17df31e1c43a88b604858233155de0461d64cdb7d','vn_contract_owner','authenticated',true),
('vn_legacy_evidence.tables()','b195f59a725f87a77c4848e459f85fc6ab123ee2146b05fa14717194adc41193','vn_contract_owner',NULL,false),
('vn_legacy_evidence.text_ok(jsonb)','59788c303f895fd79911c88aa264768d3eaefa22782ab4784cd72f519cd55fbe','vn_contract_owner',NULL,false),
('vn_legacy_evidence.validate_document(jsonb,jsonb)','72532935300aeec4a5e6388c81bbc56abea9f80e5586f02ecee86f71fd6a83d2','vn_contract_owner',NULL,false),
('vn_projection.project_command()','b7d2cbd953494aa8ea9ae2da498fa1b30e27de8450e2eecde48cea7eb05421ca','vn_contract_owner',NULL,false),
('vn_projection.require_relay_acceptance()','295044afe8bd95c5573e5a0baad294d9025eb76da538687030da354e0a93692c','vn_contract_owner',NULL,false),
('vn_read.accept_event(uuid,uuid,uuid,integer)','93c554920853f373a84cb49728e8db1edfd1551c0789a37753f140598731c94c','vn_contract_owner','vn_relay',true),
('vn_read.archive_run(uuid,bigint,uuid)','0b5b8cdd104e9bb355c8c6b66d0e957da66cb21042eb6448fbefefa7790cb04c','vn_contract_owner','authenticated',true),
('vn_read.discover(uuid,uuid,integer,integer)','167272295f6c2eadb8bc8f946140653b2b148fd4976fd016b92a5a13a7b456cc','vn_contract_owner','authenticated',true),
('vn_read.events(uuid,bigint,bigint,integer,integer)','7d62d492b9bfc51ff0b28fe95b72c481fe91e5fb0e86e42c551364732ade754f','vn_contract_owner','authenticated',true),
('vn_read.page(uuid,text,bigint,bigint,text,integer,integer)','3383561d18c60c48bfe8637f885c139c7824fd9dcd5987348029dc1d11949bdf','vn_contract_owner','authenticated',true),
('vn_release.catalog()','54a70a393621f95dd61a31be992a5345a7583a9557792693a1bc3c4c40f8eca7','vn_contract_owner',NULL,false),
('vn_release.require_open()','3b14f95769b3a59f6b013415ab2a6dbc60550d3cd66952cd9349dea117ed0c4d','vn_contract_owner',NULL,false),
('vn_release.transition(uuid,bigint,text,text)','7da55bc17c5ac87fdc72aa8de03dfa6c437a1cd33203e2a4afd9c597daddce78','vn_contract_owner',NULL,false)
) expected(signature,body_sha256,owner_role,execute_role,security_definer) LOOP
  IF to_regprocedure(item.signature) IS NULL OR
    (SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid=to_regprocedure(item.signature))
      IS DISTINCT FROM item.body_sha256 OR
    NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=to_regprocedure(item.signature)
      AND p.proowner=item.owner_role::regrole AND p.prosecdef=item.security_definer AND NOT p.proleakproof) OR
    EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.oid=to_regprocedure(item.signature) AND (a.is_grantable OR
       a.grantee NOT IN (p.proowner,coalesce(to_regrole(item.execute_role),p.proowner)))) THEN
   RAISE EXCEPTION 'complete_forward_body_changed';
  END IF;
  FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
   ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay','vn_legacy_attestor') LOOP
   IF has_function_privilege(api.oid,to_regprocedure(item.signature),'EXECUTE') IS DISTINCT FROM
      coalesce(api.rolname=item.execute_role,false) OR
      has_function_privilege(api.oid,to_regprocedure(item.signature),'EXECUTE WITH GRANT OPTION') THEN
    RAISE EXCEPTION 'complete_forward_function_authority_changed';
   END IF;
  END LOOP;
 END LOOP;
 IF (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname IN ('vn_identity','vn_access','vn_durability','vn_projection','vn_read','vn_legacy','vn_legacy_evidence','vn_release'))<>98 THEN
  RAISE EXCEPTION 'unexpected_complete_forward_function';
 END IF;
 IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND c.relkind='r')<>26
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND
      (c.relkind NOT IN ('r','i') OR c.relowner<>'vn_contract_owner'::regrole OR
        (c.relkind='r' AND (c.relforcerowsecurity OR
          (n.nspname='vn_legacy_evidence' AND c.relrowsecurity) OR
          (n.nspname<>'vn_legacy_evidence' AND NOT c.relrowsecurity)))))
    OR EXISTS(SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release'))
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
      LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND c.relkind='r'
      AND (a.grantee<>c.relowner OR a.is_grantable))
    OR EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND a.attacl IS NOT NULL) THEN
  RAISE EXCEPTION 'complete_forward_raw_authority_changed';
 END IF;
 SELECT baseline INTO STRICT legacy_expected FROM vn_legacy_evidence.gate WHERE singleton;
 IF legacy_expected IS DISTINCT FROM vn_legacy_evidence.current_catalog() THEN
  RAISE EXCEPTION 'complete_forward_legacy_catalog_changed';
 END IF;
 IF (SELECT install_catalog FROM vn_release.state WHERE singleton) IS DISTINCT FROM vn_release.catalog() THEN
  RAISE EXCEPTION 'complete_forward_catalog_changed';
 END IF;
 IF (SELECT count(*) FROM pg_class WHERE relnamespace='vn_release'::regnamespace AND relkind='r')<>2
    OR EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace='vn_release'::regnamespace
      AND (c.relowner<>'vn_contract_owner'::regrole OR (c.relkind='r' AND (NOT c.relrowsecurity OR c.relforcerowsecurity))))
    OR EXISTS(SELECT 1 FROM pg_policy WHERE polrelid IN ('vn_release.state'::regclass,'vn_release.operations'::regclass))
    OR EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.relnamespace='vn_release'::regnamespace
      AND (a.grantee<>c.relowner OR a.is_grantable))
    OR EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.pronamespace='vn_release'::regnamespace AND
      (p.proowner<>'vn_contract_owner'::regrole OR a.grantee<>p.proowner OR a.is_grantable OR p.prosecdef
       OR p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, vn_release, pg_temp'])) THEN
  RAISE EXCEPTION 'release_private_authority_postcondition_failed';
 END IF;
 FOR api IN SELECT oid FROM pg_roles WHERE rolname IN
   ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay','vn_legacy_attestor') LOOP
  IF has_schema_privilege(api.oid,'vn_release','USAGE,CREATE') OR
    has_table_privilege(api.oid,'vn_release.state','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
    has_table_privilege(api.oid,'vn_release.operations','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
    has_any_column_privilege(api.oid,'vn_release.state','SELECT,INSERT,UPDATE,REFERENCES') OR
    has_any_column_privilege(api.oid,'vn_release.operations','SELECT,INSERT,UPDATE,REFERENCES') OR
    has_function_privilege(api.oid,'vn_release.require_open()','EXECUTE') OR
    has_function_privilege(api.oid,'vn_release.transition(uuid,bigint,text,text)','EXECUTE') THEN
   RAISE EXCEPTION 'release_api_authority_postcondition_failed';
  END IF;
 END LOOP;
END $$;
RESET ROLE;
COMMIT;
