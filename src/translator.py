import logging
import sys

from isa import mnemonics, opcode_names, opcodes


def ir_label(name):
    return {"kind": "label", "name": name}


def ir_org(value):
    return {"kind": "org", "value": value}


def ir_instr(type_, value=None):
    return {"kind": "instr", "type": type_, "value": value}


def ir_word(value):
    return {"kind": "word", "value": value}


def ir_byte(value):
    return {"kind": "byte", "value": value}


class ParseState:
    def __init__(self):
        self.sections = []

    def current_section(self):
        assert self.sections, "No active section — use .text or .data first"
        return self.sections[-1]

    def in_data_section(self):
        return self.sections and self.sections[-1]["name"] == "data"

    def in_text_section(self):
        return self.sections and self.sections[-1]["name"] == "text"


def read_file(filename):
    assert filename.endswith(".s")
    with open(filename) as f:
        return f.read()


def get_meaningful_token(line):
    return line.split(";", 1)[0].strip()


def tokenize(text):
    return [t for line in text.splitlines() if (t := get_meaningful_token(line))]


def parse_line(token):
    parts = token.split(None, 1)
    if parts[0].endswith(":"):
        label = parts[0][:-1]
        operation = parts[1].strip() if len(parts) > 1 else None
        return label, operation
    return None, token


def parse_value(s):
    s = s.strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s)


def fits_int32(v):
    return -0x80000000 <= v <= 0xFFFFFFFF


def _parse_byte_args(args):
    args = args.strip()
    if (args.startswith('"') and args.endswith('"')) or (args.startswith("'") and args.endswith("'")):
        return [ir_byte(ord(ch)) for ch in args[1:-1]]
    value = parse_value(args)
    assert -0x80 <= value <= 0xFF, f"Value out of byte range: {value}"
    return [ir_byte(value & 0xFF)]


def _parse_directive(name, args, state):
    match name:
        case ".text":
            state.sections.append({"name": "text", "content": []})
        case ".data":
            state.sections.append({"name": "data", "content": []})
        case ".org":
            addr = parse_value(args)
            assert 0 <= addr <= 0x7FFFFF, f"Address out of range: {addr:#x}"
            state.current_section()["content"].append(ir_org(addr))
        case ".word":
            assert state.in_data_section(), ".word only allowed in .data section"
            value = parse_value(args)
            assert fits_int32(value), f"Value out of int32 range: {value}"
            state.current_section()["content"].append(ir_word(value))
        case ".byte":
            assert state.in_data_section(), ".byte only allowed in .data section"
            for node in _parse_byte_args(args):
                state.current_section()["content"].append(node)
        case _:
            raise ValueError(f"Unknown directive: {name}")


def parse(tokens):
    state = ParseState()
    for token in tokens:
        label, operation = parse_line(token)

        if label is not None:
            assert state.sections, f"Label '{label}' defined before any section"
            state.current_section()["content"].append(ir_label(label))

        if operation is None:
            continue

        if operation.startswith("."):
            parts = operation.split(None, 1)
            name = parts[0]
            args = parts[1].strip() if len(parts) > 1 else None
            _parse_directive(name, args, state)
        else:
            assert state.in_text_section(), f"Instructions only allowed in .text section: {operation}"
            parts = operation.split(None, 1)
            type_ = parts[0]
            value = parts[1].strip() if len(parts) > 1 else None
            state.current_section()["content"].append(ir_instr(type_, value))

    return state


_SAFE_OPS = {
    "nop": None,
    "clr": None,
    "not": None,
    "inc": None,
    "dec": None,
    "ld.w": {"immediate", "relative", "absolute"},
    "ld.b": {"immediate", "relative", "absolute"},
    "st.w": {"relative", "absolute"},
    "st.b": {"relative", "absolute"},
    "add": {"immediate", "relative", "absolute"},
    "sub": {"immediate", "relative", "absolute"},
    "and": {"immediate", "relative", "absolute"},
    "or": {"immediate", "relative", "absolute"},
    "mul": {"immediate", "relative", "absolute"},
    "in": {"absolute"},
    "out": {"absolute"},
}

