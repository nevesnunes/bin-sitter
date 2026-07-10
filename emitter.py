#!/usr/bin/env python3

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from io import BufferedReader, BytesIO
from kaitaistruct import KaitaiStruct, KaitaiStream, BytesIO
from typing import (
    ClassVar,
    Dict,
    Iterator,
    List,
    Optional,
    override,
    Set,
    Type,
    Union,
    Tuple,
)
import argparse
import attrs
import importlib
import inspect
import json
import kaitaistruct
import os
import re
import select
import shutil
import sys
import time

from finder import FieldAssignmentFinder
from logger import logger
import renderer


@dataclass(unsafe_hash=True, order=True, frozen=True)
class Segment:
    start: int
    end: int

    def __contains__(self, item):
        return (
            isinstance(item, Segment)
            and item.start >= self.start
            and item.end <= self.end
        )

    def __len__(self):
        return self.end - self.start

    def __bool__(self):
        return len(self) > 0

    def __getitem__(self, index_or_slice: Union[int, slice]):
        if isinstance(index_or_slice, slice):
            if index_or_slice.step is not None and index_or_slice.step != 1:
                raise ValueError(
                    f"{self.__class__.__name__}.__getitem__ only supports slices with step=1"
                )
            if index_or_slice.start is None:
                new_start = self.start
            else:
                new_start = self.start + index_or_slice.start
            if index_or_slice.stop is None:
                new_end = self.end
            elif index_or_slice.stop < 0:
                new_end = self.end + index_or_slice.stop
            else:
                new_end = self.start + index_or_slice.stop
            if new_start > self.end:
                new_start = self.end
            if new_end < new_start or new_end > self.end:
                new_end = new_start
            return Segment(new_start, new_end)
        elif self.start + index_or_slice >= self.end or (
            index_or_slice < 0 and -index_or_slice > len(self)
        ):
            raise IndexError(index_or_slice)
        elif index_or_slice < 0:
            return Segment(self.end + index_or_slice, self.end + index_or_slice + 1)
        else:
            return Segment(self.start + index_or_slice, self.start + index_or_slice + 1)


class ASTNode:
    """Represents an element in a parse."""

    def __init__(
        self,
        name: str,
        segment: Segment,
        offset: int,
        parent: Optional["CompoundNode"] = None,
    ):
        self.name: str = name
        self.segment: Segment = segment
        self.offset: int = offset
        if parent is None:
            if not isinstance(self, RootNode):
                raise ValueError(f"Only a RootNode can have no parent, not {self!r}")
            self.root: RootNode = self
            self.level: int = 0
        else:
            self.root = parent.root
            self.level = parent.level + 1
        self.parent: Optional[CompoundNode] = parent

    def dfs(self) -> Iterator["ASTNode"]:
        yield self

    @property
    def start(self) -> int:
        return self.offset + self.segment.start

    @property
    def end(self) -> int:
        return self.offset + self.segment.end

    @property
    def raw_value(self):
        """Sequence of bytes of this segment."""
        return self.root.get_value(self.start, self.end)

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def children(self) -> List["ASTNode"]:
        return []

    def __repr__(self):
        return f"{self.name}({self.__class__.__name__}) [{self.start}:{self.end}]"


class ValueNode(ASTNode):
    """A leaf in the parse tree."""

    TYPES = (int, float, str, bytes, Enum)

    def __init__(self, value: bytes, *args, **kwargs):
        self._value: bytes = value
        super().__init__(*args, **kwargs)

    @property
    def value(self) -> bytes:
        return self._value

    def __repr__(self):
        return f"{self.name}({self.__class__.__name__}<{self.value.__class__.__name__}>) [{self.start}:{self.end}]"


