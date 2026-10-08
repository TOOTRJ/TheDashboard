"""Private-safe fixed SQL labels, without loading a native database driver."""
FAILURE_PHASES=frozenset({'connect','begin','role','execute','decode','commit','cleanup'})
SERVER_CODES={'57014':'query_cancelled','55P03':'lock_unavailable',
    '42501':'permission_denied','28P01':'authentication_failed','28000':'authentication_failed',
    '08006':'connection_failed','40001':'serialization_failure','40P01':'deadlock',
    '22023':'invalid_parameter','P0001':'server_refused','25006':'read_only_transaction',
    '53100':'disk_full','53200':'out_of_memory','53300':'too_many_connections'}
LOCAL_CODES=frozenset({'connection_unverified','invalid_response','commit_unconfirmed',
    'operation_timed_out','operation_failed_or_uncertain','cleanup_pending_or_failed'})
FAILURE_CATEGORIES=frozenset({'server_error','transport_refused','phase_timeout',
    'operation_timeout','operation_cancelled','unexpected_exception'})
FAILURE_CODES=frozenset(SERVER_CODES.values()) | LOCAL_CODES | frozenset({
    'statement_timeout','phase_timeout','operation_timeout','operation_cancelled',
    'unexpected_exception','transport_refused'})


def safe_sql_failure(value):
    """Copy only fixed labels, including when an injected transport is hostile."""
    if type(value) is not dict or value.keys() != {'phase','category','sqlstate','code'}:
        return None
    for key, allowed in (('phase',FAILURE_PHASES),('category',FAILURE_CATEGORIES),
                         ('code',FAILURE_CODES)):
        if type(value[key]) is not str or value[key] not in allowed: return None
    state=value['sqlstate']
    if state is not None and (type(state) is not str or state not in SERVER_CODES):
        return None
    return dict(value)