_UNSAFE_OPS = {
    "halt",
    "jmp",
    "bzs",
    "bzns",
    "bcs",
    "bcns",
    "bvs",
    "bvns",
    "bns",
    "bnns",
    "swp",
    "flsh.ww",
    "flsh.bb",
    "flsh.wb",
    "flsh.bw",
}


def _label_operand(value):
    if value is None:
        return None
    v = value.strip()
    if v.startswith("$"):
        rest = v[1:].strip()
        if rest.isidentifier():
            return rest, "absolute"
        return None
    if v.startswith(("#", "(")):
        return None
    if v.isidentifier():
        return v, "relative"
    return None


def _operand_mode(value):
    if value is None:
        return None
    v = value.strip()
    if v.startswith("#"):
        return "immediate"
    if v.startswith("$"):
        return "absolute"
    if v.startswith("("):
        return "indirect"
    return "relative"


def _st_size(type_):
    return type_.split(".")[1]


def _is_safe_in_window(node, label_x):  # noqa: C901
    if node["kind"] != "instr":
        return False
    t = node["type"]
    if t in _UNSAFE_OPS:
        return False
    mode = _operand_mode(node["value"])
    if t not in _SAFE_OPS:
        return False  # assume any unknown instruction is unsafe
    allowed = _SAFE_OPS[t]
    if allowed is None:
        return True  # no-operand instruction
    if mode not in allowed:
        return False
    # store to label_x inside window aliases with shadow_ar
    if t in ("st.w", "st.b"):
        lk = _label_operand(node["value"])
        if lk is not None and lk[0] == label_x:
            return False
    return True


def _next_instr_index(nodes, start):
    for k in range(start, len(nodes)):
        if nodes[k]["kind"] == "label":
            return None  # branch target risk
        if nodes[k]["kind"] == "instr":
            return k
    return None


def _optimize_section(nodes):  # noqa: C901
    i = 0
    while i < len(nodes):
        # Gate 1: must be st.w or st.b with a label operand
        if nodes[i]["kind"] != "instr" or nodes[i]["type"] not in ("st.w", "st.b"):
            i += 1
            continue
        lx = _label_operand(nodes[i]["value"])
        if lx is None:
            i += 1
            continue
        label_x = lx[0]
        size_x = _st_size(nodes[i]["type"])
        st1_value = nodes[i]["value"]  # preserve operand string for swp

        # Gate 2: next instr (no label nodes allowed between) must be ld.w/ld.b
        # with a label operand.
        j = _next_instr_index(nodes, i + 1)
        if j is None:
            i += 1
            continue
        if nodes[j]["type"] not in ("ld.w", "ld.b"):
            i += 1
            continue
        ly = _label_operand(nodes[j]["value"])
        if ly is None:
            i += 1
            continue
        label_y = ly[0]

        # Gate 3: labels must be textually distinct
        if label_x == label_y:
            i += 1
            continue

        current_x = label_x
        current_y = label_y
        shadow_size = size_x  # size of what is currently in shadow_acc
        scan_from = j + 1
        pending = [(i, "swp", st1_value)]
        committed = False
        last_ping = None
        while True:
            # Scan for closing st.current_y
            found_close = None
            safe = True

            for k in range(scan_from, len(nodes)):
                n = nodes[k]

                if n["kind"] == "label":
                    safe = False  # potential branch target inside window
                    break
                if n["kind"] != "instr":
                    continue

                if n["type"] in ("st.w", "st.b"):
                    lk = _label_operand(n["value"])
                    if lk is not None and lk[0] == current_y:
                        found_close = (k, _st_size(n["type"]), n["value"])
                        break

                if not _is_safe_in_window(n, current_x):
                    safe = False
                    break

            if not safe or found_close is None:
                break

            k, close_size, close_value = found_close

            kk = _next_instr_index(nodes, k + 1)
            if kk is not None and nodes[kk]["type"] in ("ld.w", "ld.b"):
                lkk = _label_operand(nodes[kk]["value"])

                # If the next instruction is a load from current_y, we have a ping-pong pattern:
                # ld a; st a; ld b; st b; ld a ...
                if lkk is not None and lkk[0] == current_x:
                    logging.debug(
                        f"optimize: ping-pong [{k}] {nodes[k]['type']} {current_y} "
                        f"-> swp,  [{kk}] {nodes[kk]['type']} {current_x} -> nop"
                    )
                    pending.append((k, "swp", close_value))
                    pending.append((kk, "nop", None))
                    last_ping = {
                        "k": k,
                        "kk": kk,
                        "shadow_size": shadow_size,
                        "pos_k": len(pending) - 2,
                        "pos_kk": len(pending) - 1,
                        "current_x": current_x,
                        "current_y": current_y,
                    }
                    current_x, current_y = current_y, current_x
                    shadow_size = close_size
                    scan_from = kk + 1
                    continue

            # No ping-pong. Commit a flsh to persist the values.
            flsh_type = f"flsh.{shadow_size}{close_size}"
            logging.debug(
                f"optimize: [{i}] {nodes[i]['type']} {label_x}  "
                f"[{k}] {nodes[k]['type']} {current_y}  ->  swp + {flsh_type}"
            )
            pending.append((k, flsh_type, close_value))
            committed = True
            break
        # if earlier we found the ping-pong pattern and didn`t close it, we can still persist with the last pong in the sequence.
        if last_ping is not None and not committed:
            k = last_ping["k"]
            kk = last_ping["kk"]

            st = nodes[k]
            ld = nodes[kk]

            close_size = _st_size(st["type"])
            shadow_size = last_ping["shadow_size"]

            flsh_type = f"flsh.{shadow_size}{close_size}"
            close_value = st["value"]

            pending[last_ping["pos_k"]] = (k, flsh_type, close_value)
            pending[last_ping["pos_kk"]] = (kk, ld["type"], ld["value"])

            committed = True

        if committed:
            for idx, new_type, new_value in pending:
                nodes[idx] = ir_instr(new_type, new_value)
            i = max(idx for idx, _, _ in pending) + 1

        else:
            i += 1


