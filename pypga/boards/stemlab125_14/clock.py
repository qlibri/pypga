from migen import ClockDomain, Instance, Signal, ClockSignal, Module
from migen.genlib.resetsync import AsyncResetSynchronizer


def create_stemlabs_clocks(module, platform):
    # signals for external connectivity
    clk_adc_pins = platform.request("clk125")
    platform.add_platform_command(
        "create_clock -name clk_adc -period 8 [get_ports {port}]",
        port=clk_adc_pins.p,
    )  # xdc 208
    clk_adc_unbuffered = Signal()
    clk_adc_buffered = Signal()
    module.specials += Instance(
        "IBUFGDS",
        i_I=clk_adc_pins.p,
        i_IB=clk_adc_pins.n,
        o_O=clk_adc_unbuffered,
    )
    module.specials += Instance(
        "BUFG", i_I=clk_adc_unbuffered, o_O=clk_adc_buffered
    )
    clk_feedback = Signal()
    clk_feedback_buffered = Signal()
    module.specials += Instance(
        "BUFG", i_I=clk_feedback, o_O=clk_feedback_buffered
    )
    clk_adc = Signal()
    clk_dac_1p = Signal()
    clk_dac_2x = Signal()
    clk_dac_2p = Signal()
    clk_ser = Signal()
    clk_pwm = Signal()
    reset = Signal(reset=1)
    locked = Signal()
    module.specials += [
        Instance(
            "PLLE2_ADV",
            p_BANDWIDTH="OPTIMIZED",
            p_COMPENSATION="ZHOLD",
            p_DIVCLK_DIVIDE=1,
            p_CLKIN1_PERIOD=8.000,
            p_REF_JITTER1=0.010,
            i_RST=~reset,
            i_CLKIN1=clk_adc_unbuffered,  # top.v 314 uses unbuffered version
            i_CLKIN2=0,
            i_CLKINSEL=1,
            i_PWRDWN=0,
            p_CLKFBOUT_MULT=8, #Converts 125MHz to 1GHz
            p_CLKFBOUT_PHASE=0.0,
            o_CLKFBOUT=clk_feedback,
            i_CLKFBIN=clk_feedback_buffered,
            o_LOCKED=locked,
            # dynamic reconfiguration settings, all disabled
            i_DADDR=0,
            i_DCLK=0,
            i_DEN=0,
            i_DI=0,
            i_DWE=0,
            # o_DO=,
            # o_DRDY=,
            p_CLKOUT0_DIVIDE=8,  # 125 MHz
            p_CLKOUT0_PHASE=0.0,
            p_CLKOUT0_DUTY_CYCLE=0.5,
            o_CLKOUT0=clk_adc,
            p_CLKOUT1_DIVIDE=8,  # 125 MHz
            p_CLKOUT1_PHASE=0.000,
            p_CLKOUT1_DUTY_CYCLE=0.5,
            o_CLKOUT1=clk_dac_1p,
            p_CLKOUT2_DIVIDE=4,  # 250 MHz
            p_CLKOUT2_PHASE=0.000,
            p_CLKOUT2_DUTY_CYCLE=0.5,
            o_CLKOUT2=clk_dac_2x,
            p_CLKOUT3_DIVIDE=4,  # 250 MHz, 45 degree advanced
            p_CLKOUT3_PHASE=-45.000,
            p_CLKOUT3_DUTY_CYCLE=0.5,
            o_CLKOUT3=clk_dac_2p,
            p_CLKOUT4_DIVIDE=4,  # 250 MHz
            p_CLKOUT4_PHASE=0.000,
            p_CLKOUT4_DUTY_CYCLE=0.5,
            o_CLKOUT4=clk_ser,
            p_CLKOUT5_DIVIDE=4,  # 250 MHz
            p_CLKOUT5_PHASE=0.000,
            p_CLKOUT5_DUTY_CYCLE=0.5,
            o_CLKOUT5=clk_pwm,
        )
    ]
    #Usually getx fondigured in lcock wizard in Vivado GUI
    
    module.clock_domains.sys_ps = ClockDomain()
    module.clock_domains.clk_adc = ClockDomain()
    module.clock_domains.clk_dac_1p = ClockDomain(reset_less=True) 
    module.clock_domains.clk_dac_2x = ClockDomain(reset_less=True)
    module.clock_domains.clk_dac_2p = ClockDomain(reset_less=True)
    module.clock_domains.clk_ser = ClockDomain(reset_less=True)
    module.clock_domains.clk_pwm = ClockDomain(reset_less=True)
    module.specials += Instance("BUFG", i_I=clk_adc, o_O=module.clk_adc.clk)
    module.specials += Instance("BUFG", i_I=clk_dac_1p, o_O=module.clk_dac_1p.clk)
    module.specials += Instance("BUFG", i_I=clk_dac_2x, o_O=module.clk_dac_2x.clk)
    module.specials += Instance("BUFG", i_I=clk_dac_2p, o_O=module.clk_dac_2p.clk)
    module.specials += Instance("BUFG", i_I=clk_ser, o_O=module.clk_ser.clk)
    module.specials += Instance("BUFG", i_I=clk_pwm, o_O=module.clk_pwm.clk)
    module.specials += Instance(
        "FD",
        p_INIT=1,
        i_D=~locked,
        i_C=module.clk_adc.clk,
        o_Q=module.clk_adc.rst,
    )

    # TODO: add resets
    # // ADC reset (active low)
    # always @(posedge adc_clk)
    # adc_rstn <=  frstn[0] &  pll_locked;
    #
    # // DAC reset (active high)
    # always @(posedge dac_clk_1x)
    # dac_rst  <= ~frstn[0] | ~pll_locked;
    #
    # // PWM reset (active low)
    # always @(posedge pwm_clk)
    # pwm_rstn <=  frstn[0] &  pll_locked;
    #
    # make adc clock the default
    # module.specials += Instance("BUFG", i_I=clk_adc, o_O=module.sys.clk)
    # module.specials += AsyncResetSynchronizer(module.cd_sys, ~module.fclk.reset_n[0])

    module.specials += Instance("BUFG", i_I=clk_adc, o_O=ClockSignal())
