##
## Protocol decoder for the Fuhr multitronic electronic lock bus.
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##

import sigrokdecode as srd

# Message code -> (sender, short name, description).
# Codes 0x00-0x0F are lock status codes, 0x10-0x1F are commands/handshake.
MESSAGES = {
    0x02: ('lock', 'Door opened', 'Door opened'),
    0x03: ('lock', 'Door closed', 'Door closed, not locked'),
    0x05: ('lock', 'Locking started', 'Locking started, motor running'),
    0x06: ('lock', 'Bolts withdrawn', 'Bolts withdrawn / unlocked'),
    0x07: ('lock', 'Door locked', 'Locked and secured'),
    0x08: ('lock', 'Latch withdrawn', 'Latch withdrawn'),
    0x0D: ('lock', 'Fault / alarm', 'Fault, blocked or alarm'),
    0x0E: ('lock', 'Locking finished', 'Locking finished, bolts thrown'),
    0x10: ('ctrl', 'Cmd: open (day latch)', 'Command: open door / latch, day latch function active'),
    0x11: ('ctrl', 'Cmd: day latch on (TGF)', 'Command: day latch function on, latch withdrawn once (jumper TGF fitted)'),
    0x12: ('ctrl', 'Cmd: permanent open', 'Command: unlock door (permanent open function, ports 9 + 10)'),
    0x13: ('ctrl', 'Cmd: day latch off', 'Command: day latch function off'),
    0x14: ('ctrl', 'Cmd: withdraw latch', 'Command: withdraw latch / release input'),
    0x15: ('lock', 'Manually unlocked', 'Lock opened manually (key or handle)'),
    0x16: ('lock', 'Action complete', 'Action complete, lock unlocked'),
    0x17: ('ctrl', 'Cmd: day latch on', 'Command: day latch function on'),
    0x18: ('lock', 'Door opened while locked', 'Door opened while locked (tamper/alarm)'),
    0x19: ('lock', 'Command acknowledged', 'Command acknowledged'),
}


def crc8(byte, poly=0x1D, crc=0x00):
    crc ^= byte
    for _ in range(8):
        crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SamplerateError(Exception):
    pass


