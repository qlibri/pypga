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
        # Output signals
        self.data = Signal(64)
        self.valid = Signal()

        # Debug/visibility
        self.ar_valid = Signal()
        self.r_ready = Signal()
        self.r_valid = Signal()

        # Deep debug signals (expose to Python)
        self.ar_sent = Signal()
        self.read_received = Signal()
        self.ar_is_valid = Signal()
        self.ar_is_ready = Signal()
        self.r_is_valid = Signal()

        # AXI bus signals
        ar = axi_hp.ar
        r = axi_hp.r

        ar_valid_reg = Signal()  # Holds ar.valid until acknowledged

        # Handshake logic
        self.sync += [
            If(~ar_valid_reg & re, ar_valid_reg.eq(1)),  # latch ar.valid
            If(ar.ready & ar_valid_reg, ar_valid_reg.eq(0))  # clear when accepted
        ]

        # AXI AR (address read) channel
        self.comb += [
            ar.id.eq(0),
            ar.addr.eq(address),
            ar.len.eq(0),       # single beat
            ar.size.eq(3),      # 64-bit
            ar.burst.eq(0),     # fixed burst
            ar.cache.eq(0b1111),# bufferable, modifiable
            ar.valid.eq(ar_valid_reg),
            self.ar_valid.eq(ar_valid_reg),

            # Debug
            self.ar_is_valid.eq(ar_valid_reg),
            self.ar_is_ready.eq(ar.ready),
        ]

        # AXI R (read data) channel
        self.comb += [
            r.ready.eq(1),
            self.r_ready.eq(1),
            self.r_valid.eq(r.valid),

            # Debug
            self.r_is_valid.eq(r.valid)
        ]

        # Capture read data
        self.sync += [
            If(r.valid & r.ready,
                self.data.eq(r.data),
                self.valid.eq(1),
                self.read_received.eq(1)
            ).Else(
                self.valid.eq(0)
            )
        ]

        # Track AR transaction
        self.sync += If(ar.valid & ar.ready, self.ar_sent.eq(1))