def optimize(parse_state):
    for section in parse_state.sections:
        if section["name"] == "text":
            _optimize_section(section["content"])
            instrs = []
            for elem in section["content"]:
                if (elem["kind"] == "instr" and elem["type"] != "nop") or elem["kind"] != "instr":
                    instrs.append(elem)
            section["content"] = instrs
    return parse_state


class LayoutState:
    def __init__(self, sections, labels):
        self.sections = sections
        self.labels = labels


def layout(parse_state):
    labels = {}
    laid_out_sections = []
    current_address = 0

    for section in parse_state.sections:
        sec = {
            "name": section["name"],
            "start_address": current_address,
            "size": 0,
            "content": [],
        }

        for node in section["content"]:
            if node["kind"] == "org":
                current_address = node["value"]
                sec["start_address"] = current_address
                continue

            if node["kind"] == "label":
                assert node["name"] not in labels, f"Duplicate label: {node['name']}"
                labels[node["name"]] = current_address
                continue

            laid_node = dict(node)
            laid_node["address"] = current_address
            sec["content"].append(laid_node)

            if node["kind"] in ("instr", "word"):
                current_address += 4
                sec["size"] += 4
            elif node["kind"] == "byte":
                current_address += 1
                sec["size"] += 1

        laid_out_sections.append(sec)

    return LayoutState(laid_out_sections, labels)