class CompoundNode(ASTNode, ABC):
    """A node that can have children"""

    def __init__(self, obj: KaitaiStruct, *args, **kwargs):
        self.obj: KaitaiStruct = obj
        super().__init__(*args, **kwargs)
        self._children: Optional[List[ASTNode]] = None

    @property
    def children(self) -> List[ASTNode]:
        if self._children is None:
            self._children = list(self.explore())
        return self._children

    @abstractmethod
    def explore(self) -> Iterator[ASTNode]:
        raise NotImplementedError()

    def dfs(self) -> Iterator[ASTNode]:
        stack = [self]
        while stack:
            top = stack.pop()
            yield top
            stack.extend(reversed(top.children))

    def make_child(
        self,
        obj: KaitaiStruct,
        name: str,
        segment: Segment,
        offset: int,
    ) -> ASTNode:
        if isinstance(obj, KaitaiStruct):
            node_class = StructNode
        elif isinstance(obj, ValueNode.TYPES):
            node_class = ValueNode
        elif isinstance(obj, list):
            node_class = ArrayNode
        else:
            raise TypeError(f"Unknown object type: {type(obj)}")

        return node_class(obj, name, segment, offset, self)


class StructNode(CompoundNode):
    """Represents node of the subtype."""

    def explore(self) -> Iterator[ASTNode]:
        # Force instance properties to be fetched.
        inspect.getmembers(self.obj)

        instance_names = set(
            n for n in self.obj.__static_attributes__ if n.startswith("_m_")
        )
        for name in instance_names.union(self.obj.SEQ_FIELDS):
            markers = self.obj._debug[name].copy()
            if "arr" in markers:
                del markers["arr"]
            if "start" not in markers or "end" not in markers:
                continue
            segment = Segment(**markers)
            offset = self.offset
            if isinstance(self.parent, StructNode):
                if self.obj._io != self.parent.obj._io:
                    offset = self.start
            if hasattr(self.obj, name):
                yield self.make_child(getattr(self.obj, name), name, segment, offset)


class ArrayNode(CompoundNode):
    """Represents node of array of subtype items."""

    def explore(self) -> Iterator[ASTNode]:
        for i, obj in enumerate(self.obj):
            markers = self.parent.obj._debug[self.name]["arr"][i]
            segment = Segment(**markers)
            name = f"{self.name}[{i}]"
            yield self.make_child(obj, name, segment, self.offset)


class RootNode(StructNode):
    def __init__(self, buffer: bytes, obj: KaitaiStruct):
        self.buffer: bytes = buffer
        super().__init__(
            obj,
            name=obj.__class__.__name__,
            segment=Segment(0, len(self.buffer)),
            offset=0,
        )

    def get_value(self, start, end):
        return self.buffer[start:end]


@dataclass(unsafe_hash=True, order=True, frozen=True)
class TraversalNode:
    depth: int
    node: ASTNode
    rel_ofs: int


@dataclass(unsafe_hash=True, order=True)
class RuleOffsets:
    TOKEN_TYPE_COUNTER: ClassVar = 0
    TOKEN_TYPE_IDX_MAP: ClassVar = {}

    start: int
    depth: int
    end: int
    name: str
    parent_name: str

    flat_name: str = field(init=False)
    sz: int = field(init=False)

    def __post_init__(self):
        if not self.name:
            raise RuntimeError(f"name empty @ {self.start}")

        self.flat_name = (
            self.name if not self.parent_name else self.parent_name + "__" + self.name
        )
        if self.flat_name not in RuleOffsets.TOKEN_TYPE_IDX_MAP:
            RuleOffsets.TOKEN_TYPE_IDX_MAP[self.flat_name] = (
                RuleOffsets.TOKEN_TYPE_COUNTER
            )
            RuleOffsets.TOKEN_TYPE_COUNTER += 1

        self.sz = self.end - self.start
        if self.sz < 0:
            raise RuntimeError(
                f"{self.flat_name} @ {self.start}: sz = {self.end} - {self.start} <= 0"
            )


class Emitter:
    def __init__(self, struct: KaitaiStruct, flat: bool = True):
        self._emit = self.emit_flat if flat else self.emit_hier
        self._name = struct.__class__.__name__
        self.struct: KaitaiStruct = struct

    def emit(self):
        return self._emit()

    @abstractmethod
    def emit_flat(self):
        raise NotImplementedError()

    @abstractmethod
    def emit_hier(self):
        raise NotImplementedError()

    def _clean(self, name: str):
        name = re.sub(r"^_m_", "", name)
        name = re.sub(r"(.*)\[.*\]$", "\\1", name)
        return name

    def _clean_parents(self, node):
        name = ""
        while node.parent and node.parent.name != self._name:
            if not isinstance(node.parent, ArrayNode):
                name = "__".join(filter(None, (self._clean(node.parent.name), name)))
            node = node.parent
        return name


