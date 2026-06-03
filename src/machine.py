import logging
import re
import struct
import sys

import yaml

from isa import opcode_names, opcodes


def disassemble_at(datapath, addr):
    word = (
        (datapath.memory[addr] << 24)
        | (datapath.memory[addr + 1] << 16)
        | (datapath.memory[addr + 2] << 8)
        | datapath.memory[addr + 3]
    )
    opcode = (word >> 23) & 0x1FF
    operand = word & 0x7FFFFF
    name = opcode_names.get(opcode, f"UNKNOWN({opcode})")
    msg = f"  [{addr:#06x}] {word:#010x}  {name}  operand={operand:#x}"
    if "relative" in name:
        if operand & 0x400000:
            operand = operand - 0x800000
        addr = operand + datapath.pc
        val = (
            (datapath.memory[addr] << 24)
            | (datapath.memory[addr + 1] << 16)
            | (datapath.memory[addr + 2] << 8)
            | datapath.memory[addr + 3]
        )
        msg += f"  mem(operand) = {val:#010x}"
    elif "absolute" in name:
        addr = operand
        val = (
            (datapath.memory[addr] << 24)
            | (datapath.memory[addr + 1] << 16)
            | (datapath.memory[addr + 2] << 8)
            | datapath.memory[addr + 3]
        )
        msg += f"  mem(operand) = {val:#010x}"
    elif "indirect" in name:
        addr = operand
        val = (
            (datapath.memory[addr] << 24)
            | (datapath.memory[addr + 1] << 16)
            | (datapath.memory[addr + 2] << 8)
            | datapath.memory[addr + 3]
        )
        msg += f"  mem(operand) = {val:#010x}"
        addr = val
        val = (
            (datapath.memory[addr] << 24)
            | (datapath.memory[addr + 1] << 16)
            | (datapath.memory[addr + 2] << 8)
            | datapath.memory[addr + 3]
        )
        msg += f"  mem(mem(operand)) = {val:#010x}"
    return msg


alu_ops = {
    "ADD": {
        "action": lambda self: self.ext_acc_mux_out + self.in_or_mem_mux_out,
        "bin": 0b0000,
        "desc": lambda op: f"acc + {op} -> acc",
    },
    "SUB": {
        "action": lambda self: self.ext_acc_mux_out - self.in_or_mem_mux_out,
        "bin": 0b0001,
        "desc": lambda op: f"acc - {op} -> acc",
    },
    "AND": {
        "action": lambda self: self.ext_acc_mux_out & self.in_or_mem_mux_out,
        "bin": 0b0010,
        "desc": lambda op: f"acc & {op} -> acc",
    },
    "OR": {
        "action": lambda self: self.ext_acc_mux_out | self.in_or_mem_mux_out,
        "bin": 0b0011,
        "desc": lambda op: f"acc | {op} -> acc",
    },
    "NOT": {"action": lambda self: ~self.ext_acc_mux_out, "bin": 0b0100, "desc": lambda op: "~acc -> acc"},
    "CLR": {"action": lambda self: 0, "bin": 0b0101, "desc": lambda op: "0 -> acc"},
    "INC": {"action": lambda self: self.ext_acc_mux_out + 1, "bin": 0b0110, "desc": lambda op: f"acc + {op} -> acc"},
    "DEC": {"action": lambda self: self.ext_acc_mux_out - 1, "bin": 0b0111, "desc": lambda op: f"acc - {op} -> acc"},
    "NEG": {"action": lambda self: -self.ext_acc_mux_out, "bin": 0b1000, "desc": lambda op: "-acc -> acc"},
    "LFT": {"action": lambda self: self.ext_acc_mux_out, "bin": 0b1001, "desc": lambda op: "acc -> acc"},
    "RGHT": {"action": lambda self: self.in_or_mem_mux_out, "bin": 0b1010, "desc": lambda op: f"{op} -> acc"},
    "MUL": {
        "action": lambda self: self.ext_acc_mux_out * self.in_or_mem_mux_out,
        "bin": 0b1011,
        "desc": lambda op: f"acc * {op} -> acc",
    },
}


