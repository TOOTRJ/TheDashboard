"""Offline exact encoded/raw reserve bound, not a Python RSS/runtime proof."""
import hashlib
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from vonneumann.market import provider_acquisition_v3 as a
    from vonneumann.market import provider_recorded_transport_v3 as t


def identity(number):return str(UUID(int=2**128-number))


def padded(value,family):
    raw=a.canonical(value);maximum=a.BODY_LIMITS[family]
    assert len(raw)<=maximum
    return raw+b' '*(maximum-len(raw))


class OriginalPacketReserveTests(unittest.TestCase):
    def test_maximum_original_trio_encoded_raw_and_fixed_diagnostic_fits_pre_io_reserve(self):
        with deny_network():
            binding=a.IssuerBinding(identity(1),identity(2),identity(3),identity(4),identity(5),
                (('jupiter-price-v3',identity(6)),('solana-rpc',identity(7))))
            plan=t.PreparedPacket(binding,identity(8),identity(9),identity(10),identity(11),2**31-1,2**31-2)
            price=padded({a.MINT:{'usdPrice':100,'blockId':2**64-1,'decimals':9,'priceChange24h':None}},'jupiter-price-v3')
            genesis=padded({'jsonrpc':'2.0','id':plan.genesis_rpc_id,'result':a.GENESIS},'solana-rpc')
            block_time=padded({'jsonrpc':'2.0','id':plan.block_time_rpc_id,'result':a.MAX_SECOND},'solana-rpc')
            requests=(a.public_request('jupiter-price-v3'),
                a.public_request('solana-rpc',rpc_method='getGenesisHash',rpc_id=plan.genesis_rpc_id),
                a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=plan.block_time_rpc_id,slot=2**64-1))
            metadata={'content_type':'application/json','x_ratelimit_current':str(a.MAX_CLOCK),
                'x_ratelimit_remaining':str(-(2**63)),'x_ratelimit_reset':str(10_000_000_000)}
            originals=[]
            for record_id,family,request,body in zip((plan.price_record_id,plan.genesis_record_id,plan.block_time_record_id),
                    ('jupiter-price-v3','solana-rpc','solana-rpc'),requests,(price,genesis,block_time)):
                capsule=a.capture_capsule(binding,record_id=record_id,provider_family=family,request=request,
                    raw_body=body,http_status=200,started_wall_us=a.MAX_CLOCK-1,received_wall_us=a.MAX_CLOCK,
                    started_monotonic_us=a.MAX_CLOCK-1,received_monotonic_us=a.MAX_CLOCK,safe_response_metadata=metadata)
                self.assertEqual(a.decode_capsule(capsule.wire,binding).raw_body,body)
                self.assertEqual(len(body),a.BODY_LIMITS[family]);originals.append(capsule)
            # Conservative producer-domain upper fixture includes all three
            # maximum bodies plus the largest fixed-code attempted diagnostic.
            # This need not be a source-fresh/native-accepted observation.
            diagnostic={'record_id':plan.block_time_record_id,'provider_family':'jupiter-price-v3',
                'endpoint_binding_id':identity(7),'request_sha256':'f'*64,
                'request_started_wall_us':str(a.MAX_CLOCK),'request_started_monotonic_us':str(a.MAX_CLOCK),
                'received_wall_us':str(a.MAX_CLOCK),'received_monotonic_us':str(a.MAX_CLOCK),
                'http_status':'599','incomplete':True,'failure_code':max(t._ERROR_CODES,key=len)}
            result=t.PacketResult(plan,tuple(originals),(tuple(diagnostic.items()),),False,
                max(t._ERROR_CODES,key=len),t.CA_BUNDLE_SHA256)
            charge=len(plan.wire)+sum(len(item.wire)+len(item.raw_body) for item in originals)
            charge+=len(a.canonical(result.summary()))
            self.assertLessEqual(charge,t.PACKET_RESERVE_BYTES)
            self.assertEqual(sum(len(item.raw_body) for item in originals),262144)
            self.assertFalse(result.native_admission);self.assertFalse(result.running_authority)
            # Each canonical envelope has constant bounded identifiers/counters;
            # raw base64 expansion dominates and is measured exactly here.
            self.assertEqual(hashlib.sha256(originals[0].raw_body).hexdigest(),originals[0].to_dict()['response_sha256'])
            self.assertGreater(t.PACKET_RESERVE_BYTES-charge,300000)


if __name__=='__main__':unittest.main()
