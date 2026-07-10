# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import KaitaiStruct, KaitaiStream, BytesIO
import collections


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class Ptrs(KaitaiStruct):
    SEQ_FIELDS = ["header_field1", "header_field2", "header_field3_u8x4"]
    def __init__(self, _io, _parent=None, _root=None):
        super(Ptrs, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self
        self._debug = collections.defaultdict(dict)

    def _read(self):
        self._debug['header_field1']['start'] = self._io.pos()
        self.header_field1 = self._io.read_u2le()
        self._debug['header_field1']['end'] = self._io.pos()
        self._debug['header_field2']['start'] = self._io.pos()
        self.header_field2 = self._io.read_u2le()
        self._debug['header_field2']['end'] = self._io.pos()
        self._debug['header_field3_u8x4']['start'] = self._io.pos()
        self._debug['header_field3_u8x4']['arr'] = []
        self.header_field3_u8x4 = []
        for i in range(4):
            self._debug['header_field3_u8x4']['arr'].append({'start': self._io.pos()})
            _t_header_field3_u8x4 = Ptrs.BodyU8(self._io, self, self._root)
            try:
                _t_header_field3_u8x4._read()
            finally:
                self.header_field3_u8x4.append(_t_header_field3_u8x4)
            self._debug['header_field3_u8x4']['arr'][i]['end'] = self._io.pos()

        self._debug['header_field3_u8x4']['end'] = self._io.pos()


    def _fetch_instances(self):
        pass
        for i in range(len(self.header_field3_u8x4)):
            pass
            self.header_field3_u8x4[i]._fetch_instances()

        _ = self.footer
        if hasattr(self, '_m_footer'):
            pass

        _ = self.ref_header_field2
        if hasattr(self, '_m_ref_header_field2'):
            pass
            self._m_ref_header_field2._fetch_instances()


    class BodyU16(KaitaiStruct):
        SEQ_FIELDS = ["u16"]
        def __init__(self, _io, _parent=None, _root=None):
            super(Ptrs.BodyU16, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._debug = collections.defaultdict(dict)

        def _read(self):
            self._debug['u16']['start'] = self._io.pos()
            self.u16 = self._io.read_u2le()
            self._debug['u16']['end'] = self._io.pos()


        def _fetch_instances(self):
            pass


    class BodyU16ptr16(KaitaiStruct):
        SEQ_FIELDS = ["u16", "ptr16"]
        def __init__(self, _io, _parent=None, _root=None):
            super(Ptrs.BodyU16ptr16, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._debug = collections.defaultdict(dict)

        def _read(self):
            self._debug['u16']['start'] = self._io.pos()
            self.u16 = self._io.read_u2le()
            self._debug['u16']['end'] = self._io.pos()
            self._debug['ptr16']['start'] = self._io.pos()
            self.ptr16 = self._io.read_u2le()
            self._debug['ptr16']['end'] = self._io.pos()


        def _fetch_instances(self):
            pass
            _ = self.ref_header_field2_ptr
            if hasattr(self, '_m_ref_header_field2_ptr'):
                pass
                self._m_ref_header_field2_ptr._fetch_instances()


        @property
        def ref_header_field2_ptr(self):
            if hasattr(self, '_m_ref_header_field2_ptr'):
                return self._m_ref_header_field2_ptr

            io = self._root.ref_header_field2._io
            _pos = io.pos()
            io.seek(self.ptr16)
            self._debug['_m_ref_header_field2_ptr']['start'] = io.pos()
            self._m_ref_header_field2_ptr = Ptrs.BodyU16(io, self, self._root)
            self._m_ref_header_field2_ptr._read()
            self._debug['_m_ref_header_field2_ptr']['end'] = io.pos()
            io.seek(_pos)
            return getattr(self, '_m_ref_header_field2_ptr', None)


    class BodyU8(KaitaiStruct):
        SEQ_FIELDS = ["u8"]
        def __init__(self, _io, _parent=None, _root=None):
            super(Ptrs.BodyU8, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._debug = collections.defaultdict(dict)

        def _read(self):
            self._debug['u8']['start'] = self._io.pos()
            self.u8 = self._io.read_u1()
            self._debug['u8']['end'] = self._io.pos()


        def _fetch_instances(self):
            pass


    @property
    def footer(self):
        if hasattr(self, '_m_footer'):
            return self._m_footer

        _pos = self._io.pos()
        self._io.seek(self._io.size() - 2)
        self._debug['_m_footer']['start'] = self._io.pos()
        self._m_footer = self._io.read_u2le()
        self._debug['_m_footer']['end'] = self._io.pos()
        self._io.seek(_pos)
        return getattr(self, '_m_footer', None)

    @property
    def ref_header_field2(self):
        if hasattr(self, '_m_ref_header_field2'):
            return self._m_ref_header_field2

        _pos = self._io.pos()
        self._io.seek(self.header_field2)
        self._debug['_m_ref_header_field2']['start'] = self._io.pos()
        self._m_ref_header_field2 = Ptrs.BodyU16ptr16(self._io, self, self._root)
        self._m_ref_header_field2._read()
        self._debug['_m_ref_header_field2']['end'] = self._io.pos()
        self._io.seek(_pos)
        return getattr(self, '_m_ref_header_field2', None)