class GrammarEmitter(Emitter):
    def __init__(self, struct: KaitaiStruct, parser_path: str):
        super().__init__(struct)

        self.finder = FieldAssignmentFinder()
        with open(parser_path, "r") as f:
            self.finder.from_source_str(f.read())

    @override
    def emit_flat(self):
        rule_mappings = self.rule_mappings()

        flat_names = set()
        leafs = set()
        for parent_name, names in rule_mappings.items():
            for name in names:
                if name not in rule_mappings:
                    if parent_name == self._name:
                        flat_names.add(name)
                    else:
                        leafs.add(name)

        stack = []
        for name in leafs:
            for k, v in rule_mappings.items():
                if name in v:
                    stack.append((k, name))

            while stack:
                parent_name, flat_name = stack.pop()
                if parent_name == self._name:
                    flat_names.add(flat_name)
                    continue

                flat_name = parent_name + "__" + flat_name
                for k2, v2 in rule_mappings.items():
                    if parent_name in v2:
                        stack.append((k2, flat_name))

        i = 0
        flat = {}
        flat_names = sorted(list(flat_names))
        flat_names.append("pad")
        for name in flat_names:
            flat[name] = i
            i += 1

        return flat

    @override
    def emit_hier(self):
        rule_mappings = self.rule_mappings()

        i = 0
        hier = {}
        seen_names = set()
        for _k, v in rule_mappings.items():
            for name in v:
                if name not in seen_names:
                    seen_names.add(name)
                    hier[name] = i
                    i += 1

        return hier

    def rule_mappings(self):
        for k, v in self.finder.matches.items():
            logger.debug(k, v)

        rule_mappings = {self._name: set()}
        stack = [(self._name, self._name)]
        while stack:
            parent, clazz = stack.pop()
            if parent not in rule_mappings:
                rule_mappings[parent] = set()

            for match in self.finder.matches[clazz]:
                name = self._clean(match.lhs) if match.prop else match.lhs
                if match.rhs in self.finder.matches:
                    stack.append((name, match.rhs))

                if name not in rule_mappings[parent]:
                    rule_mappings[parent].add(name)

        logger.debug(rule_mappings)
        return rule_mappings

    def matched_t_attrs(self):
        return self.finder.matched_t_attrs


