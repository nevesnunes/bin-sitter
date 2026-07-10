#!/usr/bin/env python3

from pprint import pp
import unittest

from emitter import init_struct, OffsetEmitter
from finder import FieldAssignmentFinder


class TestEmitter(unittest.TestCase):

    EXPECTED_OFFSETS_PTRS = [
        { "start": 0, "end": 2, },
        { "start": 2, "end": 4, },
        { "start": 4, "end": 5, },
        { "start": 5, "end": 6, },
        { "start": 6, "end": 7, },
        { "start": 7, "end": 8, },
        { "start": 8, "end": 16, },
        { "start": 16, "end": 18, },
        { "start": 18, "end": 20, },
        { "start": 20, "end": 22, },
        { "start": 22, "end": 24, },
        { "start": 24, "end": 62, },
        { "start": 62, "end": 64, },
    ]

    def test_offsets_ptrs(self):
        struct = init_struct("./kaitai/ptrs.py", "./examples/0.bin")

        emitter = OffsetEmitter(struct, set())
        rules = emitter.emit()
        self.assertEqual(
            len(rules), len(self.EXPECTED_OFFSETS_PTRS), "Number of rules emitted."
        )
        for i in range(len(rules)):
            self.assertEqual(
                rules[i].start,
                self.EXPECTED_OFFSETS_PTRS[i]["start"],
                f"Computed rule #{i} offset start.",
            )
            self.assertEqual(
                rules[i].end,
                self.EXPECTED_OFFSETS_PTRS[i]["end"],
                f"Computed rule #{i} offset end.",
            )

    FINDER_INPUT_SOURCE = """
@dataclass(unsafe_hash=True, order=True, frozen=True)
class DataFoo:
    foo: int

class Foo:
    def __init__(self):
        self.data: int = None

    @property
    def find1(self):
        self.data[i][0] = DataFoo(1)

    @property
    def skip2(self):
        data = DataFoo(2)

    def skip3(self):
        self.data = DataFoo(3)

    @property
    def find4(self):
        self.data: DataFoo = DataFoo(4)

    @property
    def find5(self):
        self.data: DataFoo = __name__.DataFoo(5)

    # TODO: False positive
    # @property
    # def skip6(self):
    #     x = DataFoo(6)
    #     x = 6
    #     self.data.append(x)

    # TODO: False negative
    # @property
    # def find7(self):
    #     x = DataFoo(7)
    #     y = x
    #     self.data.append(y)

    @property
    def skip8(self):
        x = 42
        y = DataFoo(8)
        self.data.append(x)

    @property
    def find9(self):
        for i in range(1):
            try:
                x = DataFoo(9)
            finally:
                self.data.append(x)

    def _read(self):
        if x == 1:
            x = DataFoo(9)
        self.data.append(x)
    """

    EXPECTED_FINDS = [ "_read", "find1", "find4", "find5", "find9" ]

    def test_finds(self):
        finder = FieldAssignmentFinder()
        finder.from_source_str(self.FINDER_INPUT_SOURCE)

        try:
            matches = sorted(list(finder.matches["Foo"]))
            self.assertEqual(
                len(matches), len(self.EXPECTED_FINDS), "Number of assignments found."
            )
            for i in range(len(matches)):
                self.assertEqual(
                    matches[i].func,
                    self.EXPECTED_FINDS[i],
                    f"Found func name #{i}.",
                )
        except AssertionError as e:
            pp(finder.matches, width=200)
            raise e

    EXPECTED_FINDS_PTRS = {
        "Ptrs": [
            "header_field1",
            "header_field2",
            "header_field3_u8x4",
            "_m_footer",
            "_m_ref_header_field2",
        ],
        "BodyU16": ["u16"],
        "BodyU16ptr16": ["ptr16", "u16", "_m_ref_header_field2_ptr"],
        "BodyU8": ["u8"],
    }

    def test_finds_ptrs(self):
        finder = FieldAssignmentFinder()
        with open("./kaitai/ptrs.py", "r") as f:
            finder.from_source_str(f.read())

        try:
            self.assertEqual(
                len(finder.matches.keys()), len(self.EXPECTED_FINDS_PTRS.keys()), "Number of types found."
            )
            for k in finder.matches.keys():
                self.assertEqual(
                    len(finder.matches[k]),
                    len(self.EXPECTED_FINDS_PTRS[k]),
                    f"Number of assingments in type '{k}'.",
                )
                for i, a in enumerate(sorted(list(finder.matches[k]))):
                    self.assertEqual(
                        a.lhs,
                        self.EXPECTED_FINDS_PTRS[k][i],
                        f"Field name of assignment #{i} in type '{k}'.",
                    )
        except AssertionError as e:
            pp(finder.matches, width=200)
            raise e


if __name__ == "__main__":
    unittest.main()
