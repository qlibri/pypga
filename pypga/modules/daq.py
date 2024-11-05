"""
DAQ with
* averaging
* min / max of timebin
"""

from typing import Optional

import numpy as np
from pypga.core import (
    BoolRegister,
    FixedPointRegister,
    If,
    MigenModule,
    Module,
    NumberRegister,
    Register,
    Signal,
    logic,
    Case
)
from pypga.core.register import TriggerRegister
from pypga.modules.migen.axiwriter import MigenAxiWriter
from pypga.modules.migen.pulsegen import MigenPulseBurstGen

from migen import Cat, Constant, Replicate


def DAQ(
    data_depth: int = 1024,
    data_width: int = None,
    data_decimals: int = 0,
    sampling_period_width: int = 32,
    default_sampling_period: int = 10,
    data_signed: bool = False,
    axi_hp_index: Optional[int] = None,
    _ram_start_address: int = 0xa000000,
    _ram_size: int = 0x2000000,
    max_samples_in_bits=20,
):
    """
    A programmable DAQ module.

    Args:
        axi_hp_index: If an integer is passed here, an AXI HP interface
          is used to directly write data to RAM, otherwise data is sent
          to the PS using a register. The value of this number can be one 
          in [0, 1, 2, 3], indicating the index of the AXI HP bus to use.

    Input signals / args:
        on: whether the AWG should go to its next point or pause.
        reset: resets the AWG to its initial state. If None, the
            AWG is automatically reset when it's done.
        sampling_period: the sampling period.

    Output signals:
        value: a signal with the ROM value at the current index.
    """
    class _DAQ(Module):
        sampling_period_cycles: NumberRegister(
            width=sampling_period_width,
            default=default_sampling_period - 2,
            offset_from_python=-2,
            min=2, #Leo: why 2? #TODO: in future this should be 0 by defining it from the python view
        )#Leo: error here between cycles and no cycles?
        
        #used for simulating a division: multiply by the bit shifted inverse and then bitshift
        inverse_factor_sampling_period_cycles: NumberRegister(
            width=sampling_period_width,
            default=int(2**16/default_sampling_period),
            #offset_from_python=-2,
            #min=2,
        )
        length: NumberRegister(
            width=sampling_period_width,
            default=data_depth,
            offset_from_python=-1
        )
        software_trigger: TriggerRegister()
        busy: BoolRegister(readonly=True)
        
        
        reduce_mode: NumberRegister(default=0,width=3,signed=False)
        
        @property
        def sampling_period(self) -> float:
            return self.sampling_period_cycles * self._clock_period
        

        @sampling_period.setter
        def sampling_period(self, sampling_period: float):
            self.sampling_period_cycles = sampling_period / self._clock_period
            self.inverse_factor_sampling_period_cycles = int(2**16 / self.sampling_period_cycles)

        @property
        def period(self) -> float:
            return self.length * self.sampling_period

        @period.setter
        def period(self, period: float):
            self.sampling_period = period / self.length

        @property
        def frequency(self) -> float:
            return 1.0 / self.period

        @frequency.setter
        def frequency(self, frequency: float):
            self.period = 1.0 / frequency

        def get_data(self, start: int = 0, stop: int = -1) -> list:
            return self.data[start:stop]
        
        #count: NumberRegister(width=30, default=1,readonly=True,signed=False)
        #value: FixedPointRegister(width=16, default=0, readonly=True, signed=True, decimals=data_decimals)
        average_value: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=data_decimals)
        #sumvalue: FixedPointRegister(width=16+16, default=0, readonly=True, signed=data_signed, decimals=data_decimals)
        value_max: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=data_decimals)
        value_min: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=data_decimals)
        value_max_2: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=data_decimals)
        value_min_2: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=data_decimals)
        #value_max_3: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=decimals)
        #value_min_3: FixedPointRegister(width=data_width, default=0, readonly=True, signed=data_signed, decimals=decimals)
        offset: FixedPointRegister(width=data_width, default=0, readonly=False, signed=data_signed, decimals=data_decimals) #TODO: remove, just for debugging

        # count samples for averaging
        # max_samples_in_bits=20 by default
        # 2**20 is slightly more than 1M  means that you need min 125 samples/s to not maybe saturate (Because of internal 125MHz sampling)        
        # TODO: warn when having less than
        count: NumberRegister(width=max_samples_in_bits, readonly=True,signed=False)

        edge_threshold: FixedPointRegister(width=data_width, default=0, signed=data_signed, decimals=data_decimals)
        
        @logic
        def _daq(self):
            self.value=Signal((data_width, data_signed),reset=0)
            self.trigger = Signal(reset=0)
            #self.input = Signal(data_width, reset=0)            
            self.input = Signal.like(self.value)  
            self.not_above_threshold = Signal(1)
            
            self._trigger = Signal(reset=0)
            self.comb += [self._trigger.eq(self.trigger | self.software_trigger)]
            self.submodules.pulseburst = MigenPulseBurstGen(
                trigger=self._trigger,
                reset=False,
                pulses=self.length - 1, #  dynamically setting the length
                period=self.sampling_period_cycles,
            )
            self.comb += [
                # sum up the input values and divide
                #self.average_value.eq((self.sumvalue * self.inverse_factor_sampling_period_cycles) >>16), # simulate a division by multiplying with the inverse and bit shift it
                #self.average_value.eq(self.input),
                #adding this kills the timing contraints 
            ]
            #Leo: comb is just wiring, right?
            #Leo: should this  be in comb or sync? -> sync when in doubt (because no timing problem, BUT arithmetic problems trough delayed)
            
            
            self.edge_count = Signal(22)        
            self.sumvalue=Signal((data_width+max_samples_in_bits,data_signed),reset=0)
            self.oldsum = Signal.like(self.sumvalue)            
            
            # self.average_value_1 = Signal.like(self.average_value)
            # self.average_value_2 = Signal.like(self.average_value)
            # self.average_value_3 = Signal.like(self.average_value)
            # TODO: the first or the last value when averaging has a glitch (i do not know which one)
            self.sync += [
                self.oldsum.eq(self.sumvalue),
                self.not_above_threshold.eq(self.input < self.edge_threshold),
                #self.value.eq(self.average_value_1),
                # self.average_value_1.eq(self.average_value_2),  #mulitplication takes 3 cycles
                # self.average_value_2.eq(self.average_value_3),
                self.average_value.eq((self.oldsum * self.inverse_factor_sampling_period_cycles) >>16), # simulate a division by multiplying with the inverse and bit shift it
                self.busy.eq(self.pulseburst.busy),#its mainly a interface to PC so put it into sync , because timing not critical here (so make everything less critical)
                If(self.pulseburst.out == 1,
                   self.sumvalue.eq(self.input),#reset     
                   self.value_max.eq(self.input),
                   self.value_min.eq(self.input),
                   self.count.eq(0),
                   self.edge_count.eq(0),
                ).Elif(self.pulseburst.busy,
                    self.sumvalue.eq(self.sumvalue+self.input),
                    self.count.eq(self.count+1),
                    If(self.value_max < self.input,
                       self.value_max.eq(self.input)
                    ),
                    If(self.value_min > self.input,
                       self.value_min.eq(self.input)
                    ),
                    If(self.not_above_threshold & (self.input > self.edge_threshold), 
                       self.edge_count.eq(self.edge_count+1)),                    
                ),
                Case(self.reduce_mode, {
                     0: self.value.eq(self.average_value),
                     1: self.value.eq(self.value_max),
                     2: self.value.eq(self.value_min),
                     3: self.value.eq(self.input),
                     4: self.value.eq(self.edge_count), #count rising edges
                     5: self.value.eq(self.offset), #TODO: remove, just for debugging
                     6: self.value.eq(self.count), #TODO: remove, just for debugging
                 })  
            ]
        
    
        #Leo: is this also set when we are using DRM? Or is is then automatically not used? add to the if?
        data: FixedPointRegister(
            width=data_width,
            depth=data_depth,
            default=None,
            reversed=True,
            readonly=True,
            signed=data_signed,
            decimals=data_decimals,
            ram_offset=None if axi_hp_index is None else axi_hp_index * 0x800000, #This automatically reserves no space if this offset is set
        ) 
        
        #data.we
        #data.index
        #data.value.eq()
        
        #self.reg
        
        if axi_hp_index is None:
            @logic
            def _daq_data(self):
                self.comb += [
                    self.data_index.eq(self.pulseburst.count),# Leo: where is data_index defined? and where does self.pulseburst come from?
                    self.data_we.eq(self.pulseburst.out),
                    If(
                        self.pulseburst.out == 1,
                        self.data.eq(self.value),
                    ),
                ]
        else:
            @logic
            def _daq_data(self, platform, soc):
                if axi_hp_index not in range(4):
                    raise ValueError(f"Only 4 AXI_HP ports are available, the desired index {axi_hp_index} is out of range.")
                hp = getattr(soc.ps7, f"s_axi_hp{axi_hp_index}")
                address = Signal(32)
                # TODO: Find out what the size of one RAM block is
                ram_base_address = Constant(_ram_start_address + axi_hp_index * 0x800000, 32) #Leo: why constant?
                ram_size = 0x2000000  #bit: 0b1000000000000000000000
                ram_mask = Constant(ram_size-1, 32) # -> 0b0111111111111111111111111
                #why sync here
                #protect to write not outside reserved DMA memroy region
                self.sync += address.eq(
                    ram_base_address | 
                    (ram_mask &
                     Cat(#cat removes upper range
                        Constant(0, 3), #increase adress pointer by 8,16,24,32
                        self.pulseburst.count, #0b000p set adress to self.pulsberst.countx8
                        Constant(0, 32)))
                    ) # Leo: what is this?
                self.submodules.axiwriter = MigenAxiWriter(
                    address=address,
                    data=self.value,
                    we=self.pulseburst.out,
                    reset=self._trigger,
                    axi_hp=hp,
                )
                #Leo: why does this write into data? --> because of the adress



        
    return _DAQ


