import logging
import sys

from isa import mnemonics, opcode_names, opcodes


class AssemblerState:
    def __init__(self):
        self.current_address = 0
        self.sections = []
        self.labels = {}

    def current_section(self):
        assert self.sections, "No active section — use .text or .data first"
        return self.sections[-1]

    def in_data_section(self):
        return self.sections and self.sections[-1]["name"] == "data"

    def in_text_section(self):
        return self.sections and self.sections[-1]["name"] == "text"


def get_meaningful_token(line):
    return line.split(";", 1)[0].strip()


def translate_to_token_list(text):
    tokens = []
    for line in text.splitlines():
        token = get_meaningful_token(line)
        if token:
            tokens.append(token)
    return tokens


def read_file(filename):
    assert filename.endswith(".s")
    with open(filename) as f:
        return f.read()


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


def _process_byte(args, state):
    args = args.strip()
    if (args.startswith('"') and args.endswith('"')) or (args.startswith("'") and args.endswith("'")):
        for ch in args[1:-1]:
            state.current_section()["content"].append(
                {"type": "byte", "value": ord(ch), "address": state.current_address}
            )
            state.current_section()["size"] += 1
            state.current_address += 1
    else:
        value = parse_value(args)
        assert -0x80 <= value <= 0xFF, f"Value out of byte range: {value}"
        state.current_section()["content"].append(
            {"type": "byte", "value": value & 0xFF, "address": state.current_address}
        )
        state.current_section()["size"] += 1
        state.current_address += 1


def first_pass(tokens):
    state = AssemblerState()

    for token in tokens:
        label, operation = parse_line(token)

        if label is not None:
            assert label not in state.labels, f"Duplicate label: {label}"
            state.labels[label] = state.current_address

        classified = classify_operation(operation)

        if classified is None:
            continue
        if classified[0] == "directive":
            _, name, args = classified
            process_directive(name, args, state)
        else:
            _, instr_token = classified
            process_instruction(instr_token, state)
            state.current_section()["size"] += 4
            state.current_address += 4

    return state


def classify_operation(operation):
    if operation is None:
        return None
    if operation.startswith("."):
        parts = operation.split(None, 1)
        name = parts[0]
        args = parts[1].strip() if len(parts) > 1 else None
        return ("directive", name, args)
    return ("instruction", operation)


def process_directive(name, args, state):
    match name:
        case ".text":
            state.sections.append({"name": "text", "start_address": state.current_address, "size": 0, "content": []})

        case ".data":
            state.sections.append({"name": "data", "start_address": state.current_address, "size": 0, "content": []})

        case ".org":
            addr = parse_value(args)
            assert 0 <= addr <= 0x7FFFFF, f"Address out of range: {addr:#x}"
            state.current_address = addr
            state.current_section()["start_address"] = addr

        case ".word":
            assert state.in_data_section(), ".word only allowed in .data section"
            value = parse_value(args)
            assert fits_int32(value), f"Value out of int32 range: {value}"
            state.current_section()["content"].append(
                {"type": "word", "value": value, "address": state.current_address}
            )
            state.current_section()["size"] += 4
            state.current_address += 4

        case ".byte":
            assert state.in_data_section(), ".byte only allowed in .data section"
            _process_byte(args, state)

        case _:
            raise ValueError(f"Unknown directive: {name}")


def process_instruction(instr_token, state):
    assert state.in_text_section(), f"Instructions only allowed in .text section: {instr_token}"
    if len(instr_token.split(None, 1)) == 1:
        operation = instr_token.strip()
        argument = None
    else:
        operation, argument = instr_token.split(None, 1)
    state.current_section()["content"].append({"type": operation, "value": argument, "address": state.current_address})