class Datapath:
    # datapath elements
    acc = 0  # 32-bit GP register
    shadow_acc = 0  # 32-bit shadow register for acc

    ar = 0  # 23-bit address register
    shadow_ar = 0  # 23-bit shadow register for ar
    pc = 0  # 23-bit program counter

    dr = 0  # 32-bit data register, needed for instruction decoding and loading byte sized data from memory

    input_interface = None  # an address space of input devices abstraction
    output_interface = None  # an address space of output devices abstraction

    memory = None  # an array of bytes representing memory

    # service elements (not actually elements of the datapath, but used for convenience)

    # dr related
    ext_data_mux_out = 0

    dr_out = 0

    mem_out = 0

    # ar related
    rel_or_abs_mux_out = 0
    data_or_inst_mux_out = 0
    sh_ar_or_addr_mux_out = 0

    ar_out = 0
    shadow_ar_out = 0

    st_sh_mux_out = 0
    mem_in = 0

    # pc related
    next_or_offset_mux_out = 0

    pc_out = 0

    # left and right alu inputs
    ext_acc_mux_out = 0
    in_or_mem_mux_out = 0
    # acc related
    sa_or_alu_mux_out = 0

    acc_out = 0
    shadow_acc_out = 0

    # outputs of complex combinational logic
    add_pc_out = 0
    alu_out = 0

    # devices chosen by IO signals from devices address space
    input_device = None
    output_device = None

    input_out = 0

    def __init__(self, memory_size, input_interface, output_interface):
        """
        memory_size: size of memory in bytes
        input_interface: an array of device input buffers
        output_interface: an array of device output buffers
        """
        assert memory_size > 0, "Memory size must be greater than 0"
        assert memory_size <= 0x7FFFFF, "Memory size must be less than or equal to 0x7FFFFF to fit in the address space"
        self.memory = [0] * memory_size
        self.input_interface = input_interface
        self.output_interface = output_interface

    # DR signals
    def signal_latch_dr(self):
        self.dr = self.mem_out

    # IO signals
    # input addresses are capped at 0x7FFFFF so we can address all IO devices from the instruction directly without need for specifically indirect access for any of them
    def signal_latch_input_address(self):
        self.input_device = self.input_interface[self.dr_out & 0x7FFFFF]

    def signal_latch_output_address(self):
        self.output_device = self.output_interface[self.dr_out & 0x7FFFFF]

    # Acc and shadow signals
    def signal_latch_acc(self):
        self.acc = self.sa_or_alu_mux_out

    def signal_latch_shadow_acc(self):
        self.shadow_acc = self.acc_out

    # AR and shadow signals
    def signal_latch_ar(self):
        self.ar = self.sh_ar_or_addr_mux_out & 0x7FFFFF

    def signal_latch_shadow_ar(self):
        self.shadow_ar = self.ar & 0x7FFFFF

    # PC signals
    def signal_latch_pc(self):
        self.pc = self.add_pc_out & 0x7FFFFF

    # ALU and ADD signals
    def alu_perform_operation(self, operation):
        self.alu_out = alu_ops.get(operation, {"action": None})["action"](self)

    def add_perform_operation(self):
        self.add_pc_out = self.pc_out + self.next_or_offset_mux_out

    # multiplexors
    def signal_ext_data_mux(self, sel):
        if sel:
            self.ext_data_mux_out = self.dr_out
        else:
            imm = self.dr_out & 0x7FFFFF
            if imm & 0x400000:  # sign extend if negative
                imm = imm - 0x800000
            self.ext_data_mux_out = imm

    def signal_rel_or_abs_mux(self, sel):
        if sel:
            self.rel_or_abs_mux_out = self.ext_data_mux_out
        else:
            self.rel_or_abs_mux_out = self.add_pc_out

    def signal_data_or_inst_mux(self, sel):
        if sel:
            self.data_or_inst_mux_out = self.st_sh_mux_out
        else:
            self.data_or_inst_mux_out = self.pc_out

    def signal_sh_ar_or_addr_mux(self, sel):
        if sel:
            self.sh_ar_or_addr_mux_out = self.rel_or_abs_mux_out
        else:
            self.sh_ar_or_addr_mux_out = self.shadow_ar_out

    def signal_next_or_offset_mux(self, sel):
        if sel:
            self.next_or_offset_mux_out = self.ext_data_mux_out
        else:
            self.next_or_offset_mux_out = 4

    def signal_ext_acc_mux(self, sel):
        if sel:
            if self.acc_out & 0x80:
                self.ext_acc_mux_out = self.acc_out - 0x100
            else:
                self.ext_acc_mux_out = self.acc_out & 0xFF
        else:
            self.ext_acc_mux_out = self.acc_out

    def signal_sh_ar_or_ar_mux(self, sel):
        if sel:
            self.st_sh_mux_out = self.shadow_ar_out
        else:
            self.st_sh_mux_out = self.ar_out

    def signal_sh_acc_or_acc_mux(self, sel):
        if sel:
            self.mem_in = self.shadow_acc_out
        else:
            self.mem_in = self.acc_out

    def signal_in_or_mem_mux(self, sel):
        if sel:
            self.in_or_mem_mux_out = self.ext_data_mux_out
        else:
            self.in_or_mem_mux_out = self.input_out

    def signal_sa_or_alu_mux(self, sel):
        if sel:
            self.sa_or_alu_mux_out = self.alu_out
        else:
            self.sa_or_alu_mux_out = self.shadow_acc_out

    # memory
    def signal_write_memory_word(self):
        self.memory[self.data_or_inst_mux_out] = (self.mem_in >> 24) & 0xFF
        self.memory[self.data_or_inst_mux_out + 1] = (self.mem_in >> 16) & 0xFF
        self.memory[self.data_or_inst_mux_out + 2] = (self.mem_in >> 8) & 0xFF
        self.memory[self.data_or_inst_mux_out + 3] = self.mem_in & 0xFF

    def signal_write_memory_byte(self):
        self.memory[self.data_or_inst_mux_out] = self.mem_in & 0xFF

    def signal_read_memory_word(self):
        self.mem_out = (
            (self.memory[self.data_or_inst_mux_out] << 24)
            | (self.memory[self.data_or_inst_mux_out + 1] << 16)
            | (self.memory[self.data_or_inst_mux_out + 2] << 8)
            | self.memory[self.data_or_inst_mux_out + 3]
        )

    def signal_read_memory_byte(self):
        self.mem_out = (self.memory[self.data_or_inst_mux_out]) & 0xFF

    def sync(self):
        self.ar_out = self.ar
        self.shadow_ar_out = self.shadow_ar
        self.pc_out = self.pc
        self.acc_out = self.acc
        self.shadow_acc_out = self.shadow_acc
        self.dr_out = self.dr

    # IO
    def signal_write_output(self):
        assert self.output_device is not None, "No output device selected"
        self.output_device.write(self.acc_out)

    def signal_read_input(self):
        assert self.input_device is not None, "No input device selected"
        assert self.input_device.has_next() is True, "Input is depleted, cannot read from input device"

        self.input_out = self.input_device.read()

    def log_memory(self, start, end, step):
        mem_str = ""
        for addr in range(start, end, step):
            chunk = self.memory[addr : addr + step]
            hex_chunk = " ".join(f"{byte:02x}" for byte in chunk)
            mem_str += f"\n  [{addr:#06x}] {hex_chunk}"
        return mem_str.strip("\n")


class Device:
    input_buffer = None
    output_buffer = None

    def __init__(self, input_buffer=[], output_buffer=[]):
        self.input_buffer = input_buffer
        self.output_buffer = output_buffer

    def has_next(self):
        return len(self.input_buffer) > 0

    def read(self):
        assert self.has_next(), "Input buffer is empty"
        return self.input_buffer.pop(0)

    def write(self, value):
        self.output_buffer.append(value)


selectors = {
    "N": {"bin": 0b000, "desc": "N set"},
    "Z": {"bin": 0b001, "desc": "Z set"},
    "V": {"bin": 0b010, "desc": "V set"},
    "C": {"bin": 0b011, "desc": "C set"},
    "NN": {"bin": 0b100, "desc": "N not set"},
    "NZ": {"bin": 0b101, "desc": "Z not set"},
    "NV": {"bin": 0b110, "desc": "V not set"},
    "NC": {"bin": 0b111, "desc": "C not set"},
}