class OffsetEmitter(Emitter):
    def __init__(self, struct: KaitaiStruct, matched_t_attrs: Set[str]):
        super().__init__(struct)

        self._ast: Optional[RootNode] = None
        self._size = struct._io.size()
        self._matched_t_attrs = matched_t_attrs

    @property
    def ast(self) -> RootNode:
        if self._ast is None:
            _io = self.struct._io._io
            if isinstance(_io, BufferedReader):
                with open(self.struct._io._io.name, "rb") as f:
                    buffer = f.read()
            elif isinstance(_io, BytesIO):
                buffer = _io.getbuffer().tobytes()
            else:
                raise TypeError(f"Unsupported stream type: {_io.__class__.__name__}")

            self._ast = RootNode(buffer, self.struct)

        return self._ast

    def with_padding(self, rules: List[RuleOffsets]) -> List[RuleOffsets]:
        rules.sort(key=lambda r: r.start)
        cov = [0] * self._size
        for r in rules:
            for i in range(r.start, r.end):
                cov[i] = 1

        pad_interval = False
        pad_start = 0
        for i in range(len(cov)):
            if cov[i] == 0 and pad_interval == False:
                pad_start = i
                pad_interval = True
            elif cov[i] == 1 and pad_interval:
                pad_interval = False
                rules.append(RuleOffsets(pad_start, 0, i, "pad", ""))

        return sorted(rules)

    @override
    def emit_flat(self) -> List[RuleOffsets]:
        # Assumed sorted.
        stack = [TraversalNode(0, c, 0) for c in self.ast.children]

        rules = []
        while stack:
            tnode = stack.pop()
            rel_ofs = 0
            if not isinstance(tnode.node.parent, ArrayNode):
                if len(tnode.node.children) == 0:
                    rules.append(
                        RuleOffsets(
                            tnode.rel_ofs + tnode.node.start,
                            tnode.depth,
                            tnode.rel_ofs + tnode.node.end,
                            self._clean(tnode.node.name),
                            self._clean_parents(tnode.node),
                        )
                    )
            else:
                logger.debug(tnode.node.parent.name, tnode.node.parent.start, tnode.node.parent.end, tnode.node.name, tnode.node.start, tnode.node.end, tnode.node.children)
                if self._clean(tnode.node.name) in self._matched_t_attrs:
                    rel_ofs = tnode.node.start
            for node_child in tnode.node.children:
                stack.append(TraversalNode(tnode.depth + 1, node_child, rel_ofs))

        return self.with_padding(rules)

    @override
    def emit_hier(self) -> List[RuleOffsets]:
        # Assumed sorted.
        stack = [TraversalNode(0, c, 0) for c in self.ast.children]

        rules = []
        while stack:
            tnode = stack.pop()
            rel_ofs = 0
            if not isinstance(tnode.node.parent, ArrayNode):
                parent_name = (
                    tnode.node.parent.name if tnode.node.parent else self._name
                )
                rules.append(
                    RuleOffsets(
                        tnode.node.start,
                        tnode.depth,
                        tnode.node.end,
                        self._clean(tnode.node.name),
                        self._clean(parent_name),
                    )
                )
            else:
                if self._clean(tnode.node.name) in self._matched_t_attrs:
                    rel_ofs = tnode.node.start
            for node_child in tnode.node.children:
                stack.append(TraversalNode(tnode.depth + 1, node_child, rel_ofs))

        return self.with_padding(rules)


def import_parser(path: str) -> Type[KaitaiStruct]:
    if not path:
        raise RuntimeError("Missing input parser path")

    assert path.lower().endswith(".py")
    module_name = f"{__name__}.parsers.{os.path.basename(path)[:-3]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for _obj_name, obj in inspect.getmembers(module):
        if inspect.isclass(obj):
            fqn = ".".join([obj.__module__, obj.__name__])
            if f"{__name__}.parsers" in fqn:
                return obj

    raise RuntimeError(f"Could not find parser class in {path}")


def init_struct(parser_path: str, data_path: str) -> Type[KaitaiStruct]:
    if not data_path:
        raise RuntimeError("Missing input data path")

    parser = import_parser(parser_path)

    struct = parser.from_file(data_path)
    struct._read()
    logger.debug(struct._debug)

    return struct


FIFO_IN = "/tmp/bs.in"
FIFO_OUT = "/tmp/bs.out"