if __name__ == '__main__':
    from pypga.core.migen_axi.platforms import redpitaya
    from pypga.boards.stemlab125_14.soc import StemlabSoc
    
    DAQ(data_depth=2**12,
        data_width=14,
        data_decimals=13,
        data_signed=True,
        sampling_period_width=32,
        axi_hp_index=0).vis('out2.pdf',
                            platform = redpitaya.Platform(),
                            soc = StemlabSoc(platform = redpitaya.Platform()))
                            
    import matplotlib.pyplot as plt
    from numpy.random import randint
    
    # def func(i, out_value):
    #     retrun Lorenz(out_value) + np.random()
    
    query = {"sampling_period_cycles": {0:30},
             "trigger": {10:1, 11:0},
             "input": lambda i: randint(2**14),
             "value_max": None,
             "pulseburst.out":None,
             "value":None}

    t, results = DAQ(data_depth=2**12,
                     data_width=14,
                     data_decimals=13,
                     data_signed=True,
                     sampling_period_width=32,
                     axi_hp_index=0).sim(100, query,
                                         platform = redpitaya.Platform(),
                                         soc = StemlabSoc(platform = redpitaya.Platform()))

    fig, axs = plt.subplots(nrows = len(results), ncols = 1, sharex = True)
#    fig.supxlabel('Clock cycle')
#    fig.supylabel('Value')
    prop_cycle = plt.rcParams['axes.prop_cycle']
    colors = prop_cycle.by_key()['color']
    plt.tight_layout()

    for i, p in enumerate(results.items()):
        k, v = p
        axs[i].title.set_text(k)
        axs[i].plot(t, v, color = colors[i % len(colors)])
