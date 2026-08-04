##
## Protocol decoder for the Fuhr multitronic motor lock bus.
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##

'''
Fuhr multitronic electronic multi-point lock: the serial bus between the lock
and its controller.

A single line at 2000 baud. Each frame is one start bit, 32 line bits and one
stop bit. The 32 line bits are Manchester coded (10 = 1, 01 = 0), carrying 16
payload bits: an 8 bit message code followed by an 8 bit CRC (CRC-8, poly
0x1D, init 0x00).

Short frames - a start bit plus a single logical 0 - are acknowledgements,
sent by the receiving party after every data frame.

An optional second channel carries the drive signal of the controller. It
follows the data rather than sitting at a steady level, and is sampled at the
start bit only, to label the direction of each frame.
'''

from .pd import Decoder