def run_server(parser_path: str):
    if os.path.exists(FIFO_IN):
        os.remove(FIFO_IN)
    os.mkfifo(FIFO_IN)

    if os.path.exists(FIFO_OUT):
        os.remove(FIFO_OUT)
    os.mkfifo(FIFO_OUT)

    while True:
        """
        [0:4]    Data size: u32
        [4:4+sz] Data: u8[]
        """
        buf: bytearray
        i = 0
        logger.info(f"Polling '{FIFO_IN}'.")
        with open(FIFO_IN, "rb") as f:
            poller = select.poll()
            poller.register(f, select.POLLHUP | select.POLLERR)
            is_running = True
            sz: int = 0
            while is_running:
                for fd, mask in poller.poll(0):
                    if fd == f.fileno() and mask & (select.POLLHUP | select.POLLERR):
                        logger.info("Writer closed pipe, stopping reader...")
                        f.close()
                        is_running = False
                        break
                if sz == 0:
                    sz = int.from_bytes(f.read(4), "little")
                    logger.info(f"Reading {hex(sz)} ({sz}) bytes from '{FIFO_IN}'.")
                    buf = bytearray(sz)
                    if sz == 0:
                        raise RuntimeError("sz == 0")
                else:
                    buf[i : i + 1] = f.read(1)
                    i += 1
                    if i >= sz:
                        break

        parser = import_parser(parser_path)
        struct = parser.from_bytes(buf)
        struct._read()

        emitter = GrammarEmitter(struct, args.parser_path)
        matched_t_attrs = emitter.matched_t_attrs()
        rule_mappings = emitter.emit()
        for k, v in rule_mappings.items():
            logger.debug(k, v)

        emitter = OffsetEmitter(struct, matched_t_attrs)
        rules: List[RuleOffsets] = [r for r in emitter.emit() if r.sz > 0]

        """
        [0:4]    Data size: u32
        [4:4+sz] Data: u32[]
          - [i:i+4]   TokenType enum index: u32
          - [i+4:i+8] Number of bytes consumed by lexer: u32
        """
        out_sz = 2 * 4 * len(rules)
        logger.info(f"Sending {hex(out_sz)} ({out_sz}) bytes to '{FIFO_OUT}'.")
        with open(FIFO_OUT, "wb") as f:
            f.write(out_sz.to_bytes(4, "big"))
            for r in rules:
                logger.debug(r)
                if r.flat_name not in rule_mappings:
                    raise RuntimeError(f"Not mapped by GrammarEmitter: {r}")
                f.write(r.sz.to_bytes(4, "big"))
                f.write(rule_mappings[r.flat_name].to_bytes(4, "big"))


def run_oneshot(parser_path: str, data_path: str, update_path: str, file_type: str):
    struct = init_struct(parser_path, data_path)
    emitter = GrammarEmitter(struct, parser_path)
    matched_t_attrs = emitter.matched_t_attrs()
    rule_mappings = emitter.emit()
    for k, v in rule_mappings.items():
        logger.debug(k, v)

    name = struct.__class__.__name__.lower()
    renderer.grammar(name, rule_mappings.keys())
    renderer.highlights(name, rule_mappings.keys())
    renderer.scanner(name, rule_mappings.keys())
    if update_path:
        shutil.copytree(f"./generated/{name}", update_path, dirs_exist_ok=True)

        package_path = f"{update_path}/package.json"
        if os.path.isfile(package_path):
            if not file_type:
                file_type = name
            with open(package_path, "r") as f:
                package_data = json.load(f)
            package_data.update(
                {
                    "tree-sitter": [
                        {
                            "scope": f"source.{name}",
                            "file-types": [file_type],
                            "injection-regex": name,
                            "highlights": ["queries/highlights.scm"],
                        }
                    ]
                }
            )
            with open(package_path, "w") as f:
                f.write(json.dumps(package_data, indent=2))

    emitter = OffsetEmitter(struct, matched_t_attrs)
    rules: List[RuleOffsets] = [r for r in emitter.emit() if r.sz > 0]
    for r in rules:
        logger.debug(r)
        if r.flat_name not in rule_mappings:
            raise RuntimeError(f"Not mapped by GrammarEmitter: {r}")


class LayoutArg(str, Enum):
    flat = "flat"
    hier = "hier"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--layout",
        choices=[arg.value for arg in LayoutArg],
        default=LayoutArg.flat,
        type=LayoutArg,
        help="rule offsets emitted with flattened parents (i.e. a single rule for each terminal token) or hierarchical parents (i.e. distinct rules for each parent and terminal token)",
    )
    parser.add_argument(
        "--server",
        default=False,
        action="store_true",
        help=f"true to start in server mode: input data and emitted rules are passed via named pipes '{FIFO_IN}' and '{FIFO_OUT}'; false to pass input data as argument, and emit to stdout",
    )
    parser.add_argument(
        "parser_path",
        type=str,
        help="filename of kaitai-struct parser generated as python class",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        help="filename of input data to be parsed",
    )
    parser.add_argument(
        "--file-type",
        type=str,
        help="file type associated with the generated parser",
    )
    parser.add_argument(
        "--update-path",
        type=str,
        help="filename of output tree-sitter directory to be populated by generated files",
    )
    args = parser.parse_args()

    if args.server:
        run_server(args.parser_path)
    else:
        run_oneshot(args.parser_path, args.data_path, args.update_path, args.file_type)
