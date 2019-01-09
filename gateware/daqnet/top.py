from nmigen import Signal, Module, ClockDomain
from .platform import SB_PLL40_PAD, SB_IO

from .ethernet.mac import MAC
from .ethernet.ip import IPStack
# from .uart import UARTTxFromMemory, UARTTx


class LEDBlinker:
    def __init__(self, nbits):
        self.led = Signal()
        self.nbits = nbits

    def get_fragment(self, platform):
        m = Module()
        divider = Signal(self.nbits)
        m.d.sync += divider.eq(divider + 1)
        m.d.comb += self.led.eq(divider[-1])
        return m.lower(platform)


class Top:
    def __init__(self, platform, args):
        pass


class SensorTop(Top):
    def __init__(self, platform, args):
        self.led_blinker = LEDBlinker(23)

    def get_fragment(self, platform):
        m = Module()

        # Set up PLL
        m.submodules.pll = pll = SB_PLL40_PAD(0, 31, 3, 2)
        pll.packagepin = platform.request("clk25")
        pll.plloutglobal = Signal()

        # Set up clock domain on PLL output
        cd = ClockDomain("sync", reset_less=True)
        m.d.comb += cd.clk.eq(pll.plloutglobal)

        # Create LED blinker in PLL clock domain
        blinker = self.led_blinker.get_fragment(platform)
        blinker.add_domains(cd)
        m.submodules.led_blinker = blinker
        m.d.comb += platform.request("user_led_3").eq(self.led_blinker.led)

        frag = m.lower(platform)

        # Add all the ports used on the platform to this module's ports
        for port, dirn in platform.get_ports():
            frag.add_ports(port, dir=dirn)

        return frag


class SwitchTop(Top):
    def __init__(self, platform, args):
        self.led_blinker = LEDBlinker(24)

    def get_fragment(self, platform):
        m = Module()

        # Set up PLL to multiply 25MHz clock to 100MHz clock
        m.submodules.pll = pll = SB_PLL40_PAD(0, 31, 3, 2)
        pll.packagepin = platform.request("clk25")
        pll.plloutglobal = Signal()

        # Set up clock domain on output of PLL
        cd = ClockDomain("sync", reset_less=True)
        m.d.comb += cd.clk.eq(pll.plloutglobal)

        # Ethernet MAC
        rmii = platform.request_group("rmii")
        phy_rst = platform.request("phy_rst")
        eth_led = platform.request("eth_led")
        mac_addr = "02:44:4E:30:76:9E"
        mac = MAC(100e6, 0, mac_addr, rmii, phy_rst, eth_led)
        m.submodules.mac = mac

        # IP stack
        ip4_addr = "10.1.1.5"
        ipstack = IPStack(
            ip4_addr, mac_addr, self.mac.rx_port, self.mac.tx_port)
        m.submodules.ipstack = ipstack
        m.comb += [
            ipstack.rx_valid.eq(mac.rx_valid),
            ipstack.rx_len.eq(mac.rx_len),
            ipstack.tx_ready.eq(mac.tx_ready),
            mac.rx_ack.eq(ipstack.rx_ack),
            mac.tx_start.eq(ipstack.tx_start),
            mac.tx_len.eq(ipstack.tx_len),
        ]

        frag = m.lower(platform)

        # Add all the ports used on the platform to this module's ports
        for port, dirn in platform.get_ports():
            frag.add_ports(port, dir=dirn)

        return frag


class ProtoSwitchTop(Module):
    def __init__(self, platform):
        self.clock_domains.sys = ClockDomain("sys")
        clk25 = platform.request("clk25")

        # Set up 100MHz PLL
        self.submodules.pll = PLL(divr=0, divf=31, divq=3, filter_range=2)
        self.comb += self.pll.clk_in.eq(clk25)
        self.comb += self.sys.clk.eq(self.pll.clk_out)

        # Instantiate Ethernet MAC
        rmii = platform.request("rmii")
        phy_rst = platform.request("phy_rst")
        eth_led = platform.request("eth_led")
        mac_addr = "02:44:4E:30:76:9E"
        self.submodules.mac = MAC(100e6, 0, mac_addr, rmii, phy_rst, eth_led)

        # Instantiate IP stack
        ip4_addr = "10.1.1.5"
        self.submodules.ipstack = IPStack(
            ip4_addr, mac_addr, self.mac.rx_port, self.mac.tx_port)
        self.comb += [
            self.ipstack.rx_valid.eq(self.mac.rx_valid),
            self.ipstack.rx_len.eq(self.mac.rx_len),
            self.ipstack.tx_ready.eq(self.mac.tx_ready),
            self.mac.rx_ack.eq(self.ipstack.rx_ack),
            self.mac.tx_start.eq(self.ipstack.tx_start),
            self.mac.tx_len.eq(self.ipstack.tx_len),
        ]

        # Debug outputs
        led1 = platform.request("user_led")
        led2 = platform.request("user_led")

        self.comb += [
            led1.eq(eth_led),
            led2.eq(self.mac.link_up),
        ]