def second_pass(state):
    for section in state.sections:
        if section["name"] == "text":
            for instr in section["content"]:
                if instr["value"] is not None:
                    value = instr["value"].strip()
                    if value.startswith("#"):
                        addressing_mode = "immediate"
                        operand = value[1:].strip()
                    elif value.startswith("$"):
                        addressing_mode = "absolute"
                        operand = value[1:].strip()
                    elif value.startswith("(") and value.endswith(")"):
                        addressing_mode = "indirect"
                        operand = value[1:-1].strip()
                    else:
                        addressing_mode = "relative"
                        operand = value

                    if operand in state.labels:
                        operand_value = state.labels[operand]
                        if addressing_mode == "relative":
                            operand_value -= instr["address"] + 4
                    else:
                        operand_value = parse_value(operand)
                    try:
                        instr["value"] = operand_value
                        instr["encoded"] = opcodes[instr["type"] + "_" + addressing_mode] << 23 | (
                            operand_value & 0x7FFFFF
                        )
                    except KeyError:
                        raise ValueError(
                            f"Unknown instruction or addressing mode: {instr['type']} with operand {value}"
                        )
                else:
                    try:
                        instr["encoded"] = opcodes[instr["type"]] << 23
                    except KeyError:
                        raise ValueError(f"Unknown instruction: {instr['type']}")
                logging.debug(f"Encoded instruction at address {instr['address']:#x}: {instr['encoded']:#010x}")
    return state


def write_output(state, target):
    with open(target, "wb") as f:
        f.write(0x600DCAFE.to_bytes(4, byteorder="big", signed=False))  # magic number
        f.write(state.labels["_start"].to_bytes(4, byteorder="big", signed=False))  # entry point
        for section in state.sections:
            f.write(section["start_address"].to_bytes(4, byteorder="big", signed=False))
            f.write(section["size"].to_bytes(4, byteorder="big", signed=False))
        f.write(0xBAADCAFE.to_bytes(4, byteorder="big", signed=False))  # section header end marker

        for section in state.sections:
            if section["name"] == "text":
                for instr in section["content"]:
                    logging.debug(f"Writing encoded instruction: {instr['encoded']}")
                    f.write(instr["encoded"].to_bytes(4, byteorder="big", signed=False))
            elif section["name"] == "data":
                for item in section["content"]:
                    if item["type"] == "word":
                        logging.debug(f"Writing word: {item['value']} at address {item['address']:#x}")
                        f.write(item["value"].to_bytes(4, byteorder="big", signed=True))
                    elif item["type"] == "byte":
                        logging.debug(f"Writing byte: {item['value']} at address {item['address']:#x}")
                        f.write(item["value"].to_bytes(1, byteorder="big", signed=True))


def write_debug_file(filename, state):
    lines = []
    max_addr = len("<address>")
    max_hex = len("<hex_code>")
    max_mnemonic = len("<mnemonic>")

    for section in state.sections:
        if section["name"] == "text":
            for instr in section["content"]:
                address = instr["address"]
                hex_code = f"{instr['encoded']:#010x}"
                mnemonic = f"{instr['type']}: {mnemonics[opcode_names[instr['encoded'] >> 23 & 0x1FF]](instr['value'])}"

                lines.append((address, hex_code, mnemonic))
                max_addr = max(max_addr, len(str(address)))
                max_hex = max(max_hex, len(hex_code))
                max_mnemonic = max(max_mnemonic, len(mnemonic))

    with open(filename, "w") as f:
        header = f"{'<address>':<{max_addr}} | {'<hex_code>':<{max_hex}} | {'<mnemonic>':<{max_mnemonic}}"
        f.write(header + "\n")

        for address, hex_code, mnemonic in lines:
            line = f"{address:<{max_addr}} | {hex_code:<{max_hex}} | {mnemonic:<{max_mnemonic}}"
            f.write(line + "\n")


def main(source, target, debug=False):
    text = read_file(source)
    tokens = translate_to_token_list(text)
    state = first_pass(tokens)
    state = second_pass(state)
    if debug:
        write_debug_file("translator.debug", state)
    write_output(state, target)


if __name__ == "__main__":
    assert len(sys.argv) >= 3, "Wrong arguments: translator.py <input_file> <target_file>"
    if len(sys.argv) > 3 and sys.argv[3] == "--debug":
        main(sys.argv[1], sys.argv[2], True)
    else:
        main(sys.argv[1], sys.argv[2])