def encode(layout_state):  # noqa: C901
    labels = layout_state.labels

    for section in layout_state.sections:
        if section["name"] != "text":
            continue

        for instr in section["content"]:
            value = instr.get("value")

            if value is not None:
                v = value.strip()
                if v.startswith("#"):
                    mode, operand = "immediate", v[1:].strip()
                elif v.startswith("$"):
                    mode, operand = "absolute", v[1:].strip()
                elif v.startswith("(") and v.endswith(")"):
                    mode, operand = "indirect", v[1:-1].strip()
                else:
                    mode, operand = "relative", v

                if operand in labels:
                    operand_value = labels[operand]
                    if mode == "relative":
                        operand_value -= instr["address"] + 4
                else:
                    operand_value = parse_value(operand)

                instr["value"] = operand_value
                try:
                    instr["encoded"] = opcodes[instr["type"] + "_" + mode] << 23 | (operand_value & 0x7FFFFF)
                except KeyError as e:
                    raise ValueError(
                        f"Unknown instruction or addressing mode: " f"{instr['type']} with operand {value}"
                    ) from e
            else:
                try:
                    instr["encoded"] = opcodes[instr["type"]] << 23
                except KeyError as e:
                    raise ValueError(f"Unknown instruction: {instr['type']}") from e

    return layout_state


def write_header(layout_state, f):
    assert "_start" in layout_state.labels, "No _start label defined"
    f.write(0x600DCAFE.to_bytes(4, byteorder="big", signed=False))
    f.write(layout_state.labels["_start"].to_bytes(4, byteorder="big", signed=False))
    for section in layout_state.sections:
        f.write(section["start_address"].to_bytes(4, byteorder="big", signed=False))
        f.write(section["size"].to_bytes(4, byteorder="big", signed=False))
    f.write(0xBAADCAFE.to_bytes(4, byteorder="big", signed=False))


def write_text_section(section, f):
    for instr in section["content"]:
        logging.debug(f"Writing encoded instruction: {instr['encoded']:#010x}")
        f.write(instr["encoded"].to_bytes(4, byteorder="big", signed=False))


def write_data_section(section, f):
    for item in section["content"]:
        if item["kind"] == "word":
            f.write(item["value"].to_bytes(4, byteorder="big", signed=True))
        elif item["kind"] == "byte":
            f.write(item["value"].to_bytes(1, byteorder="big", signed=True))


def write_output(layout_state, target):
    with open(target, "wb") as f:
        write_header(layout_state, f)
        for section in layout_state.sections:
            if section["name"] == "text":
                write_text_section(section, f)
            elif section["name"] == "data":
                write_data_section(section, f)


def write_debug_file(filename, layout_state):
    lines = []
    max_addr = len("<address>")
    max_hex = len("<hex_code>")
    max_mnemonic = len("<mnemonic>")

    for section in layout_state.sections:
        if section["name"] != "text":
            continue
        for instr in section["content"]:
            address = instr["address"]
            hex_code = f"{instr['encoded']:#010x}"
            mnemonic = f"{instr['type']}: " f"{mnemonics[opcode_names[instr['encoded'] >> 23 & 0x1FF]](instr['value'])}"
            lines.append((address, hex_code, mnemonic))
            max_addr = max(max_addr, len(str(address)))
            max_hex = max(max_hex, len(hex_code))
            max_mnemonic = max(max_mnemonic, len(mnemonic))

    with open(filename, "w") as f:
        f.write(f"{'<address>':<{max_addr}} | {'<hex_code>':<{max_hex}} | " f"{'<mnemonic>':<{max_mnemonic}}\n")
        for address, hex_code, mnemonic in lines:
            f.write(f"{address:<{max_addr}} | {hex_code:<{max_hex}} | {mnemonic:<{max_mnemonic}}\n")


def main(source, target, debug="", optimize_shadows=False):
    text = read_file(source)
    tokens = tokenize(text)
    parse_state = parse(tokens)
    if optimize_shadows:
        optimize(parse_state)
    layout_state = layout(parse_state)
    encode(layout_state)
    if debug:
        write_debug_file(debug, layout_state)
    write_output(layout_state, target)


if __name__ == "__main__":
    assert len(sys.argv) >= 3, (
        "Wrong arguments: translator.py <input_file> <target_file> " "[--debug=<debug_file>] [--optimize]"
    )
    _debug = ""
    _optimize = False
    for _arg in sys.argv[3:]:
        if _arg.startswith("--debug="):
            _debug = _arg.split("=")[1]
        elif _arg == "--optimize":
            _optimize = True
    main(sys.argv[1], sys.argv[2], _debug, _optimize)