def dp_mc(
    # mux selectors
    ext_data_mux_sel=False,
    rel_or_abs_mux_sel=False,
    data_or_inst_mux_sel=False,
    sh_ar_or_addr_mux_sel=False,
    next_or_offset_mux_sel=False,
    ext_acc_mux_sel=False,
    in_or_mem_mux_sel=True,
    sa_or_alu_mux_sel=False,
    st_sh_mux_sel=False,
    # operations
    alu_operation=None,
    add_operation=False,
    # latches
    latch_dr=False,
    latch_input_address=False,
    latch_output_address=False,
    latch_acc=False,
    latch_shadow_acc=False,
    latch_ar=False,
    latch_shadow_ar=False,
    latch_pc=False,
    # mem
    read_memory_word=False,
    read_memory_byte=False,
    write_memory_word=False,
    write_memory_byte=False,
    # IO
    write_output=False,
    read_input=False,
    # control flow
    dispatch=False,
    halt=False,
    jmp=False,
    cmp=False,
    sel_cmp=None,
    address=None,
    # mnemonics
    mnemonic=None,
):
    return {"type": "dp", **locals()}


def cf_mc(
    halt=False,
    jmp=False,
    cmp=False,
    sel_cmp=None,
    address=None,
    dispatch=False,
    mnemonic=None,
):
    # cf_mc is now just dp_mc with no datapath signals
    return dp_mc(
        halt=halt,
        jmp=jmp,
        cmp=cmp,
        sel_cmp=sel_cmp,
        address=address,
        dispatch=dispatch,
        mnemonic=mnemonic,
    )


class ControlUnit:
    mpc = 0
    microcode_memory = None
    nzvc = None
    tick = 0
    datapath = None
    running = False
    mir = dp_mc()
    opcode_table = None

    def __init__(self, microcode_memory, datapath, opcode_table):
        self.nzvc = {"N": False, "Z": False, "V": False, "C": False}
        self.microcode_memory = microcode_memory
        self.datapath = datapath
        self.opcode_table = opcode_table

    def run(self, config):
        self.datapath.sync()
        self.running = True
        while self.running and self.tick < config.get("limit", 4096):
            self.process_next_tick()
            if config.get("report", False):
                template = next(
                    (report for report in config.get("report") if report.get("type") == "step-by-step"), None
                )
                if template:
                    logging.info(log_template(template.get("view", ""), self))
        if self.tick >= config.get("limit", 4096):
            logging.warning("Reached the limit of simulation.")

    def process_next_tick(self):
        # mIR latches the microinstruction from microcode memory
        self.mir = self.microcode_memory[self.mpc]
        self._execute_mc(self.mir)
        logging.debug(f"DR: {self.datapath.dr:#010x}")
        self.datapath.sync()
        self.tick += 1

    def _execute_mc(self, mc):  # noqa: C901
        dp = self.datapath

        # st_sh_mux_out (needed by data_or_inst_mux and sh_acc_or_acc_mux)
        dp.signal_sh_ar_or_ar_mux(mc["st_sh_mux_sel"])

        # ext_data_mux_out (needed by rel_or_abs_mux and next_or_offset_mux)
        dp.signal_ext_data_mux(mc["ext_data_mux_sel"])

        # next_or_offset_mux_out (needed by add)
        dp.signal_next_or_offset_mux(mc["next_or_offset_mux_sel"])

        # add_pc_out (needed by rel_or_abs_mux)
        if mc["add_operation"]:
            dp.add_perform_operation()

        # rel_or_abs_mux_out (needed by sh_ar_or_addr_mux)
        dp.signal_rel_or_abs_mux(mc["rel_or_abs_mux_sel"])

        # data_or_inst_mux_out (needed by memory reads/writes)
        dp.signal_data_or_inst_mux(mc["data_or_inst_mux_sel"])

        # sh_ar_or_addr_mux_out (needed by latch_ar)
        dp.signal_sh_ar_or_addr_mux(mc["sh_ar_or_addr_mux_sel"])

        # memory reads use data_or_inst_mux_out
        if mc["read_memory_word"]:
            dp.signal_read_memory_word()
        if mc["read_memory_byte"]:
            dp.signal_read_memory_byte()

        # IO
        if mc["write_output"]:
            dp.signal_write_output()
        if mc["read_input"]:
            dp.signal_read_input()

        # in_or_mem_mux_out (needed by ALU right input)
        dp.signal_in_or_mem_mux(mc["in_or_mem_mux_sel"])

        # ext_acc_mux_out (needed by ALU left input)
        dp.signal_ext_acc_mux(mc["ext_acc_mux_sel"])

        # alu_out (needed by sa_or_alu_mux)
        if mc["alu_operation"] is not None:
            dp.alu_perform_operation(mc["alu_operation"])
            self._update_nzvc(dp.alu_out)

        # sa_or_alu_mux_out (needed by latch_acc)
        dp.signal_sa_or_alu_mux(mc["sa_or_alu_mux_sel"])

        # sh_acc_or_acc_mux (mem_in, needed by memory writes)
        dp.signal_sh_acc_or_acc_mux(mc["st_sh_mux_sel"])

        # memory writes use data_or_inst_mux_out and mem_in
        if mc["write_memory_word"]:
            dp.signal_write_memory_word()
        if mc["write_memory_byte"]:
            dp.signal_write_memory_byte()

        # latches — all inputs now settled
        if mc["latch_dr"]:
            dp.signal_latch_dr()
        if mc["latch_input_address"]:
            dp.signal_latch_input_address()
        if mc["latch_output_address"]:
            dp.signal_latch_output_address()
        if mc["latch_acc"]:
            dp.signal_latch_acc()
        if mc["latch_shadow_acc"]:
            dp.signal_latch_shadow_acc()
        if mc["latch_ar"]:
            dp.signal_latch_ar()
        if mc["latch_shadow_ar"]:
            dp.signal_latch_shadow_ar()
        if mc["latch_pc"]:
            dp.signal_latch_pc()

        # control flow — default advance, overridden by any CF signal
        if mc["halt"]:
            self.running = False
        elif mc["dispatch"]:
            logging.debug(disassemble_at(dp, dp.pc - 4))
            logging.debug(f"Acc: {dp.acc} out: {dp.output_interface[0].output_buffer}")
            self.mpc = self.opcode_table[dp.mem_out >> 23 & 0x1FF]
        elif mc["jmp"]:
            assert mc["address"] is not None, "jumps need address"
            if mc["cmp"]:
                assert mc["sel_cmp"] is not None, "comparison microinstructions need the comparison attribute selector"
                if self._check_condition(mc["sel_cmp"]):
                    self.mpc = mc["address"]
                else:
                    self.mpc += 1
            else:
                self.mpc = mc["address"]
        else:
            self.mpc += 1

    def _check_condition(self, sel_cmp):
        flag_sel = sel_cmp & 0b011
        polarity_xor = (sel_cmp >> 2) & 1

        flags = [self.nzvc["N"], self.nzvc["Z"], self.nzvc["V"], self.nzvc["C"]]
        selected = flags[flag_sel]

        return selected ^ bool(polarity_xor)

    def _update_nzvc(self, result):
        unsigned = result & 0xFFFFFFFF
        signed = result if result < 0x80000000 else result - 0x100000000
        self.nzvc["Z"] = unsigned == 0
        self.nzvc["N"] = signed < 0
        self.nzvc["C"] = result != unsigned
        self.nzvc["V"] = result > 0x7FFFFFFF or result < -0x80000000


