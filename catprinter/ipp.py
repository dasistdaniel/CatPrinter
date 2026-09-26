"""Minimaler IPP-Codec (RFC 8010): Nachrichten lesen und schreiben.

Ein Attribut ist ein Tupel (name, tag, [werte]). Werte von Collections sind
selbst Listen von Attributen.
"""
import struct

# Gruppen-Tags
OPERATION = 0x01
JOB = 0x02
END = 0x03
PRINTER = 0x04
UNSUPPORTED_GROUP = 0x05

# Werte-Tags
UNSUPPORTED = 0x10
UNKNOWN = 0x12
NO_VALUE = 0x13
INTEGER = 0x21
BOOLEAN = 0x22
ENUM = 0x23
OCTET_STRING = 0x30
DATETIME = 0x31
RESOLUTION = 0x32
RANGE = 0x33
BEGIN_COLLECTION = 0x34
TEXT_LANG = 0x35
NAME_LANG = 0x36
END_COLLECTION = 0x37
TEXT = 0x41
NAME = 0x42
KEYWORD = 0x44
URI = 0x45
URI_SCHEME = 0x46
CHARSET = 0x47
LANGUAGE = 0x48
MIME = 0x49
MEMBER_NAME = 0x4A

# Operationen
PRINT_JOB = 0x0002
VALIDATE_JOB = 0x0004
CREATE_JOB = 0x0005
SEND_DOCUMENT = 0x0006
CANCEL_JOB = 0x0008
GET_JOB_ATTRIBUTES = 0x0009
GET_JOBS = 0x000A
GET_PRINTER_ATTRIBUTES = 0x000B
CLOSE_JOB = 0x003B
IDENTIFY_PRINTER = 0x003C

OPERATION_NAMES = {
    PRINT_JOB: "Print-Job", VALIDATE_JOB: "Validate-Job", CREATE_JOB: "Create-Job",
    SEND_DOCUMENT: "Send-Document", CANCEL_JOB: "Cancel-Job",
    GET_JOB_ATTRIBUTES: "Get-Job-Attributes", GET_JOBS: "Get-Jobs",
    GET_PRINTER_ATTRIBUTES: "Get-Printer-Attributes", CLOSE_JOB: "Close-Job",
    IDENTIFY_PRINTER: "Identify-Printer",
}

# Statuscodes
OK = 0x0000
OK_IGNORED = 0x0001
BAD_REQUEST = 0x0400
NOT_FOUND = 0x0406
NOT_POSSIBLE = 0x0404
DOCUMENT_FORMAT_NOT_SUPPORTED = 0x040A
OPERATION_NOT_SUPPORTED = 0x0501
INTERNAL_ERROR = 0x0500

_INT_TAGS = (INTEGER, ENUM)
_STR_TAGS = (TEXT, NAME, KEYWORD, URI, URI_SCHEME, CHARSET, LANGUAGE, MIME, MEMBER_NAME)


class Message:
    def __init__(self, version=(2, 0), code=0, request_id=0, groups=None):
        self.version = version
        self.code = code  # Operation (Anfrage) oder Statuscode (Antwort)
        self.request_id = request_id
        self.groups = groups if groups is not None else []  # [(group_tag, [attr])]

    def group(self, tag):
        for gtag, attrs in self.groups:
            if gtag == tag:
                return attrs
        return []

    def get(self, name, group=None, default=None):
        """Erster Wert eines Attributs, optional nur in einer Gruppe."""
        for gtag, attrs in self.groups:
            if group is not None and gtag != group:
                continue
            for aname, _tag, values in attrs:
                if aname == name and values:
                    return values[0]
        return default

    def get_all(self, name, group=None):
        for gtag, attrs in self.groups:
            if group is not None and gtag != group:
                continue
            for aname, _tag, values in attrs:
                if aname == name:
                    return values
        return []

    def add_group(self, tag, attrs):
        self.groups.append((tag, attrs))


# ---------------------------------------------------------------- Dekodieren

def _decode_value(tag, raw):
    if tag in _INT_TAGS:
        return struct.unpack(">i", raw)[0]
    if tag == BOOLEAN:
        return raw != b"\x00"
    if tag == RANGE:
        return struct.unpack(">ii", raw)
    if tag == RESOLUTION:
        return struct.unpack(">iib", raw)
    if tag in _STR_TAGS:
        return raw.decode("utf-8", "replace")
    if tag in (TEXT_LANG, NAME_LANG):
        lang_len = struct.unpack(">H", raw[:2])[0]
        text_len = struct.unpack(">H", raw[2 + lang_len:4 + lang_len])[0]
        return raw[4 + lang_len:4 + lang_len + text_len].decode("utf-8", "replace")
    return raw


