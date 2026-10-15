import queue,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker import Worker

class WorkerShutdownTests(unittest.TestCase):
    def test_shutdown_between_dequeue_and_dispatch_does_not_start_network_work(self):
        closing=threading.Event();commands=Mock();gateway=Mock()
        def dequeue(**kwargs):
            closing.set();return 'maps',None
        commands.get.side_effect=dequeue
        with tempfile.TemporaryDirectory() as folder,patch('worker.fetch_maps') as fetch:
            worker=Worker(queue.Queue(),commands,closing,gateway)
            worker.data_path=Path(folder);worker.run()
            fetch.assert_not_called();gateway.close.assert_called_once()

    def test_request_stop_wakes_an_idle_queue(self):
        commands=queue.Queue();closing=threading.Event()
        worker=Worker(queue.Queue(),commands,closing,Mock());worker.request_stop()
        self.assertTrue(closing.is_set());self.assertEqual(commands.get_nowait(),('shutdown',None))

if __name__=='__main__':unittest.main()
