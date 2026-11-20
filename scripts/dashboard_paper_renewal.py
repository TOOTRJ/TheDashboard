"""Original-bound, finite paper-login renewal, no automatic retry.

The caller verifies the exact Dashboard project/schema before constructing this
operator. Passwords, role grants, owners, runs and original credential bytes are
never modified. All new evidence lives beside that original in renewal files.
"""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4

FORMAT='dashboard-finite-paper-renewal-v1'
HEADROOM=900
MAX_LIFETIME=604800


class RenewalRefused(RuntimeError): pass


def need(value):
    if not value: raise RenewalRefused('finite_renewal_precondition_failed')


def stamp(value):
    need(type(value) is str)
    result=datetime.fromisoformat(value)
    need(result.utcoffset()==timedelta(0))
    return result


def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def literal(value):
    need(type(value) is str and '\x00' not in value)
    return "'"+value.replace("'","''")+"'"


def identity(initial):
    for key in ('owner_id','run_id'):
        need(type(initial[key]) is str and str(UUID(initial[key]))==initial[key])
    need(re.fullmatch(r'vn_paper_[a-f0-9]{32}',initial['db_login']) is not None
        and type(initial['role_oid']) is int and initial['role_oid']>0)
    stamp(initial['valid_until'])
    return {key:initial[key] for key in ('owner_id','run_id','db_login','role_oid')}


def restrictions_sql(alias='r'):
    return ("NOT("+alias+".rolsuper OR "+alias+".rolcreatedb OR "+alias+".rolcreaterole OR "+alias+".rolinherit OR "+alias+".rolreplication OR "+alias+".rolbypassrls) AND "+alias+".rolconnlimit=2 "
        "AND NOT EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member="+alias+".oid)")


def rpc_sql(alias='r'):
    return ("has_schema_privilege("+alias+".oid,'vn_paper_v6','USAGE') AND "
        "has_function_privilege("+alias+".oid,'vn_paper_v6.rpc(text,jsonb)','EXECUTE')")


def no_table_sql(alias='r'):
    return ("NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='vn_paper_v6' AND c.relkind='r' AND (has_table_privilege("+alias+".oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') "
        "OR has_any_column_privilege("+alias+".oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))")


def envelope_sql(alias='r'):
    return restrictions_sql(alias)+' AND '+rpc_sql(alias)+' AND '+no_table_sql(alias)


def status_sql(initial):
    scope=identity(initial)
    return ("SELECT r.oid AS role_oid,b.owner_id::text AS owner_id,b.run_id::text AS run_id,r.rolname::text AS db_login,"
        "r.rolvaliduntil::text AS role_deadline,b.expires_at::text AS binding_deadline,clock_timestamp()::text AS db_now,"
        "r.rolcanlogin AS can_login,"+restrictions_sql()+" AS restricted,"+rpc_sql()+" AS direct_rpc,"+no_table_sql()+" AS no_table_access "
        "FROM pg_roles r JOIN vn_paper_v6.bindings b ON b.login=r.rolname WHERE r.rolname="+literal(scope['db_login'])+";")


def check_status(initial,row):
    need(type(row) is dict and all(row.get(key)==value for key,value in identity(initial).items())
        and all(row.get(key) is True for key in ('restricted','direct_rpc','no_table_access')))
    return stamp(row['role_deadline']),stamp(row['binding_deadline']),stamp(row['db_now'])


def check_request(initial,observed,previous,new):
    role,binding,now=check_status(initial,observed)
    previous,new=stamp(previous),stamp(new)
    need(observed['can_login'] is True and role==binding==previous
        and previous-now>=timedelta(seconds=HEADROOM)
        and new>previous and new<=now+timedelta(seconds=MAX_LIFETIME))


def payload(record):return {key:value for key,value in record.items() if key not in ('state','receipt','payload_sha256')}


