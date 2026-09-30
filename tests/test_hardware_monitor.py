import time
import unittest
from unittest.mock import Mock,patch
from cfd_studio.hardware_monitor import parse_smi,Monitor
from cfd_studio.windows_gpu import aggregate_engines


def engine(pid,eng,kind='3D',low='123',phys=0):return f'pid_{pid}_luid_0x00000000_0x{low}_phys_{phys}_eng_{eng}_engtype_{kind}'

class HardwareTests(unittest.TestCase):
    def test_per_process_readings_sum_per_engine_then_take_busiest(self):
        result=aggregate_engines([(engine(1,0),30,0),(engine(2,0),40,0),(engine(1,1,'Copy'),50,0),(engine(1,0,low='456'),20,0)])
        self.assertEqual(result[(0,0x123)]['u'],70);self.assertEqual(result[(0,0x456)]['u'],20)

    def test_engine_cap_invalid_and_distinct_physical_nodes(self):
        result=aggregate_engines([(engine(1,0),80,0),(engine(2,0),70,1),(engine(1,0,phys=1),30,0),('bad',80,0),(engine(3,2),float('nan'),0),(engine(3,3),99,1234)])
        self.assertEqual(result[(0,0x123)]['u'],100)
        self.assertEqual(aggregate_engines([(engine(1,0),40,2)]),{})

    def test_missing_gpu_fields_do_not_remove_other_devices_or_become_zero(self):
        rows=parse_smi('0, "GPU, name", GPU-a, N/A, 128, 8192\n1, GPU b, GPU-b, 22, N/A, 8192\n',42)
        self.assertEqual(len(rows),2);self.assertIsNone(rows[0]['u']);self.assertIsNone(rows[1]['mu']);self.assertEqual(rows[1]['u'],22);self.assertEqual(rows[0]['sampled_at'],42)

    def test_sample_matches_uuid_not_card_position_and_keeps_memory_separate(self):
        m=Monitor();m.cpu=Mock();m.cpu.sample.return_value={'cpu':20};m.nvidia=Mock()
        m.nvidia.sample.return_value=[{'id':'A','i':0,'u':99,'mu':123,'mt':1024,'source':'NVML','sampled_at':time.time()},{'id':'B','i':1,'u':88,'mu':456,'mt':2048,'source':'NVML','sampled_at':time.time()}]
        m.refresh_luids=time.monotonic()+100;m.luids={'A':(0,2),'B':(0,1)};m.engines=Mock();m.engines.sample.return_value={(0,1):{'u':40,'engine':'3D'},(0,2):{'u':10,'engine':'Copy'}}
        rows=m.sample()['gpus'];self.assertEqual([g['u'] for g in rows],[10,40]);self.assertEqual([g['driver_u'] for g in rows],[99,88]);self.assertEqual(rows[0]['mu'],123)
        m.engines.sample.return_value={};self.assertIsNone(m.sample()['gpus'][0]['u'])

    def test_failed_sample_preserves_identity_without_fresh_utilization(self):
        m=Monitor();m.cpu=Mock();m.cpu.sample.return_value={'cpu':20};m.nvidia=Mock();m.nvidia.sample.side_effect=OSError('device unavailable')
        m.last_gpus=[{'id':'A','i':0,'u':80,'mu':100,'mt':1024,'sampled_at':10}]
        data=m.sample();self.assertIsNone(data['gpus'][0]['u']);self.assertIsNone(data['gpus'][0]['mu']);self.assertEqual(data['gpus'][0]['sampled_at'],10);self.assertTrue(data['gpus'][0]['stale']);self.assertEqual(data['cpu'],20)

if __name__=='__main__':unittest.main()
