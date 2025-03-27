from typing import Any, Union

from migen import If, Signal, Constant
from pypga.core import MigenModule


class MigenAxiReader(MigenModule):
    def __init__(
        self,
        address: Union[Signal, Constant, int],
        re: Signal,  # read enable
        reset: Union[Signal, Constant, bool],
        axi_hp: Any,  # AXI_HP instance
    ):
        """
        A Module that reads data from RAM via the AXI interface.

        Args:
            address: RAM address to read from. Must be a 32-bit register.
            re: Read enable signal, data is read when high.
        Output signals:
            data: Read data (64-bit).
            valid: Indicates when data is valid.
        """
        # high-level signals
        self.idle = Signal()
        self.error = Signal()

        # outputs
        self.data = Signal(64)
        self.valid = Signal()

        # low-level debug
        self.ar_valid = Signal()
        self.r_ready = Signal()
        self.r_valid = Signal()


        self.ar_fired = Signal()
        self.read_fired = Signal()

        ar = axi_hp.ar
        r = axi_hp.r

        ar_valid = Signal()
        r_ready = Signal()

        ###
        # Read address channel logic
        self.sync += [
            If(re, ar_valid.eq(1))
            .Elif(ar.ready, ar_valid.eq(0))
            .Else(ar_valid.eq(0))
        ]

        self.comb += [
            ar.id.eq(0),
            ar.addr.eq(address),
            ar.len.eq(0),       # single transfer
            ar.size.eq(3),      # 64-bit
            ar.burst.eq(0),     # fixed address burst
            ar.cache.eq(0b1111),
            ar.valid.eq(ar_valid),

            self.ar_valid.eq(ar_valid)
        ]

        ###
        # Read data channel logic
        self.comb += [
            r_ready.eq(1),         # Always ready to receive
            r.ready.eq(r_ready),
            self.r_ready.eq(r_ready),
            self.r_valid.eq(r.valid)
        ]

        self.sync += [
            If(r.valid & r_ready,
                self.data.eq(r.data),
                self.valid.eq(1),
                If(r.last,
                    self.idle.eq(1)
                )
            ).Else(
                self.valid.eq(0)
            )
        ]

        self.sync += [
            If(ar.valid & ar.ready, self.ar_fired.eq(1)),
            If(r.valid & r_ready, self.read_fired.eq(1)),
        ]