def load_program_into_memory(datapath, bin_file):
    with open(bin_file, "rb") as f:
        data = f.read()

    offset = 0

    # Validate magic number
    (magic_number,) = struct.unpack_from(">I", data, offset)
    assert magic_number == 0x600DCAFE, f"Invalid magic number: expected 0x600DCAFE, found {magic_number:#010x}"
    offset += 4

    # Read entry point
    assert len(data) >= 20, f"Program too short: {len(data)} bytes, expected at least 20 for header"
    (entry_point,) = struct.unpack_from(">I", data, offset)
    logging.debug(f"Entry point: {entry_point:#x}")
    datapath.pc = entry_point
    offset += 4

    # Read section headers until end-of-header marker 0xBAADCAFE
    section_info = []
    while True:
        assert offset + 4 <= len(data), "End of header not found, missing 0xBAADCAFE"
        (marker,) = struct.unpack_from(">I", data, offset)
        if marker == 0xBAADCAFE:
            offset += 4
            break
        assert offset + 8 <= len(data), "Incomplete section header entry"
        section_start, section_size = struct.unpack_from(">II", data, offset)
        section_info.append((section_start, section_size))
        offset += 8

    # Load sections into memory
    for section_start, section_size in section_info:
        assert offset + section_size <= len(data), (
            f"Section data size mismatch: expected {section_size} bytes " f"but only {len(data) - offset} remain"
        )
        assert section_start + section_size <= len(datapath.memory), (
            f"Section exceeds memory bounds: start {section_start}, "
            f"size {section_size}, memory size {len(datapath.memory)}"
        )
        section_data = data[offset : offset + section_size]
        datapath.memory[section_start : section_start + section_size] = section_data
        offset += section_size


# common microinstructions for reuse.
def _mc_set_ar_abs_from_dr():
    return dp_mc(
        ext_data_mux_sel=True,
        rel_or_abs_mux_sel=True,
        data_or_inst_mux_sel=True,
        sh_ar_or_addr_mux_sel=True,
        latch_ar=True,
        mnemonic="dr[22:0] -> ar",
    )


def _mc_set_ar_rel_from_dr():
    return dp_mc(
        ext_data_mux_sel=False,
        next_or_offset_mux_sel=True,
        add_operation=True,
        rel_or_abs_mux_sel=False,
        data_or_inst_mux_sel=True,
        sh_ar_or_addr_mux_sel=True,
        latch_ar=True,
        mnemonic="dr[22:0] + pc -> ar",
    )


def _mc_read_word_to_dr():
    return dp_mc(data_or_inst_mux_sel=True, read_memory_word=True, latch_dr=True, mnemonic="mem(ar)[31:0] -> dr")


def _mc_read_byte_to_dr():
    return dp_mc(data_or_inst_mux_sel=True, read_memory_byte=True, latch_dr=True, mnemonic="mem(ar)[7:0] -> dr")


def _mc_load_from_dr_word(fetch_addr):
    return dp_mc(
        ext_data_mux_sel=True,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation="RGHT",
        latch_acc=True,
        jmp=True,
        address=fetch_addr,
        mnemonic="dr[31:0] -> acc",
    )


def _mc_load_from_dr_byte(fetch_addr):
    return dp_mc(
        ext_data_mux_sel=True,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation="RGHT",
        latch_acc=True,
        jmp=True,
        address=fetch_addr,
        mnemonic="dr[7:0] -> acc",
    )


def _mc_load_imm(fetch_addr):
    return dp_mc(
        ext_data_mux_sel=False,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation="RGHT",
        latch_acc=True,
        jmp=True,
        address=fetch_addr,
        mnemonic="extended(dr[22:0]) -> acc",
    )


def _mc_alu_imm(op, fetch_addr):
    return dp_mc(
        ext_data_mux_sel=False,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation=op,
        latch_acc=True,
        jmp=True,
        address=fetch_addr,
        mnemonic=alu_ops[op]["desc"]("extended(dr[22:0])"),
    )


def _mc_alu_mem(op, fetch_addr):
    return dp_mc(
        ext_data_mux_sel=True,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation=op,
        latch_acc=True,
        jmp=True,
        address=fetch_addr,
        mnemonic=alu_ops[op]["desc"]("mem(ar)"),
    )