def validate(original,initial,initial_sha):
    need(original.get('format')==FORMAT and original.get('initial_sha256')==initial_sha
        and original.get('payload_sha256')==sha(canon(payload(original)))
        and all(original.get(key)==value for key,value in identity(initial).items()))
    need(str(UUID(original['operation_id']))==original['operation_id'])
    stamp(original['previous_deadline']);stamp(original['new_deadline'])
    need(original['state'] in ('prepared','submitted_or_uncertain','unresolved','committed_verified'))
    before,new,prepared=[stamp(original[key]) for key in ('previous_deadline','new_deadline','prepared_database_clock')]
    need(before-prepared>=timedelta(seconds=HEADROOM) and before<new<=prepared+timedelta(seconds=MAX_LIFETIME))
    if original['state']=='committed_verified':
        receipt=original.get('receipt');need(type(receipt) is dict
            and stamp(receipt['role_deadline'])==stamp(receipt['binding_deadline'])==new)


def renew_sql(record):
    scope={key:record[key] for key in ('owner_id','run_id','db_login','role_oid')}
    identity({**scope,'valid_until':record['previous_deadline']})
    owner,run,login,old,new=[literal(record[key]) for key in ('owner_id','run_id','db_login','previous_deadline','new_deadline')]
    oid=str(record['role_oid'])
    return ("BEGIN; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='1s'; SET LOCAL search_path=pg_catalog,pg_temp; "
        "DO $renew$ DECLARE original vn_paper_v6.bindings%ROWTYPE; affected integer; BEGIN "
        "SELECT * INTO STRICT original FROM vn_paper_v6.bindings WHERE login="+login+"::name AND owner_id="+owner+"::uuid AND run_id="+run+"::uuid AND expires_at="+old+"::timestamptz FOR UPDATE; "
        "IF original.expires_at-clock_timestamp()<interval '900 seconds' OR "+new+"::timestamptz<="+old+"::timestamptz OR "+new+"::timestamptz>clock_timestamp()+interval '7 days' THEN RAISE EXCEPTION 'finite_renewal_deadline_refused'; END IF; "
        "IF NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname="+login+" AND r.oid="+oid+"::oid AND r.rolcanlogin AND r.rolvaliduntil="+old+"::timestamptz AND "+envelope_sql()+") THEN RAISE EXCEPTION 'finite_renewal_original_changed'; END IF; "
        "EXECUTE format('ALTER ROLE %I VALID UNTIL %L',"+login+","+new+"); "
        "IF NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname="+login+" AND r.oid="+oid+"::oid AND r.rolcanlogin AND r.rolvaliduntil="+new+"::timestamptz AND "+envelope_sql()+") THEN RAISE EXCEPTION 'finite_renewal_original_changed'; END IF; "
        "UPDATE vn_paper_v6.bindings SET expires_at="+new+"::timestamptz WHERE login="+login+"::name AND owner_id="+owner+"::uuid AND run_id="+run+"::uuid AND expires_at="+old+"::timestamptz; "
        "GET DIAGNOSTICS affected=ROW_COUNT; IF affected<>1 OR NOT EXISTS(SELECT 1 FROM vn_paper_v6.bindings WHERE login="+login+"::name AND owner_id="+owner+"::uuid AND run_id="+run+"::uuid AND expires_at="+new+"::timestamptz) THEN RAISE EXCEPTION 'finite_renewal_binding_postcondition'; END IF; "
        "IF NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname="+login+" AND r.oid="+oid+"::oid AND r.rolcanlogin AND r.rolvaliduntil="+new+"::timestamptz AND "+envelope_sql()+") THEN RAISE EXCEPTION 'finite_renewal_permission_postcondition'; END IF; END $renew$; COMMIT;")


def private_read(path):
    need(not path.is_symlink() and not path.parent.is_symlink())
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and stat.S_IMODE(info.st_mode)==0o600 and 0<info.st_size<=65536)
        raw=source.read(65537);need(len(raw)==info.st_size)
        return raw