class Decoder(srd.Decoder):
    api_version = 3
    id = 'fuhr_multitronic'
    name = 'Fuhr multitronic'
    longname = 'Fuhr multitronic motor lock bus'
    desc = 'Serial bus between a Fuhr multitronic lock and its controller.'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = []
    tags = ['Embedded/industrial']

    channels = (
        {'id': 'bus', 'name': 'Bus', 'desc': 'Bus line carrying all traffic'},
    )
    optional_channels = (
        {'id': 'ctrl', 'name': 'Ctrl TX', 'desc':
            'Asserted while the controller transmits (idle while the lock transmits)'},
    )
    options = (
        {'id': 'baudrate', 'desc': 'Bit rate (baud)', 'default': 2000},
        {'id': 'polarity', 'desc': 'Bus polarity', 'default': 'idle-low',
         'values': ('idle-low', 'idle-high')},
        {'id': 'manchester', 'desc': 'Manchester mapping', 'default': '10=1',
         'values': ('10=1', '01=1')},
        {'id': 'show_bits', 'desc': 'Annotate individual line bits',
         'default': 'no', 'values': ('no', 'yes')},
    )
    annotations = (
        ('startbit', 'Start bit'),          # 0
        ('stopbit', 'Stop bit'),            # 1
        ('linebit', 'Line bit'),            # 2
        ('linedata', 'Line data'),          # 3
        ('code', 'Message code'),           # 4
        ('crc-ok', 'CRC ok'),               # 5
        ('crc-bad', 'CRC error'),           # 6
        ('message', 'Message'),             # 7
        ('ack', 'Acknowledge'),             # 8
        ('direction', 'Direction'),         # 9
        ('warning', 'Warning'),             # 10
    )
    annotation_rows = (
        ('bits', 'Bits', (0, 1, 2)),
        ('line', 'Line data', (3,)),
        ('fields', 'Fields', (4, 5, 6)),
        ('messages', 'Messages', (7, 8)),
        ('directions', 'Direction', (9,)),
        ('warnings', 'Warnings', (10,)),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplerate = None

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    # -- helpers ----------------------------------------------------------
    def putx(self, ss, es, data):
        self.put(int(ss), int(es), self.out_ann, data)

    def goto(self, abs_sample):
        '''Advance to an absolute sample number.'''
        skip = int(abs_sample) - self.samplenum
        if skip > 0:
            return self.wait({'skip': skip})
        return None

    def logical(self, pins):
        '''Return the logical level of the bus (start bit is always a 0).'''
        lvl = pins[0]
        return 1 - lvl if self.options['polarity'] == 'idle-low' else lvl

    # -- main -------------------------------------------------------------
    def decode(self):
        if not self.samplerate:
            raise SamplerateError('Cannot decode without samplerate.')
        bw = float(self.samplerate) / float(self.options['baudrate'])
        if bw < 4:
            raise SamplerateError('Samplerate too low for this bit rate.')
        one = '10' if self.options['manchester'] == '10=1' else '01'
        zero = '01' if self.options['manchester'] == '10=1' else '10'
        edge = 'r' if self.options['polarity'] == 'idle-low' else 'f'
        has_ctrl = self.has_channel(1)

        while True:
            pins = self.wait({0: edge})
            start = self.samplenum
            src = None
            if has_ctrl:
                src = 'CTRL' if pins[1] else 'LOCK'

            self.putx(start, start + bw, [0, ['Start bit', 'Start', 'S']])

            bits = []
            aborted = False
            for k in range(32):
                pins = self.goto(start + (k + 1.5) * bw)
                if pins is None:
                    aborted = True
                    break
                b = self.logical(pins)
                bits.append(b)
                if self.options['show_bits'] == 'yes':
                    self.putx(start + (k + 1) * bw, start + (k + 2) * bw,
                              [2, [str(b)]])
                # An acknowledge is a start bit plus a single logical 0.
                # A data frame always continues with 01 or 10 pairs, so two
                # consecutive 1s at this position can only be an ACK.
                if k == 3 and bits[2] == 1 and bits[3] == 1:
                    aborted = True
                    break

            if aborted and len(bits) == 4:
                es = start + 3 * bw
                if src:
                    self.putx(start, es, [9, ['%s transmits' % src, src]])
                self.putx(start, es, [8, ['Acknowledge', 'ACK', 'A']])
                self.goto(start + 3 * bw)
                continue
            if aborted:
                self.putx(start, self.samplenum,
                          [10, ['Truncated frame', 'Truncated', '!']])
                continue

            data_ss, data_es = start + bw, start + 33 * bw
            frame_es = start + 34 * bw

            if src:
                self.putx(start, frame_es, [9, ['%s transmits' % src, src]])

            s = ''.join(str(b) for b in bits)
            self.putx(data_ss, data_es,
                      [3, ['Line data: %08X' % int(s, 2), '%08X' % int(s, 2)]])

            # Manchester decode.
            payload, ok = 0, True
            for i in range(0, 32, 2):
                pair = s[i:i + 2]
                if pair == one:
                    payload = (payload << 1) | 1
                elif pair == zero:
                    payload = payload << 1
                else:
                    ok = False
                    payload = payload << 1
                    self.putx(data_ss + i * bw, data_ss + (i + 2) * bw,
                              [10, ['Manchester violation', 'MC err', '!']])
            code, crc = payload >> 8, payload & 0xFF

            self.putx(data_ss, data_ss + 16 * bw,
                      [4, ['Code: 0x%02X' % code, '0x%02X' % code]])
            good = (crc8(code) == crc)
            self.putx(data_ss + 16 * bw, data_es,
                      [5 if good else 6,
                       ['CRC 0x%02X %s' % (crc, 'ok' if good else
                                           'BAD, expected 0x%02X' % crc8(code)),
                        'CRC 0x%02X' % crc, 'CRC']])

            if not ok:
                self.putx(data_ss, data_es,
                          [10, ['Invalid Manchester coding', 'MC err', '!']])
            elif code in MESSAGES:
                sender, short, long = MESSAGES[code]
                if src and ((sender == 'ctrl') != (src == 'CTRL')):
                    self.putx(data_ss, data_es,
                              [10, ['Unexpected sender for 0x%02X' % code,
                                    'Sender?', '?']])
                self.putx(data_ss, data_es,
                          [7, ['0x%02X: %s (%s)' % (code, short, long),
                               '0x%02X: %s' % (code, short), short]])
            else:
                self.putx(data_ss, data_es,
                          [7, ['0x%02X: unknown code' % code,
                               '0x%02X: ?' % code, '?']])

            self.putx(data_es, frame_es, [1, ['Stop bit', 'Stop', 'P']])
            self.goto(frame_es)
