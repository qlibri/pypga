# from pypga.core import (
#     BoolRegister,
#     FixedPointRegister,
#     If,
#     MigenModule,
#     Module,
#     NumberRegister,
#     Register,
#     Signal,
#     logic,
#     Case
# )
# from pypga.core.register import TriggerRegister
# from pypga.modules.migen.axireader import MigenAxiReader
# from pypga.modules.migen.pulsegen import MigenPulseBurstGen

# from migen import Cat, Constant, Replicate
# from typing import Optional



# def RAMREADER(
#     axi_hp_index: Optional[int] = None,
#     _ram_start_address: int = 0xa000000,
#     _ram_size: int = 0x2000000
# ):
#     class _RAMREADER(Module):
#         exposed_data: FixedPointRegister(
#             width=16,
#             depth=1024,
#             default=None,
#             readonly=False,
#             signed=True,
#             decimals=0,
#             ram_offset=None if axi_hp_index is None else axi_hp_index * 0x800000, #This automatically reserves no space if this offset is set
#         )


#         @logic
#         def _read_ram(self, platform, soc):
#             if axi_hp_index not in range(4):
#                 raise ValueError(f"Only 4 AXI_HP ports are available, the desired index {axi_hp_index} is out of range.")

#             hp = getattr(soc.ps7, f"s_axi_hp{axi_hp_index}")

#             address = Signal(32)
#             read_enable = Signal()
#             counter = Signal(8)

#             ram_base_address = Constant(_ram_start_address + axi_hp_index * 0x800000, 32)
#             ram_mask = Constant(_ram_size - 1, 32)

#             # Generate increasing addresses
#             self.sync += [
#                 counter.eq(counter + 1),
#                 read_enable.eq(1),
#                 address.eq(
#                     ram_base_address |
#                     (ram_mask & Cat(Constant(0, 3), counter, Constant(0, 32)))
#                 )
#             ]

#             self.submodules.axireader = MigenAxiReader(
#                 address=address,
#                 re=read_enable,
#                 reset=0,
#                 axi_hp=hp,
#             )



#         @logic
#         def expose(self):
#             self.comb += [
#                 self.exposed_data.eq(0)
#             ]

#         @property
#         def get_data(self):
#             return self.exposed_data
        
#     return _RAMREADER


import numpy as np

from pypga.core import (
    BoolRegister,
    FixedPointRegister,
    MigenModule,
    Module,
    NumberRegister,
    Register,
    Signal,
    logic,
    If
)
from pypga.core.register import TriggerRegister, BoolRegister
from pypga.modules.migen.pulsegen import MigenPulseBurstGen
from pypga.modules.migen.axireader import MigenAxiReader
from typing import Optional

from migen import Constant, Cat


def RAMREADER(
    axi_hp_index: Optional[int] = None,
    _ram_start_address: int = 0xa000000,
    _ram_size: int = 0x2000000,
):
    class _RAMREADER(Module):
        data: FixedPointRegister(
            width=16,
            depth=1024,
            default=None,
            readonly=False,
            decimals=0,
        )
        valid_data: BoolRegister()
        
        ar_accepted: BoolRegister()
        read_returned: BoolRegister()
        
        ar_fired: BoolRegister()
        read_fired: BoolRegister()
        ar_ready_flag: BoolRegister()
        ar_valid_flag: BoolRegister()
        r_valid_flag: BoolRegister()



        @logic
        def _read_ram(self, platform, soc):
            hp = getattr(soc.ps7, f"s_axi_hp{axi_hp_index}")

            address = Signal(32)
            read_enable = Signal()
            counter = Signal(10)

            ram_base_address = Constant(_ram_start_address + axi_hp_index * 0x800000, 32)
            ram_mask = Constant(_ram_size - 1, 32)

            self.comb += read_enable.eq(1)

            # Generate increasing addresses
            self.sync += [
                counter.eq(counter + 1),
                address.eq(
                    ram_base_address |
                    (ram_mask & Cat(Constant(0, 3), counter, Constant(0, 32)))
                )
            ]            


            self.submodules.axireader = MigenAxiReader(
                address=Constant(0x00100000, 32),
                re=read_enable,
                reset=0,
                axi_hp=hp,
            )

            self.comb += [
                self.valid_data.eq(self.axireader.valid),
                
                If(
                    self.axireader.valid,
                    self.data.eq(self.axireader.data)
                )
            ]

            self.comb += [
                self.ar_fired.eq(self.axireader.ar_sent),
                self.read_fired.eq(self.axireader.read_received),
                self.ar_valid_flag.eq(self.axireader.ar_is_valid),
                self.ar_ready_flag.eq(self.axireader.ar_is_ready),
                self.r_valid_flag.eq(self.axireader.r_is_valid),
            ]

        @property
        def valid(self):
            return self.valid_data

        @property
        def accepted(self):
            return [self.ar_accepted, self.read_returned]
        

        def get_data(self):
            return self.data
        

    return _RAMREADER