def private_write(path,value,replace=False):
    parent=path.parent;meta=parent.lstat()
    need(not parent.is_symlink() and parent.resolve()==parent and stat.S_ISDIR(meta.st_mode)
        and meta.st_uid==os.getuid() and stat.S_IMODE(meta.st_mode)==0o700 and not path.is_symlink())
    target=parent/('pending-'+uuid4().hex+'.json') if replace else path
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as destination:
        destination.write(canon(value)+b'\n');destination.flush();os.fsync(destination.fileno())
    if replace:os.replace(target,path)
    fd=os.open(parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


@contextmanager
def credential_lock(credential_path):
    path=Path(credential_path);meta=path.parent.lstat()
    need(not path.parent.is_symlink() and path.parent.resolve()==path.parent
        and stat.S_ISDIR(meta.st_mode) and meta.st_uid==os.getuid() and stat.S_IMODE(meta.st_mode)==0o700)
    fd=os.open(path.parent/'.renewal-operation.lock',os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
            and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RenewalRefused('renewal_operation_busy') from None
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

class RenewalStore:
    def __init__(self,credential_path):
        self.path=Path(credential_path)
        self.raw=private_read(self.path);self.initial=json.loads(self.raw);identity(self.initial)
        self.initial_sha=sha(self.raw);self.folder=self.path.parent/'renewals'

    @contextmanager
    def exclusive(self):
        with credential_lock(self.path):yield

    def originals(self):
        need(private_read(self.path)==self.raw)
        if not self.folder.exists():return []
        need(not self.folder.is_symlink() and self.folder.resolve()==self.folder
            and stat.S_IMODE(self.folder.stat().st_mode)==0o700 and self.folder.stat().st_uid==os.getuid())
        records=[]
        for path in self.folder.glob('renewal-*.json'):
            record=json.loads(private_read(path));validate(record,self.initial,self.initial_sha)
            need(path.name=='renewal-'+record['operation_id']+'.json');records.append(record)
        return records

    def chain(self):
        records=self.originals();ordered=[];previous=None;deadline=self.initial['valid_until']
        while records:
            nexts=[record for record in records if record['previous_operation_id']==previous]
            need(len(nexts)==1);record=nexts[0]
            need(stamp(record['previous_deadline'])==stamp(deadline))
            ordered.append(record);records.remove(record)
            if record['state']!='committed_verified':need(not records);break
            previous=record['operation_id'];deadline=record['new_deadline']
        return ordered,deadline

    def effective_record(self):
        with self.exclusive():return self._effective_record()

    def _effective_record(self):
        chain,deadline=self.chain();record=dict(self.initial)
        record['initial_valid_until']=record['valid_until'];record['valid_until']=deadline
        committed=[item for item in chain if item['state']=='committed_verified']
        record['renewal_operation_id']=None if not committed else committed[-1]['operation_id']
        receipt=self.path.parent/'credential-status-after-renewal.json'
        if receipt.exists():
            value=json.loads(private_read(receipt));need(value['initial_sha256']==self.initial_sha
                and value['owner_id']==record['owner_id'] and value['run_id']==record['run_id']
                and value['role_oid']==record['role_oid'])
            if value.get('renewal_operation_id')==record['renewal_operation_id']:
                need(stamp(value['valid_until'])==stamp(deadline));record['state']=value['state']
            else:need(value['state'] not in ('close_submitted_or_uncertain','closed_verified'))
        return record

    def save_credential_status(self,record):
        with self.exclusive():return self._save_credential_status(record)

    def _save_credential_status(self,record):
        # Verification/closure outcomes are separate from the initial credential.
        current=self._effective_record()
        need(all(record.get(key)==current.get(key) for key in ('owner_id','run_id','role_oid','valid_until','renewal_operation_id')))
        need(record['state'] in ('issued_verified','close_submitted_or_uncertain','closed_verified'))
        if current['state']=='closed_verified':need(record['state']=='closed_verified')
        if current['state']=='close_submitted_or_uncertain':need(record['state']!='issued_verified')
        value={key:record[key] for key in ('owner_id','run_id','role_oid','valid_until','state')}
        value['initial_sha256']=self.initial_sha
        value['renewal_operation_id']=record.get('renewal_operation_id')
        target=self.path.parent/'credential-status-after-renewal.json'
        private_write(target,value,replace=target.exists())

    def status(self,client):
        client.verify();rows=client.query(status_sql(self.initial),(),read_only=True)
        need(type(rows) is list and len(rows)==1);check_status(self.initial,rows[0]);return rows[0]

    def prepare(self,client,new_deadline):
        with self.exclusive():return self._prepare(client,new_deadline)

    def _prepare(self,client,new_deadline):
        need(self._effective_record()['state']=='issued_verified')
        chain,previous=self.chain();need(not chain or chain[-1]['state']=='committed_verified')
        observed=self.status(client);new_deadline=stamp(new_deadline).isoformat()
        check_request(self.initial,observed,previous,new_deadline)
        record={'format':FORMAT,**identity(self.initial),'operation_id':str(uuid4()),
            'initial_sha256':self.initial_sha,'previous_deadline':previous,'new_deadline':new_deadline,
            'previous_operation_id':None if not chain else chain[-1]['operation_id'],
            'prepared_database_clock':stamp(observed['db_now']).isoformat(),'state':'prepared'}
        record['payload_sha256']=sha(canon(payload(record)))
        if not self.folder.exists():self.folder.mkdir(mode=0o700)
        private_write(self.folder/('renewal-'+record['operation_id']+'.json'),record)
        return self.report(record,observed)

    def load(self,operation_id):
        need(str(UUID(operation_id))==operation_id)
        record=json.loads(private_read(self.folder/('renewal-'+operation_id+'.json')))
        validate(record,self.initial,self.initial_sha);return record

    def apply(self,client,operation_id):
        with self.exclusive():return self._apply(client,operation_id)

    def _apply(self,client,operation_id):
        need(self._effective_record()['state']=='issued_verified')
        record=self.load(operation_id);need(record['state']=='prepared')
        chain,previous=self.chain();need(chain[-1]['operation_id']==operation_id)
        observed=self.status(client);check_request(self.initial,observed,record['previous_deadline'],record['new_deadline'])
        record['state']='submitted_or_uncertain'
        private_write(self.folder/('renewal-'+operation_id+'.json'),record,replace=True)
        client.verify()
        try:client.query(renew_sql(record),(),read_only=False)
        except Exception:pass
        return self._reconcile(client,operation_id)

    def reconcile(self,client,operation_id):
        with self.exclusive():return self._reconcile(client,operation_id)

    def _reconcile(self,client,operation_id):
        record=self.load(operation_id)
        need(record['state'] in ('submitted_or_uncertain','unresolved','committed_verified'))
        observed=self.status(client);role,binding,now=check_status(self.initial,observed)
        if role==binding==stamp(record['new_deadline']):record['state']='committed_verified'
        elif role==binding==stamp(record['previous_deadline']):record['state']='unresolved'
        else:raise RenewalRefused('renewal_original_readback_mismatch')
        record['receipt']={'role_deadline':role.isoformat(),'binding_deadline':binding.isoformat(),'database_clock':now.isoformat()}
        private_write(self.folder/('renewal-'+operation_id+'.json'),record,replace=True)
        return self.report(record,observed)

    def report(self,record,observed):
        return {'operation_id':record['operation_id'],'state':record['state'],
            'previous_deadline':record['previous_deadline'],'new_deadline':record['new_deadline'],
            'remaining_headroom_seconds':int((stamp(observed['role_deadline'])-stamp(observed['db_now'])).total_seconds()),
            'max_lifetime_seconds':MAX_LIFETIME,'automatic_retry':False,'password_changed':False}
