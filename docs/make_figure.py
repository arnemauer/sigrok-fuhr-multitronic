"""Render docs/decoded-frame.svg from a real capture.

The figure shows what the decoder puts on screen, drawn from the actual bus
edges of the TGF-fitted day latch capture (tests/edges/), so every timing and
every level in it is measured rather than drawn by hand.

    python3 docs/make_figure.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAPTURE = os.path.join(ROOT, 'tests', 'edges',
                       'tgf_fitted_day_mode_on_wait_20s_then_off.txt')
OUT = os.path.join(HERE, 'decoded-frame.svg')

BIT_US = 500          # 2000 baud
FRAME_BITS = 34       # start + 32 line bits + stop

# Palette
BG = '#ffffff'
GRID = '#e3e6ea'
TXT = '#1f2328'
MUTED = '#57606a'
BUS = '#0969da'
CTRL = '#8250df'
ROW_BITS = '#eef2f6'
ROW_LINE = '#dbeafe'
ROW_FIELD = '#dcfce7'
ROW_MSG = '#fef3c7'
ROW_DIR = '#f3e8ff'
OK = '#1a7f37'


def load(path):
    out = []
    for line in open(path):
        t, b, c = line.split()
        out.append((int(t), int(b), int(c)))
    return out


def level_at(edges, t, idx):
    lvl = 0
    for e in edges:
        if e[0] > t:
            break
        lvl = e[idx]
    return lvl


def crc8(byte, poly=0x1D, crc=0x00):
    crc ^= byte
    for _ in range(8):
        crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def decode(edges, start_us):
    """Sample the 32 line bits at their centres, exactly as the decoder does."""
    bits = ''
    for k in range(32):
        t = start_us + (2 * k + 3) * BIT_US // 2
        bits += '0' if level_at(edges, t, 1) else '1'   # inverted line
    payload, ok = 0, True
    for i in range(0, 32, 2):
        pair = bits[i:i + 2]
        if pair == '10':
            payload = (payload << 1) | 1
        elif pair == '01':
            payload <<= 1
        else:
            ok = False
            payload <<= 1
    return bits, payload >> 8, payload & 0xFF, ok


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main():
    edges = load(CAPTURE)

    # First rising edge of the command burst just after 9.16 s.
    start = next(e[0] for e in edges if e[0] > 9_160_000 and e[1] == 1)
    bits, code, crc, mc_ok = decode(edges, start)
    line_hex = '%08X' % int(bits, 2)
    crc_ok = crc8(code) == crc

    # ---- geometry -------------------------------------------------------
    W, H = 1180, 480
    L, R = 118, 40                      # margins
    plot_w = W - L - R
    span_us = FRAME_BITS * BIT_US + 1500   # frame plus a little idle either side
    t0 = start - 750

    def x(t_us):
        return L + (t_us - t0) * plot_w / span_us

    def bit_x(k):                        # left edge of bit k (start bit = 0)
        return x(start + k * BIT_US)

    s = []
    s.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
             'font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif">' % (W, H))
    s.append('<rect width="%d" height="%d" fill="%s"/>' % (W, H, BG))
    s.append('<text x="%d" y="30" font-size="16" font-weight="600" fill="%s">'
             'One decoded frame: controller sends 0x11, day latch function on '
             '(jumper TGF fitted)</text>' % (L - 78, TXT))
    s.append('<text x="%d" y="50" font-size="12" fill="%s">Drawn from the real '
             'capture, frame starts at t = %.4f s. Every edge and every level '
             'below is measured.</text>' % (L - 78, MUTED, start / 1e6))

    # bit grid
    for k in range(FRAME_BITS + 1):
        gx = bit_x(k)
        s.append('<line x1="%.1f" y1="70" x2="%.1f" y2="250" stroke="%s" '
                 'stroke-width="1"/>' % (gx, gx, GRID))

    # ---- traces ---------------------------------------------------------
    def trace(idx, y_top, height, colour, label):
        s.append('<text x="%d" y="%d" font-size="12" font-weight="600" '
                 'fill="%s" text-anchor="end">%s</text>'
                 % (L - 12, y_top + height / 2 + 4, TXT, label))
        pts = []
        lvl = level_at(edges, t0, idx)
        pts.append((x(t0), lvl))
        for e in edges:
            if t0 < e[0] <= t0 + span_us and e[idx] != lvl:
                pts.append((x(e[0]), lvl))
                lvl = e[idx]
                pts.append((x(e[0]), lvl))
        pts.append((x(t0 + span_us), lvl))
        d = ' '.join('%s%.1f,%.1f' % ('M' if i == 0 else 'L', px,
                                      y_top + height - pv * height)
                     for i, (px, pv) in enumerate(pts))
        s.append('<path d="%s" fill="none" stroke="%s" stroke-width="2"/>' % (d, colour))

    trace(1, 80, 46, BUS, 'Bus')
    trace(2, 146, 46, CTRL, 'Ctrl TX')

    # sample points at bit centres
    for k in range(32):
        cx = bit_x(k + 1) + (bit_x(k + 2) - bit_x(k + 1)) / 2
        s.append('<circle cx="%.1f" cy="%.1f" r="1.8" fill="%s" opacity="0.55"/>'
                 % (cx, 80 + 46 - level_at(edges, start + (2 * k + 3) * BIT_US // 2, 1) * 46, TXT))
    s.append('<text x="%d" y="238" font-size="11" fill="%s" text-anchor="end">'
             'sampled at</text>' % (L - 12, MUTED))
    s.append('<text x="%d" y="252" font-size="11" fill="%s" text-anchor="end">'
             'bit centres</text>' % (L - 12, MUTED))
    s.append('<text x="%.1f" y="212" font-size="11" fill="%s">Ctrl TX carries the '
             'controller\u2019s own drive, so it follows the data. Only its state '
             'at the start bit is used, to tell who is talking.</text>'
             % (L + 4, MUTED))

    # ---- annotation rows -------------------------------------------------
    rows = [
        ('Bits', ROW_BITS, 268),
        ('Line data', ROW_LINE, 300),
        ('Fields', ROW_FIELD, 332),
        ('Messages', ROW_MSG, 364),
        ('Direction', ROW_DIR, 396),
    ]
    for label, colour, y in rows:
        s.append('<text x="%d" y="%d" font-size="12" fill="%s" '
                 'text-anchor="end">%s</text>' % (L - 12, y + 18, MUTED, label))

    def box(x1, x2, y, colour, text, bold=False, small=False, fg=TXT):
        s.append('<rect x="%.1f" y="%d" width="%.1f" height="26" rx="4" '
                 'fill="%s" stroke="#cbd5e1" stroke-width="0.8"/>'
                 % (x1, y, max(x2 - x1, 2), colour))
        s.append('<text x="%.1f" y="%d" font-size="%d" %s fill="%s" '
                 'text-anchor="middle">%s</text>'
                 % ((x1 + x2) / 2, y + 18, 11 if small else 12,
                    'font-weight="600"' if bold else '', fg, esc(text)))

    # Bits row: start and stop
    box(bit_x(0), bit_x(1), 268, ROW_BITS, 'Start', small=True)
    box(bit_x(33), bit_x(34), 268, ROW_BITS, 'Stop', small=True)
    # Line data
    box(bit_x(1), bit_x(33), 300, ROW_LINE, 'Line data: %s' % line_hex, bold=True)
    # Fields
    box(bit_x(1), bit_x(17), 332, ROW_FIELD, 'Code: 0x%02X' % code, bold=True)
    box(bit_x(17), bit_x(33), 332, ROW_FIELD,
        'CRC 0x%02X %s' % (crc, 'ok' if crc_ok else 'BAD'), bold=True,
        fg=OK if crc_ok else '#b91c1c')
    # Messages
    box(bit_x(1), bit_x(33), 364, ROW_MSG,
        '0x%02X: Cmd: day latch on (TGF)' % code, bold=True)
    # Direction
    box(bit_x(0), bit_x(34), 396, ROW_DIR,
        'CTRL transmits  (Ctrl TX high at the start bit)')

    # ---- footnote --------------------------------------------------------
    s.append('<text x="%d" y="%d" font-size="11" fill="%s">'
             '34 bit times at 2000 baud = 17.0 ms  ·  32 line bits Manchester '
             'coded = 16 payload bits  ·  CRC-8 poly 0x1D, init 0x00  ·  '
             'Manchester %s</text>'
             % (L - 78, H - 16, MUTED, 'valid' if mc_ok else 'INVALID'))
    s.append('</svg>')

    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(s) + '\n')
    print('wrote %s  (code 0x%02X, crc 0x%02X %s, line %s)'
          % (OUT, code, crc, 'ok' if crc_ok else 'BAD', line_hex))


if __name__ == '__main__':
    main()
