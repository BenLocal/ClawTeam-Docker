"""Run inside the image: python3 tests/test_leader_watcher.py."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, '/usr/local/lib/clawteam-docker')
from leader_runtime import DashboardWatcher
from clawteam.team.tasks import TaskStore


class PendingTaskTest(unittest.TestCase):
    def test_new_pending_tasks_wake_leader_without_repeating(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {'CLAWTEAM_DATA_DIR': directory}
        ):
            watcher = DashboardWatcher('watcher-test', 'leader', heartbeat_interval=3600)
            with patch.object(watcher, '_inject', return_value=(True, 'injected')):
                watcher.check_once()
                self.assertFalse(watcher.check_once().injected)
                store = TaskStore('watcher-test')
                store.create(subject='First dashboard task')
                self.assertTrue(watcher.check_once().injected)
                self.assertFalse(watcher.check_once().injected)
                store.create(subject='Second dashboard task')
                self.assertTrue(watcher.check_once().injected)


if __name__ == '__main__':
    unittest.main()