def setup_machine_simulation(memory_size=1024, input_interface=[Device()], output_interface=[Device()]):  # noqa: C901
    datapath = Datapath(memory_size, input_interface, output_interface)

    microcode = []

    def emit(mc):
        addr = len(microcode)
        microcode.append(mc)
        return addr

    # fetch sequence
    fetch_addr = len(microcode)
    emit(
        dp_mc(
            data_or_inst_mux_sel=False,
            next_or_offset_mux_sel=False,
            add_operation=True,
            latch_pc=True,
            read_memory_word=True,
            latch_dr=True,
            dispatch=True,
            mnemonic="mem(pc)[31:0] -> dr, pc+4 -> pc, jmp @instruction",
        )
    )

    # address resolve sequences
    def emit_abs_prologue():
        emit(_mc_set_ar_abs_from_dr())

    def emit_rel_prologue():
        emit(_mc_set_ar_rel_from_dr())

    def emit_ind_prologue():
        emit(_mc_set_ar_abs_from_dr())
        emit(_mc_read_word_to_dr())
        emit(_mc_set_ar_abs_from_dr())

    def emit_cond_branch_rel(inverted_sel_entry):
        inverted_sel = inverted_sel_entry["bin"]
        a = len(microcode)
        emit(
            cf_mc(
                jmp=True,
                cmp=True,
                sel_cmp=inverted_sel,
                address=fetch_addr,
                mnemonic=f"if {inverted_sel_entry['desc']}: jmp @fetch",
            )
        )
        emit(
            dp_mc(
                ext_data_mux_sel=False,
                next_or_offset_mux_sel=True,
                add_operation=True,
                latch_pc=True,
                jmp=True,
                address=fetch_addr,
                mnemonic="pc + extended(dr[22:0]) -> pc",
            )
        )
        return a

    def emit_cond_branch_ind(inverted_sel_entry):
        inverted_sel = inverted_sel_entry["bin"]
        a = len(microcode)
        emit(
            cf_mc(
                jmp=True,
                cmp=True,
                sel_cmp=inverted_sel,
                address=fetch_addr,
                mnemonic=f"if {inverted_sel_entry['desc']}: jmp @fetch",
            )
        )
        emit(_mc_set_ar_abs_from_dr())
        emit(_mc_read_word_to_dr())
        emit(
            dp_mc(
                ext_data_mux_sel=False,
                next_or_offset_mux_sel=True,
                add_operation=True,
                latch_pc=True,
                jmp=True,
                address=fetch_addr,
                mnemonic="pc + mem(ar) -> pc",
            )
        )
        return a

    # NOP
    addr_nop = len(microcode)
    emit(cf_mc(jmp=True, address=fetch_addr, mnemonic="jmp @fetch"))

    # HALT
    addr_halt = len(microcode)
    emit(cf_mc(halt=True, mnemonic="halt"))

    # CLR
    addr_clr = len(microcode)
    emit(
        dp_mc(
            sa_or_alu_mux_sel=True,
            alu_operation="CLR",
            latch_acc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="0 -> acc",
        )
    )

    # NOT
    addr_not = len(microcode)
    emit(
        dp_mc(
            sa_or_alu_mux_sel=True,
            alu_operation="NOT",
            latch_acc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="~acc -> acc",
        )
    )

    # INC
    addr_inc = len(microcode)
    emit(
        dp_mc(
            sa_or_alu_mux_sel=True,
            alu_operation="INC",
            latch_acc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc + 1 -> acc",
        )
    )

    # DEC
    addr_dec = len(microcode)
    emit(
        dp_mc(
            sa_or_alu_mux_sel=True,
            alu_operation="DEC",
            latch_acc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc - 1 -> acc",
        )
    )

    # LD WORD
    addr_ld_imm_word = len(microcode)
    emit(_mc_load_imm(fetch_addr))

    addr_ld_rel_word = len(microcode)
    emit_rel_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word(fetch_addr))

    addr_ld_abs_word = len(microcode)
    emit_abs_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word(fetch_addr))

    addr_ld_ind_word = len(microcode)
    emit_ind_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word(fetch_addr))

    # LD BYTE
    addr_ld_imm_byte = len(microcode)
    emit(_mc_load_imm(fetch_addr))

    addr_ld_rel_byte = len(microcode)
    emit_rel_prologue()
    emit(_mc_read_byte_to_dr())
    emit(_mc_load_from_dr_byte(fetch_addr))

    addr_ld_abs_byte = len(microcode)
    emit_abs_prologue()
    emit(_mc_read_byte_to_dr())
    emit(_mc_load_from_dr_byte(fetch_addr))

    addr_ld_ind_byte = len(microcode)
    emit_ind_prologue()
    emit(_mc_read_byte_to_dr())
    emit(_mc_load_from_dr_byte(fetch_addr))

    # ST WORD
    addr_st_rel_word = len(microcode)
    emit_rel_prologue()
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc[31:0] -> mem(ar)",
        )
    )

    addr_st_abs_word = len(microcode)
    emit_abs_prologue()
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc[31:0] -> mem(ar)",
        )
    )

    addr_st_ind_word = len(microcode)
    emit_ind_prologue()
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc[31:0] -> mem(ar)",
        )
    )

    # ST BYTE
    addr_st_rel_byte = len(microcode)
    emit_rel_prologue()
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc[7:0] -> mem(ar)",
        )
    )

    addr_st_abs_byte = len(microcode)
    emit_abs_prologue()
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc[7:0] -> mem(ar)",
        )
    )

    addr_st_ind_byte = len(microcode)
    emit_ind_prologue()
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc[7:0] -> mem(ar)",
        )
    )

    # alu
    def emit_alu_group(op):
        a_imm = len(microcode)
        emit(_mc_alu_imm(op, fetch_addr))

        a_rel = len(microcode)
        emit_rel_prologue()
        emit(_mc_read_word_to_dr())
        emit(_mc_alu_mem(op, fetch_addr))

        a_abs = len(microcode)
        emit_abs_prologue()
        emit(_mc_read_word_to_dr())
        emit(_mc_alu_mem(op, fetch_addr))

        a_ind = len(microcode)
        emit_ind_prologue()
        emit(_mc_read_word_to_dr())
        emit(_mc_alu_mem(op, fetch_addr))

        return a_imm, a_rel, a_abs, a_ind

    addr_add_imm, addr_add_rel, addr_add_abs, addr_add_ind = emit_alu_group("ADD")
    addr_sub_imm, addr_sub_rel, addr_sub_abs, addr_sub_ind = emit_alu_group("SUB")
    addr_and_imm, addr_and_rel, addr_and_abs, addr_and_ind = emit_alu_group("AND")
    addr_or_imm, addr_or_rel, addr_or_abs, addr_or_ind = emit_alu_group("OR")
    addr_mul_imm, addr_mul_rel, addr_mul_abs, addr_mul_ind = emit_alu_group("MUL")

    # in
    addr_in_abs = len(microcode)
    emit(dp_mc(latch_input_address=True, mnemonic="dr[22:0] -> input address"))
    emit(
        dp_mc(
            read_input=True,
            in_or_mem_mux_sel=False,
            sa_or_alu_mux_sel=True,
            alu_operation="RGHT",
            latch_acc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="input -> acc",
        )
    )

    addr_in_ind = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(dp_mc(latch_input_address=True, mnemonic="dr[31:0] -> input address"))
    emit(
        dp_mc(
            read_input=True,
            in_or_mem_mux_sel=False,
            sa_or_alu_mux_sel=True,
            alu_operation="RGHT",
            latch_acc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="input -> acc",
        )
    )

    # out
    addr_out_abs = len(microcode)
    emit(dp_mc(latch_output_address=True, mnemonic="dr[22:0] -> output address"))
    emit(dp_mc(write_output=True, jmp=True, address=fetch_addr, mnemonic="acc -> output"))

    addr_out_ind = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(dp_mc(latch_output_address=True, mnemonic="dr[31:0] -> output address"))
    emit(dp_mc(write_output=True, jmp=True, address=fetch_addr, mnemonic="acc -> output"))

    # jmp
    addr_jmp_rel = len(microcode)
    emit(
        dp_mc(
            ext_data_mux_sel=False,
            next_or_offset_mux_sel=True,
            add_operation=True,
            latch_pc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="pc + extended(dr[22:0]) -> pc",
        )
    )

    addr_jmp_ind = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(
        dp_mc(
            ext_data_mux_sel=False,
            next_or_offset_mux_sel=True,
            add_operation=True,
            latch_pc=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="pc + dr[31:0] -> pc",
        )
    )

    # Conditional branches

    addr_bzs_rel = emit_cond_branch_rel(selectors["NZ"])
    addr_bzs_ind = emit_cond_branch_ind(selectors["NZ"])
    addr_bzns_rel = emit_cond_branch_rel(selectors["Z"])
    addr_bzns_ind = emit_cond_branch_ind(selectors["Z"])
    addr_bcs_rel = emit_cond_branch_rel(selectors["NC"])
    addr_bcs_ind = emit_cond_branch_ind(selectors["NC"])
    addr_bcns_rel = emit_cond_branch_rel(selectors["C"])
    addr_bcns_ind = emit_cond_branch_ind(selectors["C"])
    addr_bvs_rel = emit_cond_branch_rel(selectors["NV"])
    addr_bvs_ind = emit_cond_branch_ind(selectors["NV"])
    addr_bvns_rel = emit_cond_branch_rel(selectors["V"])
    addr_bvns_ind = emit_cond_branch_ind(selectors["V"])
    addr_bns_rel = emit_cond_branch_rel(selectors["NN"])
    addr_bns_ind = emit_cond_branch_ind(selectors["NN"])
    addr_bnns_rel = emit_cond_branch_rel(selectors["N"])
    addr_bnns_ind = emit_cond_branch_ind(selectors["N"])

    # SWP
    addr_swp_rel = len(microcode)
    emit(
        dp_mc(
            latch_shadow_acc=True,
            sa_or_alu_mux_sel=False,
            latch_acc=True,
            ext_data_mux_sel=False,
            next_or_offset_mux_sel=True,
            rel_or_abs_mux_sel=False,
            data_or_inst_mux_sel=True,
            sh_ar_or_addr_mux_sel=True,
            add_operation=True,
            latch_ar=True,
            latch_shadow_ar=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc <-> shadow_acc, dr[22:0] + pc -> ar -> shadow_ar",
        )
    )

    addr_swp_abs = len(microcode)
    emit(
        dp_mc(
            latch_shadow_acc=True,
            sa_or_alu_mux_sel=False,
            latch_acc=True,
            ext_data_mux_sel=True,
            rel_or_abs_mux_sel=True,
            data_or_inst_mux_sel=True,
            sh_ar_or_addr_mux_sel=True,
            latch_ar=True,
            latch_shadow_ar=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc <-> shadow_acc, dr[22:0] -> ar -> shadow_ar",
        )
    )

    addr_swp_ind = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(
        dp_mc(
            latch_shadow_acc=True,
            sa_or_alu_mux_sel=False,
            latch_acc=True,
            ext_data_mux_sel=True,
            rel_or_abs_mux_sel=True,
            data_or_inst_mux_sel=True,
            sh_ar_or_addr_mux_sel=True,
            latch_ar=True,
            latch_shadow_ar=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="acc <-> shadow_acc, mem(dr[22:0]) -> ar -> shadow_ar",
        )
    )

    # FLSH
    addr_flsh_ww_rel = len(microcode)
    emit_rel_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_word=True, mnemonic="acc[31:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[31:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_ww_abs = len(microcode)
    emit_abs_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_word=True, mnemonic="acc[31:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[31:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_ww_ind = len(microcode)
    emit_ind_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_word=True, mnemonic="acc[31:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[31:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_bb_rel = len(microcode)
    emit_rel_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_byte=True, mnemonic="acc[7:0] -> mem(ar)"))
    emit(
        dp_mc(
            st_sh_mux_sel=True,
            data_or_inst_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[7:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_bb_abs = len(microcode)
    emit_abs_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_byte=True, mnemonic="acc[7:0] -> mem(ar)"))
    emit(
        dp_mc(
            st_sh_mux_sel=True,
            data_or_inst_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[7:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_bb_ind = len(microcode)
    emit_ind_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_byte=True, mnemonic="acc[7:0] -> mem(ar)"))
    emit(
        dp_mc(
            st_sh_mux_sel=True,
            data_or_inst_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[7:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_wb_rel = len(microcode)
    emit_rel_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_byte=True, mnemonic="acc[7:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[31:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_wb_abs = len(microcode)
    emit_abs_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_byte=True, mnemonic="acc[7:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[31:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_wb_ind = len(microcode)
    emit_ind_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_byte=True, mnemonic="acc[7:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_word=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[31:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_bw_rel = len(microcode)
    emit_rel_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_word=True, mnemonic="acc[31:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[7:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_bw_abs = len(microcode)
    emit_abs_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_word=True, mnemonic="acc[31:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[7:0] -> mem(shadow_ar)",
        )
    )

    addr_flsh_bw_ind = len(microcode)
    emit_ind_prologue()
    emit(dp_mc(data_or_inst_mux_sel=True, write_memory_word=True, mnemonic="acc[31:0] -> mem(ar)"))
    emit(
        dp_mc(
            data_or_inst_mux_sel=True,
            st_sh_mux_sel=True,
            write_memory_byte=True,
            jmp=True,
            address=fetch_addr,
            mnemonic="shadow_acc[7:0] -> mem(shadow_ar)",
        )
    )

    dispatch_table = {
        # no operand
        opcodes["nop"]: addr_nop,
        opcodes["halt"]: addr_halt,
        opcodes["clr"]: addr_clr,
        opcodes["not"]: addr_not,
        opcodes["inc"]: addr_inc,
        opcodes["dec"]: addr_dec,
        opcodes["ld.w_immediate"]: addr_ld_imm_word,
        opcodes["ld.w_relative"]: addr_ld_rel_word,
        opcodes["ld.w_absolute"]: addr_ld_abs_word,
        opcodes["ld.w_indirect"]: addr_ld_ind_word,
        opcodes["ld.b_immediate"]: addr_ld_imm_byte,
        opcodes["ld.b_relative"]: addr_ld_rel_byte,
        opcodes["ld.b_absolute"]: addr_ld_abs_byte,
        opcodes["ld.b_indirect"]: addr_ld_ind_byte,
        opcodes["st.w_relative"]: addr_st_rel_word,
        opcodes["st.w_absolute"]: addr_st_abs_word,
        opcodes["st.w_indirect"]: addr_st_ind_word,
        opcodes["st.b_relative"]: addr_st_rel_byte,
        opcodes["st.b_absolute"]: addr_st_abs_byte,
        opcodes["st.b_indirect"]: addr_st_ind_byte,
        opcodes["add_immediate"]: addr_add_imm,
        opcodes["add_relative"]: addr_add_rel,
        opcodes["add_absolute"]: addr_add_abs,
        opcodes["add_indirect"]: addr_add_ind,
        opcodes["mul_immediate"]: addr_mul_imm,
        opcodes["mul_relative"]: addr_mul_rel,
        opcodes["mul_absolute"]: addr_mul_abs,
        opcodes["mul_indirect"]: addr_mul_ind,
        opcodes["sub_immediate"]: addr_sub_imm,
        opcodes["sub_relative"]: addr_sub_rel,
        opcodes["sub_absolute"]: addr_sub_abs,
        opcodes["sub_indirect"]: addr_sub_ind,
        opcodes["and_immediate"]: addr_and_imm,
        opcodes["and_relative"]: addr_and_rel,
        opcodes["and_absolute"]: addr_and_abs,
        opcodes["and_indirect"]: addr_and_ind,
        opcodes["or_immediate"]: addr_or_imm,
        opcodes["or_relative"]: addr_or_rel,
        opcodes["or_absolute"]: addr_or_abs,
        opcodes["or_indirect"]: addr_or_ind,
        # IO
        opcodes["in_absolute"]: addr_in_abs,
        opcodes["in_indirect"]: addr_in_ind,
        opcodes["out_absolute"]: addr_out_abs,
        opcodes["out_indirect"]: addr_out_ind,
        # jumps
        opcodes["jmp_relative"]: addr_jmp_rel,
        opcodes["jmp_indirect"]: addr_jmp_ind,
        # branches
        opcodes["bzs_relative"]: addr_bzs_rel,
        opcodes["bzs_indirect"]: addr_bzs_ind,
        opcodes["bzns_relative"]: addr_bzns_rel,
        opcodes["bzns_indirect"]: addr_bzns_ind,
        opcodes["bcs_relative"]: addr_bcs_rel,
        opcodes["bcs_indirect"]: addr_bcs_ind,
        opcodes["bcns_relative"]: addr_bcns_rel,
        opcodes["bcns_indirect"]: addr_bcns_ind,
        opcodes["bvs_relative"]: addr_bvs_rel,
        opcodes["bvs_indirect"]: addr_bvs_ind,
        opcodes["bvns_relative"]: addr_bvns_rel,
        opcodes["bvns_indirect"]: addr_bvns_ind,
        opcodes["bns_relative"]: addr_bns_rel,
        opcodes["bns_indirect"]: addr_bns_ind,
        opcodes["bnns_relative"]: addr_bnns_rel,
        opcodes["bnns_indirect"]: addr_bnns_ind,
        opcodes["swp_relative"]: addr_swp_rel,
        opcodes["swp_absolute"]: addr_swp_abs,
        opcodes["swp_indirect"]: addr_swp_ind,
        opcodes["flsh.ww_relative"]: addr_flsh_ww_rel,
        opcodes["flsh.ww_absolute"]: addr_flsh_ww_abs,
        opcodes["flsh.ww_indirect"]: addr_flsh_ww_ind,
        opcodes["flsh.bb_relative"]: addr_flsh_bb_rel,
        opcodes["flsh.bb_absolute"]: addr_flsh_bb_abs,
        opcodes["flsh.bb_indirect"]: addr_flsh_bb_ind,
        opcodes["flsh.wb_relative"]: addr_flsh_wb_rel,
        opcodes["flsh.wb_absolute"]: addr_flsh_wb_abs,
        opcodes["flsh.wb_indirect"]: addr_flsh_wb_ind,
        opcodes["flsh.bw_relative"]: addr_flsh_bw_rel,
        opcodes["flsh.bw_absolute"]: addr_flsh_bw_abs,
        opcodes["flsh.bw_indirect"]: addr_flsh_bw_ind,
    }

    assert len(microcode) <= 2**23, f"Microcode exceeds addressable space: {len(microcode)} entries"
    assert len(dispatch_table) <= 2**9, f"Dispatch table exceeds addressable space: {len(dispatch_table)} entries"

    control_unit = ControlUnit(microcode, datapath, dispatch_table)
    return control_unit, datapath


def parse_config(config_file):
    with open(config_file) as f:
        return yaml.safe_load(f.read())


def current_mc_to_str(control_unit):
    mc = control_unit.mir

    def b(key):
        return str(int(mc[key]))

    alu = f"{alu_ops[mc['alu_operation']]['bin']:04b}" if mc["alu_operation"] is not None else "0000"

    if mc["address"] is not None:
        addr_bits = f"{mc['address']:023b}"
    elif mc["dispatch"]:
        addr_bits = f"{control_unit.opcode_table[control_unit.datapath.mem_out >> 23 & 0x1FF]:023b}"
    else:
        addr_bits = "0" * 23

    sel_bits = f"{int(mc['sel_cmp']):03b}" if mc["sel_cmp"] is not None else "000"

    return (
        b("read_memory_word")
        + b("read_memory_byte")
        + b("write_output")
        + b("read_input")
        + b("ext_data_mux_sel")
        + b("next_or_offset_mux_sel")
        + b("add_operation")
        + b("rel_or_abs_mux_sel")
        + b("in_or_mem_mux_sel")
        + b("ext_acc_mux_sel")
        + alu
        + b("data_or_inst_mux_sel")
        + b("sh_ar_or_addr_mux_sel")
        + b("sa_or_alu_mux_sel")
        + b("st_sh_mux_sel")
        + b("write_memory_word")
        + b("write_memory_byte")
        + b("latch_dr")
        + b("latch_input_address")
        + b("latch_output_address")
        + b("latch_acc")
        + b("latch_shadow_acc")
        + b("latch_ar")
        + b("latch_shadow_ar")
        + b("latch_pc")
        + b("halt")
        + b("dispatch")
        + b("jmp")
        + b("cmp")
        + sel_bits
        + addr_bits
    )


def current_mc_to_mnemonic(control_unit):
    mc = control_unit.mir
    if mc["type"] == "dp":
        return mc["mnemonic"] or ""
    return mc["mnemonic"] or ""


def get_device_state(control_unit, device, io_type):
    if io_type == "input":
        return control_unit.datapath.input_interface[device].input_buffer
    return control_unit.datapath.output_interface[device].output_buffer


def log_template(template, control_unit):
    state = {
        r"{acc}": f"{control_unit.datapath.acc:#010x}",
        r"{shadow_acc}": f"{control_unit.datapath.shadow_acc:#010x}",
        r"{pc}": f"{control_unit.datapath.pc:#010x}",
        r"{dr}": f"{control_unit.datapath.dr:#010x}",
        r"{ar}": f"{control_unit.datapath.ar:#010x}",
        r"{shadow_ar}": f"{control_unit.datapath.shadow_ar:#010x}",
        r"{N}": f"{int(control_unit.nzvc['N'])}",
        r"{Z}": f"{int(control_unit.nzvc['Z'])}",
        r"{V}": f"{int(control_unit.nzvc['V'])}",
        r"{C}": f"{int(control_unit.nzvc['C'])}",
        r"{mir}": f"{current_mc_to_str(control_unit)}",
        r"{mpc}": f"{control_unit.mpc:#06x}",
        r"{tick}": f"{control_unit.tick:04d}",
        r"{in\(\d\)}": lambda device: get_device_state(control_unit, device, "input"),
        r"{in\(\d\):hex}": lambda device: "["
        + ", ".join(f"{word:#08x}" for word in get_device_state(control_unit, device, "input"))
        + "]",
        r"{in\(\d\):dec}": lambda device: [word for word in get_device_state(control_unit, device, "input")],
        r"{in\(\d\):sym}": lambda device: [f"{chr(byte)}" for byte in get_device_state(control_unit, device, "input")],
        r"{out\(\d\)}": lambda device: get_device_state(control_unit, device, "output"),
        r"{out\(\d\):hex}": lambda device: "["
        + ", ".join(f"{word:#08x}" for word in get_device_state(control_unit, device, "output"))
        + "]",
        r"{out\(\d\):dec}": lambda device: [word for word in get_device_state(control_unit, device, "output")],
        r"{out\(\d\):sym}": lambda device: [
            f"{chr(byte)}" for byte in get_device_state(control_unit, device, "output")
        ],
        r"{memory\(\d+:\d+:\d+\)}": lambda start, end, step: control_unit.datapath.log_memory(start, end, step),
        r"{mnemonic}": current_mc_to_mnemonic(control_unit),
    }
    for key, value in state.items():
        if callable(value):

            def make_replacer(fn):
                def replacer(match):
                    args = [int(s) for s in re.findall(r"\d+", match.group(0))]
                    return str(fn(*args))

                return replacer

            template = re.sub(key, make_replacer(value), template)
        else:
            template = template.replace(key, value)
        template = template.strip("\n")
    return template


def setup_devices(config):
    input_interface = []
    output_interface = []
    if "devices" in config.keys():
        for elem in config["devices"]:
            for key in ["in", "out"]:
                for word in elem.get(key, []):
                    if isinstance(word, str):
                        assert len(word) == 1, "String literals in device buffers must be single characters"
                        elem[key][elem[key].index(word)] = ord(word)
                    else:
                        assert isinstance(word, int), "Device buffer words must be integers"
                        assert 0 <= word <= 0xFFFFFFFF, "Device buffer words must be 32-bit unsigned integers"
            device = Device(input_buffer=elem["in"], output_buffer=elem["out"])

            input_interface.append(device)
            output_interface.append(device)
    return input_interface, output_interface


def main(bin_file, config_file):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = parse_config(config_file)

    input_interface, output_interface = setup_devices(config)

    control_unit, datapath = setup_machine_simulation(
        memory_size=config.get("memory_size", 1024), input_interface=input_interface, output_interface=output_interface
    )

    load_program_into_memory(datapath, bin_file)
    if config.get("report", False):
        template = next((report for report in config.get("report") if report.get("type") == "first"), None)
        if template:
            logging.info(log_template(template.get("view", ""), control_unit))
    control_unit.run(config)
    if config.get("report", False):
        template = next((report for report in config.get("report") if report.get("type") == "last"), None)
        if template:
            logging.info(log_template(template.get("view", ""), control_unit))


if __name__ == "__main__":
    assert len(sys.argv) == 3, "Wrong arguments: machine.py <input_file> --conf=<config_file>"
    main(sys.argv[1], sys.argv[2].replace("--conf=", ""))
