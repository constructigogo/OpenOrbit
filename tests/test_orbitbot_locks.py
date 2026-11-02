"""Save locks shared by the panel and OrbitBot (server/panel/locks.py): the bot lock is read, panel locks are written and removed."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'panel'))
import locks


def _write(folder, name, data):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _dead_pid():
    """A pid known to be dead: a finished child process."""
    import subprocess
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    p.wait()
    return p.pid


class BotLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saves = self.tmp.name

    def test_bot_lock_with_live_pid_is_busy(self):
        d = os.path.join(self.saves, 'a')
        _write(d, locks.BOT_LOCK, {'pid': os.getpid(), 'since': 1})
        self.assertTrue(locks.bot_using(d))

    def test_bot_lock_with_dead_pid_is_ignored(self):
        d = os.path.join(self.saves, 'a')
        _write(d, locks.BOT_LOCK, {'pid': _dead_pid(), 'since': 1})
        self.assertFalse(locks.bot_using(d))
        self.assertFalse(locks.bot_using(os.path.join(self.saves, 'missing')))
        with open(os.path.join(d, locks.BOT_LOCK), 'w') as f:
            f.write('broken{')
        self.assertFalse(locks.bot_using(d))

    def test_bot_slot_checks_by_id_and_is_total(self):
        _write(os.path.join(self.saves, 'a'), locks.BOT_LOCK, {'pid': os.getpid(), 'since': 1})
        self.assertTrue(locks.bot_slot(self.saves, 'a'))
        self.assertFalse(locks.bot_slot(self.saves, 'b'))
        for bad in ('', None, '../a', 'A', 'a/b', 'x' * 41, 5):
            self.assertFalse(locks.bot_slot(self.saves, bad))

    def test_panel_locks_written_and_removed(self):
        for s in ('a', 'b'):
            os.makedirs(os.path.join(self.saves, s))
        locks.panel_locks(self.saves, {'a': {'what': 'play', 'address': None}})
        la = os.path.join(self.saves, 'a', locks.PANEL_LOCK)
        lb = os.path.join(self.saves, 'b', locks.PANEL_LOCK)
        with open(la, encoding='utf-8') as f:
            v = json.load(f)
        self.assertEqual((v['pid'], v['what']), (os.getpid(), 'play'))
        self.assertIsInstance(v['since'], (int, float))
        self.assertFalse(os.path.exists(lb))
        locks.panel_locks(self.saves, {'b': {'what': 'extra', 'address': None}})   # a is no longer used
        self.assertFalse(os.path.exists(la))
        self.assertTrue(os.path.exists(lb))
        locks.panel_locks(self.saves, {})
        self.assertFalse(os.path.exists(lb))

    def test_other_pid_lock_is_left_alone(self):
        d = os.path.join(self.saves, 'a')
        _write(d, locks.PANEL_LOCK, {'pid': os.getpid() + 1, 'since': 1, 'what': 'play', 'address': None})
        locks.panel_locks(self.saves, {})
        self.assertTrue(os.path.exists(os.path.join(d, locks.PANEL_LOCK)))

    def test_panel_lock_contains_join_address(self):
        os.makedirs(os.path.join(self.saves, 'a'))
        locks.panel_locks(self.saves, {'a': {'what': 'join', 'address': '10.0.0.5:8080'}})
        with open(os.path.join(self.saves, 'a', locks.PANEL_LOCK), encoding='utf-8') as f:
            v = json.load(f)
        self.assertEqual((v['what'], v['address']), ('join', '10.0.0.5:8080'))


if __name__ == '__main__':
    unittest.main()
