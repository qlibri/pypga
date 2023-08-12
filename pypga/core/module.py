import functools
import logging
import typing
import os
import inspect
from typing import Callable
from migen.build.generic_platform import GenericPlatform

from .builder import get_builder
from .interface import LocalInterface, RemoteInterface
from .logic_function import is_logic
from .register import _Register
from .migen import AutoMigenModule

logger = logging.getLogger(__name__)


def scan_module_class(module_class) -> typing.Tuple[dict, dict, dict, dict]:
    """
    Returns all pypga objects defined in a given module class.

    The returned tuple contains the four dicts ``(registers, logic, submodules, other)``.
    """
    registers = {}
    logic = {}
    submodules = {}
    other = {}
    for name, value in typing.get_type_hints(module_class).items():
        if isinstance(value, type) and issubclass(value, Module):
            submodules[name] = value
        elif isinstance(value, type) and issubclass(value, _Register):
            registers[name] = value
        else:
            # let common coding mistakes produce an error
            if isinstance(value, _Register):
                raise ValueError(
                    f"Register {name} should not be instantiated. "
                    f"Type annotations require the type, not an "
                    f"instance. Consider removing `()` from the "
                    f"register definition."
                )
            elif isinstance(value, Module):
                raise ValueError(
                    f"Submodule {name} should not be instantiated. "
                    f"Type annotations require the type, not an "
                    f"instance. Consider removing `()` from the "
                    f"module definition."
                )
            else:
                logger.debug(f"Ignoring annotated type {name}: {value}.")
    for name in dir(module_class):
        value = getattr(module_class, name)
        if is_logic(value):
            logic[name] = value
        elif isinstance(value, _Register):
            logger.warning(
                f"The register {name} was already instantiated. This is "
                f"currently discouraged and not fully supported."
            )
            registers[name] = value
        else:
            if not name.startswith("__"):
                other[name] = value
    return registers, logic, submodules, other


