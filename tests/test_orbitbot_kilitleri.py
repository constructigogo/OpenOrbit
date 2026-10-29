"""Panel ile OrbitBot'un ortak kayıt kilitleri (server/panel/kilitler.py): bot kilidi okunur, panel kilitleri yazılır ve kaldırılır."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'panel'))
import kilitler


def _yaz(klasor, ad, veri):
    os.makedirs(klasor, exist_ok=True)
    with open(os.path.join(klasor, ad), 'w', encoding='utf-8') as f:
        json.dump(veri, f)


def _olu_pid():
    """Ölü olduğu bilinen bir pid: biten bir alt süreç."""
    import subprocess
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    p.wait()
    return p.pid


class BotKilidiTesti(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kayitlar = self.tmp.name

    def test_bot_lock_with_live_pid_is_busy(self):
        d = os.path.join(self.kayitlar, 'a')
        _yaz(d, kilitler.BOT_KILIDI, {'pid': os.getpid(), 'since': 1})
        self.assertTrue(kilitler.bot_kullaniyor(d))

    def test_bot_lock_with_dead_pid_is_ignored(self):
        d = os.path.join(self.kayitlar, 'a')
        _yaz(d, kilitler.BOT_KILIDI, {'pid': _olu_pid(), 'since': 1})
        self.assertFalse(kilitler.bot_kullaniyor(d))
        self.assertFalse(kilitler.bot_kullaniyor(os.path.join(self.kayitlar, 'yok')))
        with open(os.path.join(d, kilitler.BOT_KILIDI), 'w') as f:
            f.write('bozuk{')
        self.assertFalse(kilitler.bot_kullaniyor(d))

    def test_panel_locks_written_and_removed(self):
        for s in ('a', 'b'):
            os.makedirs(os.path.join(self.kayitlar, s))
        kilitler.panel_kilitleri(self.kayitlar, {'a': {'ne': 'oyna', 'adres': None}})
        ka = os.path.join(self.kayitlar, 'a', kilitler.PANEL_KILIDI)
        kb = os.path.join(self.kayitlar, 'b', kilitler.PANEL_KILIDI)
        with open(ka, encoding='utf-8') as f:
            v = json.load(f)
        self.assertEqual((v['pid'], v['ne']), (os.getpid(), 'oyna'))
        self.assertIsInstance(v['since'], (int, float))
        self.assertFalse(os.path.exists(kb))
        kilitler.panel_kilitleri(self.kayitlar, {'b': {'ne': 'ek', 'adres': None}})   # a artık kullanılmıyor
        self.assertFalse(os.path.exists(ka))
        self.assertTrue(os.path.exists(kb))
        kilitler.panel_kilitleri(self.kayitlar, {})
        self.assertFalse(os.path.exists(kb))

    def test_other_pid_lock_is_left_alone(self):
        d = os.path.join(self.kayitlar, 'a')
        _yaz(d, kilitler.PANEL_KILIDI, {'pid': os.getpid() + 1, 'since': 1, 'ne': 'oyna', 'adres': None})
        kilitler.panel_kilitleri(self.kayitlar, {})
        self.assertTrue(os.path.exists(os.path.join(d, kilitler.PANEL_KILIDI)))

    def test_panel_lock_contains_join_address(self):
        os.makedirs(os.path.join(self.kayitlar, 'a'))
        kilitler.panel_kilitleri(self.kayitlar, {'a': {'ne': 'katil', 'adres': '10.0.0.5:8080'}})
        with open(os.path.join(self.kayitlar, 'a', kilitler.PANEL_KILIDI), encoding='utf-8') as f:
            v = json.load(f)
        self.assertEqual((v['ne'], v['adres']), ('katil', '10.0.0.5:8080'))


if __name__ == '__main__':
    unittest.main()
