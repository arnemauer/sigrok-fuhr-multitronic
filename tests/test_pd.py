"""Run the fuhr_multitronic decoder against real captured traffic.

libsigrokdecode is not needed: this stubs the parts of its API the decoder
uses (Decoder, wait(), put()) and feeds it the bus edges recorded in edges/,
then compares the decoded message codes with expected.txt.

    python3 tests/test_pd.py

The edge files hold microsecond timestamps of every transition of the two
probes, exported from the original .sr captures. They are replayed at a
notional 1 MHz, so one microsecond is one sample.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SAMPLERATE = 1_000_000          # 1 sample per microsecond


# ------------------------------------------------------- libsigrokdecode stub
class _EOF(Exception):
    pass


srd = types.ModuleType('sigrokdecode')
srd.OUTPUT_ANN = 0
srd.SRD_CONF_SAMPLERATE = 1


class _Decoder(object):
    def register(self, *a, **kw):
        return 0

    def put(self, ss, es, out, data):
        self._anns.append((ss, es, data[0], data[1]))

    def has_channel(self, idx):
        return idx in self._channels

    def wait(self, conds=None):
        if conds and 'skip' in conds:
            n = self.samplenum + conds['skip']
            if n >= self._total:
                raise _EOF()
            self.samplenum = n
            return self._pins(n)
        ch, kind = list(conds.items())[0]
        i = self._index_after(self.samplenum)
        while i < len(self._edges):
            t, levels = self._edges[i]
            prev = self._edges[i - 1][1][ch] if i else 0
            if (kind == 'r' and levels[ch] == 1 and prev == 0) or \
               (kind == 'f' and levels[ch] == 0 and prev == 1):
                self.samplenum = t
                return self._pins(t)
            i += 1
        raise _EOF()

    def _index_after(self, t):
        lo, hi = 0, len(self._edges)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._edges[mid][0] <= t:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _pins(self, t):
        i = self._index_after(t) - 1
        levels = self._edges[max(i, 0)][1]
        return (levels[0], levels[1]) + (0,) * 6


srd.Decoder = _Decoder
sys.modules['sigrokdecode'] = srd

from fuhr_multitronic.pd import Decoder  # noqa: E402


# --------------------------------------------------------------------- runner
def load_edges(path):
    """[(t_us, (bus, ctrl))] with consecutive duplicates removed."""
    out = []
    for line in open(path):
        t, b, c = line.split()
        lv = (int(b), int(c))
        if out and out[-1][1] == lv:
            continue
        out.append((int(t), lv))
    return out


def run(path, channels=(0, 1)):
    edges = load_edges(path)
    d = Decoder()
    d._anns, d._edges = [], edges
    d._total = edges[-1][0] + 2_000_000 if edges else 0
    d._channels, d.samplenum = set(channels), 0
    d.options = {'baudrate': 2000, 'polarity': 'idle-low',
                 'manchester': '10=1', 'show_bits': 'no'}
    d.start()
    d.metadata(srd.SRD_CONF_SAMPLERATE, SAMPLERATE)
    try:
        d.decode()
    except _EOF:
        pass
    return d._anns


def main():
    expected = {}
    for line in open(os.path.join(HERE, 'expected.txt')):
        if not line.strip():
            continue
        name, ncodes, nacks, codes = line.split()
        expected[name] = ([int(c, 16) for c in codes.split(',')], int(nacks))

    total_msg = total_ack = 0
    failures = []
    for name, (want, want_acks) in sorted(expected.items()):
        path = os.path.join(HERE, 'edges', name + '.txt')
        if not os.path.exists(path):
            failures.append((name, 'missing edge file'))
            continue
        for wired in (True, False):
            anns = run(path, (0, 1) if wired else (0,))
            got = [int(t[0][2:4], 16) for _, _, idx, t in anns if idx == 7]
            acks = sum(1 for a in anns if a[2] == 8)
            warns = [a for a in anns if a[2] == 10]
            crc_bad = [a for a in anns if a[2] == 6]
            if got != want:
                failures.append((name, 'ctrl=%d codes %d/%d' %
                                 (wired, len(got), len(want))))
            elif acks != want_acks:
                failures.append((name, 'ctrl=%d acks %d/%d' %
                                 (wired, acks, want_acks)))
            elif crc_bad or warns:
                failures.append((name, 'ctrl=%d %d crc, %d warnings' %
                                 (wired, len(crc_bad), len(warns))))
            if wired:
                total_msg += len(got)
                total_ack += acks

    print('captures replayed : %d (x2 wiring modes)' % len(expected))
    print('messages decoded  : %d' % total_msg)
    print('acknowledges      : %d' % total_ack)
    print('failures          : %d' % len(failures))
    for name, why in failures:
        print('  FAIL %-55s %s' % (name, why))
    print('PASS' if not failures else 'FAILED')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