class Module:
    @classmethod
    def __init_subclass__(cls):
        logger.debug(f"Running {cls}.__init_subclass__.")
        # 1. extract which registers and submodules are defined
        (
            cls._pypga_registers,
            cls._pypga_logic,
            cls._pypga_submodules,
            other,
        ) = scan_module_class(cls)
        # 2. instantiate all registers
        for name, register_cls in cls._pypga_registers.items():
            try:
                register = getattr(cls, name)
            except AttributeError:
                register = register_cls()
                register.name = name
                setattr(cls, name, register)
            else:
                # register was already instantiated
                assert isinstance(register, _Register)
                assert register.name == name
        # 3. insert call to _init_module into constructor for submodule instantiation at runtime
        old_init = functools.partial(cls.__init__)

        @functools.wraps(cls.__init__)
        def new_init(self, *args, name="top", parent=None, interface=None, **kwargs):
            self._init_module(name, parent, interface)
            old_init(self, *args, **kwargs)

        cls.__init__ = new_init
        # 4. compute hash for module

    def _init_module(self, name, parent, interface):
        """Initializes the pypga module hierarchy before the actual constructor is called."""
        if hasattr(self, "_parent") and hasattr(self, "_interface"):
            logger.debug(f"Skipping {self}._init_module because it has already run.")
            return
        logger.debug(
            f"Running {self}._init_module(self={self}, parent={parent}, interface={interface})."
        )
        self._name = name
        self._parent = parent
        self._interface = interface
        for name, submodule_cls in self._pypga_submodules.items():
            setattr(
                self, name, submodule_cls(name=name, parent=self, interface=interface)
            )

    def _get_parents(self):
        parents = [self._name]
        parent = self._parent
        while parent is not None:
            parents.insert(0, parent._name)
            parent = parent._parent
        return parents

    def _get_full_name(self):
        parents = self._get_parents()
        return parents[0] + "." + "_".join(parents[1:])

    @property
    def registers(self):
        registers = {name: getattr(self, name) for name in self._pypga_registers}
        return {k: v for k, v in registers.items() if not isinstance(v, Callable)}

    @property
    def _clock_period(self):
        # TODO: generalize to multiple boards
        return 8e-9

    @property
    def _clock_rate(self):
        # TODO: generalize to multiple boards
        return 1 / self._clock_period

    @property
    def _ram_start(self):
        # TODO: generalize to multiple boards
        return 0xA000000
    
    @classmethod
    def sim(cls, num_steps, query, platform = GenericPlatform, soc = None, omit_csr = True):
        from migen.sim import run_simulation
        
        module = AutoMigenModule(cls, platform, soc, omit_csr = omit_csr)
        t = []
        results = {k: [] for k in query}
        
        def getattr_(obj, lst):
            """
            Equivalent for getattr() for nested objects
            """
            if len(lst) == 1:
                return getattr(obj, lst[0])
            else:
                return getattr_(getattr(obj, lst[0]), lst[1:])
            
        def sim():
            """
            Run simulation and store parameter values in global lists
            """
            for i in range(num_steps):
                t.extend([i, i+1])
                for k, v in query.items():
                    # try:
                    #     yield getattr_(module, k.split('.')).eq(v(i))
                    #     val = (yield getattr_(module, k.split('.')))
                    # except:
                    if v is None:
                        val = (yield getattr_(module, k.split('.')))
                    if isinstance(v, dict):
                        if i in v:
                            yield getattr_(module, k.split('.')).eq(v[i])
                        val = (yield getattr_(module, k.split('.')))
                    if callable(v):
                        arglist = inspect.getfullargspec(v).args
                        kwargs = {}
                        for arg in arglist[1:]:
                            kwargs[arg] = (yield getattr_(module, arg.split('.')))
                        yield getattr_(module, k.split('.')).eq(v(i, **kwargs))
                        val = (yield getattr_(module, k.split('.')))
                    results[k].extend([val]*2)
                yield
                
        run_simulation(module, sim())
        return t, results    
    
    @classmethod
    def vis(cls, fname, platform = GenericPlatform, soc = None, omit_csr = True):
        from migen.fhdl.structure import _Assign, Signal, _Operator, Constant, If, Case, Cat, _Slice
        
        if os.path.splitext(fname)[1] != '.pdf':
            raise ValueError('Only PDF output is supported.')
        
        def get_name(signal):
            """
            Get name of a signal, omitting common prefixes.
            """
            pre = signal.backtrace[-2][0]
            if pre.endswith('automigenmodule') or pre.endswith('custom_numberregister') or pre.endswith('custom_fixedpointregister') or pre.endswith('custom_boolregister'):
                pre = ''
            else:
                pre += '.'
            return (pre + signal.backtrace[-1][0])
        
        def handle_signal(s):
            return {str(id(s)): {'name': get_name(s), 'nbits': s.nbits, 'signed': s.signed}}, set()
        
        def handle_constant(s):
            # Don't include constants in visualization
            return dict(), set()
        
        def handle_operator(s):
            nodes = dict()
            edges = set()
            for o in s.operands:
                handler = handler_mapping[type(o)]
                n, e = handler(o)
                nodes.update(n)
                edges.update(e)
                    
            return nodes, edges
        
        def handle_assign(s):
            nodes = dict()
            edges = set()
            
            nl, el = handle_signal(s.l)
            nodes.update(nl)
            edges.update(el)
            
            handler = handler_mapping[type(s.r)]
            nr, er = handler(s.r)
            nodes.update(nr)
            edges.update(er)
            
            for n in nr:
                edges.add((n, next(iter(nl))))
                
            return nodes, edges
        
        def handle_cat(s):
            nodes = dict()
            edges = set()
            
            for r in s.l:
                handler = handler_mapping[type(r)]
                n, e = handler(r)
                nodes.update(n)
                edges.update(e)
                
            return nodes, edges
                
        def handle_if(s):
            nodes = dict()
            edges = set()
            
            for t in s.t:
                handler = handler_mapping[type(t)]
                n, e = handler(t)
                nodes.update(n)
                edges.update(e)
            for f in s.f:
                handler = handler_mapping[type(f)]
                n, e = handler(f)
                nodes.update(n)
                edges.update(e)
                
            return nodes, edges
        
        def handle_case(s):
            nodes = dict()
            edges = set()
            
            for k, v in s.cases.items():
                for r in v:
                    handler = handler_mapping[type(r)]
                    n, e = handler(r)
                    nodes.update(n)
                    edges.update(e)
                
            return nodes, edges
        
        def handle_slice(s):
            return handle_signal(s.value)
                
        handler_mapping = {_Assign: handle_assign,
                           Signal: handle_signal,
                           _Operator: handle_operator,
                           Constant: handle_constant, 
                           If: handle_if,
                           Case: handle_case,
                           Cat: handle_cat,
                           _Slice: handle_slice}
        
        nodes = dict()
        sync_edges = set()
        comb_edges = set()
        module = AutoMigenModule(cls, platform, soc, omit_csr = omit_csr)

        for s in module.sync._fm._fragment.sync['sys']:
            #print(s)
            handler = handler_mapping[type(s)]
            n, e = handler(s)
            nodes.update(n)
            sync_edges.update(e)
        
        for s in module.sync._fm._fragment.comb:
            #print(s)
            handler = handler_mapping[type(s)]
            n, e = handler(s)
            nodes.update(n)
            comb_edges.update(e)
        
        for s in module.comb._fm._fragment.sync['sys']:
            #print(s)
            handler = handler_mapping[type(s)]
            n, e = handler(s)
            nodes.update(n)
            sync_edges.update(e)
        
        for s in module.comb._fm._fragment.comb:
            #print(s)
            handler = handler_mapping[type(s)]
            n, e = handler(s)
            nodes.update(n)
            comb_edges.update(e)
        
        import graphviz
        dot = graphviz.Digraph('DAQ')
        
        for k, v in nodes.items():
            if v['signed']:
                color = "lightcoral"
            else:
                color = "lightgreen"
            dot.node(k, f"<<b>{k}</b><br/>bits={v['nbits']}<br/>signed={v['signed']}>", style="filled", fillcolor=color)
            
        for p in sync_edges:
            a, b = p
            dot.edge(a, b)
            
        for p in comb_edges:
            a, b = p
            dot.edge(a, b, color="black:none:black", arrowhead="none")
            
        dot.render(os.path.splitext(fname)[0], cleanup=True)


DEFAULT_BOARD = "stemlab125_14"


class TopModule(Module):
    @classmethod
    def _build(cls, board=DEFAULT_BOARD):
        builder = get_builder(board=board, module_class=cls)
        return builder.build()

    @classmethod
    @functools.wraps(RemoteInterface)
    def run(
        cls,
        *args,
        host=None,
        password=None,
        board=DEFAULT_BOARD,
        autobuild=True,
        forcebuild=False,
        **kwargs,
    ):
        """Runs the design on a board and returns an interfaced instance."""
        builder = get_builder(board=board, module_class=cls)
        if forcebuild or not builder.result_exists:
            if autobuild or forcebuild:
                builder.build()
            else:
                raise ValueError(
                    "The design you are trying to instantiate must be built first. Try "
                    "running this function call with the argument ``autobuild=True``."
                )
        if host is None:
            interface = LocalInterface(result_path=builder.result_path)
        else:
            interface = RemoteInterface(host=host, password=password, result_path=builder.result_path)
        return cls(*args, interface=interface, **kwargs)

    def stop(self):
        self._interface.stop()

    def __del__(self):
        self.stop()