def decode(data):
    """Dekodiert eine IPP-Nachricht. Gibt (Message, Dokumentdaten) zurück."""
    if len(data) < 9:
        raise ValueError("IPP-Nachricht zu kurz")
    major, minor, code, request_id = struct.unpack(">BBHI", data[:8])
    msg = Message((major, minor), code, request_id)
    pos = 8
    attrs = None
    # Stapel für verschachtelte Collections: (Liste der Mitglieder, aktuelles Mitglied)
    stack = []
    last = None  # zuletzt gelesenes Attribut (für Zusatzwerte)

    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == END:
            return msg, data[pos:]
        if tag < 0x10:  # Gruppen-Begrenzer
            attrs = []
            msg.add_group(tag, attrs)
            last = None
            continue
        name_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        name = data[pos:pos + name_len].decode("utf-8", "replace")
        pos += name_len
        value_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        raw = data[pos:pos + value_len]
        pos += value_len

        if stack:
            members, current = stack[-1]
            if tag == END_COLLECTION:
                stack.pop()
                continue
            if tag == MEMBER_NAME:
                current = [raw.decode("utf-8", "replace"), None, []]
                members.append(current)
                stack[-1] = (members, current)
                continue
            if tag == BEGIN_COLLECTION:
                sub = []
                current[1] = tag
                current[2].append(sub)
                stack.append((sub, None))
                continue
            current[1] = tag
            current[2].append(_decode_value(tag, raw))
            continue

        if attrs is None:
            raise ValueError("Attribut außerhalb einer Gruppe")
        if tag == BEGIN_COLLECTION:
            sub = []
            if name:
                last = [name, tag, [sub]]
                attrs.append(last)
            elif last is not None:
                last[2].append(sub)
            stack.append((sub, None))
            continue
        value = _decode_value(tag, raw)
        if name:
            last = [name, tag, [value]]
            attrs.append(last)
        elif last is not None:
            last[2].append(value)
    raise ValueError("IPP-Nachricht ohne End-Tag")


# ---------------------------------------------------------------- Kodieren

def _encode_value(tag, value):
    if tag in _INT_TAGS:
        return struct.pack(">i", value)
    if tag == BOOLEAN:
        return b"\x01" if value else b"\x00"
    if tag == RANGE:
        return struct.pack(">ii", *value)
    if tag == RESOLUTION:
        return struct.pack(">iib", *value)
    if tag in (NO_VALUE, UNSUPPORTED, UNKNOWN):
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _encode_attr(out, name, tag, values, member=False):
    for i, value in enumerate(values):
        attr_name = b"" if (member or i > 0) else name.encode("utf-8")
        if tag == BEGIN_COLLECTION:
            out += struct.pack(">BH", BEGIN_COLLECTION, len(attr_name)) + attr_name + b"\x00\x00"
            for mname, mtag, mvalues in value:
                mb = mname.encode("utf-8")
                out += struct.pack(">BHH", MEMBER_NAME, 0, len(mb)) + mb
                _encode_attr(out, mname, mtag, mvalues, member=True)
            out += struct.pack(">BHH", END_COLLECTION, 0, 0)
        else:
            raw = _encode_value(tag, value)
            out += struct.pack(">BH", tag, len(attr_name)) + attr_name
            out += struct.pack(">H", len(raw)) + raw


def encode(msg):
    out = bytearray(struct.pack(">BBHI", msg.version[0], msg.version[1], msg.code, msg.request_id))
    for gtag, attrs in msg.groups:
        out.append(gtag)
        for name, tag, values in attrs:
            _encode_attr(out, name, tag, values)
    out.append(END)
    return bytes(out)


def describe(msg):
    """Lesbare Kurzfassung einer Nachricht fürs Log."""
    lines = []
    for gtag, attrs in msg.groups:
        lines.append(f"  [Gruppe 0x{gtag:02x}]")
        for name, tag, values in attrs:
            shown = ", ".join(_short(v) for v in values)
            lines.append(f"    {name} (0x{tag:02x}) = {shown}")
    return "\n".join(lines)


def _short(value):
    if isinstance(value, list):
        return "{" + "; ".join(f"{n}={','.join(_short(v) for v in vs)}" for n, _t, vs in value) + "}"
    if isinstance(value, bytes):
        return value[:32].hex()
    return str(value)
