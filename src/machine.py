import logging
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

    memory_out = 0

    # ar related
    rel_or_abs_mux_out = 0
    data_or_inst_mux_out = 0
    sh_ar_or_addr_mux_out = 0

    ar_out = 0
    shadow_ar_out = 0

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
        self.dr = self.memory_out

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
        self.shadow_ar = self.ar_out & 0x7FFFFF

    # PC signals
    def signal_latch_pc(self):
        self.pc = self.add_pc_out & 0x7FFFFF

    # ALU and ADD signals
    def alu_perform_operation(self, operation):
        if operation == "ADD":
            self.alu_out = self.ext_acc_mux_out + self.in_or_mem_mux_out
        elif operation == "SUB":
            self.alu_out = self.ext_acc_mux_out - self.in_or_mem_mux_out
        elif operation == "AND":
            self.alu_out = self.ext_acc_mux_out & self.in_or_mem_mux_out
        elif operation == "OR":
            self.alu_out = self.ext_acc_mux_out | self.in_or_mem_mux_out
        elif operation == "NOT":
            self.alu_out = ~self.ext_acc_mux_out
        elif operation == "CLR":
            self.alu_out = 0
        elif operation == "INC":
            self.alu_out = self.ext_acc_mux_out + 1
        elif operation == "DEC":
            self.alu_out = self.ext_acc_mux_out - 1
        elif operation == "NEG":
            self.alu_out = -self.ext_acc_mux_out
        elif operation == "LFT":
            self.alu_out = self.ext_acc_mux_out
        elif operation == "RGHT":
            self.alu_out = self.in_or_mem_mux_out
        else:
            raise ValueError(f"Unsupported ALU operation: {operation}")

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
            self.data_or_inst_mux_out = self.rel_or_abs_mux_out
        else:
            self.data_or_inst_mux_out = self.pc

    def signal_sh_ar_or_addr_mux(self, sel):
        if sel:
            self.sh_ar_or_addr_mux_out = self.data_or_inst_mux_out
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
        self.memory[self.ar_out] = (self.acc_out >> 24) & 0xFF
        self.memory[self.ar_out + 1] = (self.acc_out >> 16) & 0xFF
        self.memory[self.ar_out + 2] = (self.acc_out >> 8) & 0xFF
        self.memory[self.ar_out + 3] = self.acc_out & 0xFF

    def signal_write_memory_byte(self):
        self.memory[self.ar_out] = self.acc_out & 0xFF

    def signal_write2_memory_word(self):
        self.memory[self.shadow_ar_out] = (self.shadow_acc_out >> 24) & 0xFF
        self.memory[self.shadow_ar_out + 1] = (self.shadow_acc_out >> 16) & 0xFF
        self.memory[self.shadow_ar_out + 2] = (self.shadow_acc_out >> 8) & 0xFF
        self.memory[self.shadow_ar_out + 3] = self.shadow_acc_out & 0xFF

    def signal_write2_memory_byte(self):
        self.memory[self.shadow_ar_out] = self.shadow_acc_out & 0xFF

    def signal_read_memory_word(self):
        self.memory_out = (
            (self.memory[self.ar_out] << 24)
            | (self.memory[self.ar_out + 1] << 16)
            | (self.memory[self.ar_out + 2] << 8)
            | self.memory[self.ar_out + 3]
        )

    def signal_read_memory_byte(self):
        self.memory_out = (self.memory[self.ar_out]) & 0xFF

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
        logging.debug("Memory dump:")
        for addr in range(start, end, step):
            chunk = self.memory[addr : addr + step]
            hex_chunk = " ".join(f"{byte:02x}" for byte in chunk)
            logging.info(f"  [{addr:#06x}] {hex_chunk}")


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


SEL_N = 0b000  # branch if N
SEL_Z = 0b001  # branch if Z
SEL_V = 0b010  # branch if V
SEL_C = 0b011  # branch if C
SEL_NN = 0b100  # branch if not N
SEL_NZ = 0b101  # branch if not Z
SEL_NV = 0b110  # branch if not V
SEL_NC = 0b111  # branch if not C


class ControlUnit:
    mpc = 0
    microcode_memory = None
    nzvc = {"N": False, "Z": False, "V": False, "C": False}
    tick = 0
    datapath = None
    running = False

    opcode_table = None

    def __init__(self, microcode_memory, datapath, opcode_table):
        self.microcode_memory = microcode_memory
        self.datapath = datapath
        self.opcode_table = opcode_table

    def run(self, limit):
        self.datapath.sync()
        self.running = True
        while self.running and self.tick < limit:
            self.process_next_tick()
        if self.tick >= limit:
            logging.warning("Reached the limit of simulation.")

    def process_next_tick(self):
        # mIR latches the microinstruction from microcode memory
        mir = self.microcode_memory[self.mpc]
        if mir["type"] == "dp":
            # DP decoder fires; CF decoder defaults to mPC+1
            self._execute_dp(mir)
        else:
            # CF decoder fires; DP decoder output is masked off
            self._execute_cf(mir)
        logging.debug(f"DR: {self.datapath.dr:#010x}")
        self.datapath.sync()
        self.tick += 1

    def _execute_dp(self, mc):
        # Drives all datapath control lines combinatorially from the DP field.
        # mPC advances by +1 (the default sequential path in the scheme).
        dp = self.datapath

        if mc["read_memory_word"]:
            dp.signal_read_memory_word()
        if mc["read_memory_byte"]:
            dp.signal_read_memory_byte()

        if mc["write_output"]:
            dp.signal_write_output()
        if mc["read_input"]:
            dp.signal_read_input()

        dp.signal_ext_data_mux(mc["ext_data_mux_sel"])

        dp.signal_next_or_offset_mux(mc["next_or_offset_mux_sel"])

        if mc["add_operation"]:
            dp.add_perform_operation()

        dp.signal_rel_or_abs_mux(mc["rel_or_abs_mux_sel"])

        dp.signal_in_or_mem_mux(mc["in_or_mem_mux_sel"])

        dp.signal_ext_acc_mux(mc["ext_acc_mux_sel"])

        if mc["alu_operation"] is not None:
            dp.alu_perform_operation(mc["alu_operation"])
            self._update_nzvc(dp.alu_out)

        dp.signal_data_or_inst_mux(mc["data_or_inst_mux_sel"])

        dp.signal_sh_ar_or_addr_mux(mc["sh_ar_or_addr_mux_sel"])

        dp.signal_sa_or_alu_mux(mc["sa_or_alu_mux_sel"])

        if mc["write_memory_word"]:
            dp.signal_write_memory_word()
        if mc["write_memory_byte"]:
            dp.signal_write_memory_byte()

        if mc["write2_memory_word"]:
            dp.signal_write2_memory_word()
        if mc["write2_memory_byte"]:
            dp.signal_write2_memory_byte()

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

        self.mpc += 1

    def _execute_cf(self, mc):
        if mc["halt"]:
            self.running = False
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
        elif mc["dispatch"]:
            logging.debug(disassemble_at(self.datapath, self.datapath.pc - 4))
            logging.debug(f"Acc: {self.datapath.acc} out: {self.datapath.output_interface[0].output_buffer}")

            address = self.opcode_table[self.datapath.dr_out >> 23 & 0x1FF]
            self.mpc = address

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
    write2_memory_byte=False,
    write2_memory_word=False,
    # IO
    write_output=False,
    read_input=False,
):
    """DP microinstruction: drives datapath control lines. mPC advances by +1."""
    return {"type": "dp", **locals()}


def cf_mc(
    halt=False,
    jmp=False,
    cmp=False,
    sel_cmp=None,
    address=None,
    dispatch=False,
):
    return {"type": "cf", **locals()}


def load_program_into_memory(datapath, bin):
    with open(bin, "rb") as f:
        data = f.read()

    offset = 0

    # Validate magic number
    (magic_number,) = struct.unpack_from(">I", data, offset)
    if magic_number != 0x600DCAFE:
        raise ValueError(f"Invalid magic number: expected 0x600DCAFE, found {magic_number:#010x}")
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
        ext_data_mux_sel=True,  # ext_data_mux_out = dr_out (full word)
        rel_or_abs_mux_sel=True,  # select ext_data_mux_out
        data_or_inst_mux_sel=True,  # select rel_or_abs_mux_out
        sh_ar_or_addr_mux_sel=True,  # select data_or_inst_mux_out
        latch_ar=True,  # AR ← result & 0x7FFFFF
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
    )


def _mc_read_word_to_dr():
    return dp_mc(read_memory_word=True, latch_dr=True)


def _mc_read_byte_to_dr():
    return dp_mc(read_memory_byte=True, latch_dr=True)


# TODO: REFACTOR INTO ONE INSTRUCTION mc_load_from_dr
def _mc_load_from_dr_word():
    return dp_mc(
        ext_data_mux_sel=True,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation="RGHT",
        latch_acc=True,
    )


def _mc_load_from_dr_byte():
    return dp_mc(
        ext_data_mux_sel=True,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation="RGHT",
        latch_acc=True,
    )


def _mc_load_imm():
    return dp_mc(
        ext_data_mux_sel=False,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation="RGHT",
        latch_acc=True,
    )


def _mc_alu_imm(op):
    return dp_mc(
        ext_data_mux_sel=False,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation=op,
        latch_acc=True,
    )


def _mc_alu_mem(op):
    return dp_mc(
        ext_data_mux_sel=True,
        in_or_mem_mux_sel=True,
        sa_or_alu_mux_sel=True,
        alu_operation=op,
        latch_acc=True,
    )


def setup_machine_simulation(memory_size=1024, input_interface=[Device()], output_interface=[Device()]):
    datapath = Datapath(memory_size, input_interface, output_interface)

    microcode = []

    # TODO: add comments for microinstructions
    def emit(mc):
        addr = len(microcode)
        microcode.append(mc)
        return addr

    # fetch sequence
    fetch_addr = len(microcode)  # = 0

    emit(
        dp_mc(
            data_or_inst_mux_sel=False,
            sh_ar_or_addr_mux_sel=True,
            next_or_offset_mux_sel=False,
            add_operation=True,
            latch_ar=True,
            latch_pc=True,
        )
    )
    emit(
        dp_mc(
            read_memory_word=True,
            latch_dr=True,
        )
    )
    emit(cf_mc(dispatch=True))

    def jmp_fetch():
        return cf_mc(jmp=True, address=fetch_addr)

    # address resolve sequences
    def emit_abs_prologue():
        emit(_mc_set_ar_abs_from_dr())

    def emit_rel_prologue():
        emit(_mc_set_ar_rel_from_dr())

    def emit_ind_prologue():
        emit(_mc_set_ar_abs_from_dr())
        emit(_mc_read_word_to_dr())
        emit(_mc_set_ar_abs_from_dr())

    def emit_cond_branch_rel(inverted_sel):
        a = len(microcode)
        emit(cf_mc(jmp=True, cmp=True, sel_cmp=inverted_sel, address=fetch_addr))
        emit(
            dp_mc(
                ext_data_mux_sel=False,
                next_or_offset_mux_sel=True,
                add_operation=True,
                latch_pc=True,
            )
        )
        emit(jmp_fetch())
        return a

    def emit_cond_branch_ind(inverted_sel):
        a = len(microcode)
        emit(cf_mc(jmp=True, cmp=True, sel_cmp=inverted_sel, address=fetch_addr))
        emit(_mc_set_ar_abs_from_dr())  # AR ← operand cell address
        emit(_mc_read_word_to_dr())  # DR ← relative offset from memory
        emit(
            dp_mc(
                ext_data_mux_sel=False,
                next_or_offset_mux_sel=True,
                add_operation=True,
                latch_pc=True,
            )
        )
        emit(jmp_fetch())
        return a

    # NOP
    addr_nop = len(microcode)
    emit(jmp_fetch())

    # HALT
    addr_halt = len(microcode)
    emit(cf_mc(halt=True))

    # CLR
    addr_clr = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation="CLR", latch_acc=True))
    emit(jmp_fetch())

    # NOT
    addr_not = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation="NOT", latch_acc=True))
    emit(jmp_fetch())

    # INC
    addr_inc = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation="INC", latch_acc=True))
    emit(jmp_fetch())

    # DEC
    addr_dec = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation="DEC", latch_acc=True))
    emit(jmp_fetch())

    # LD WORD
    addr_ld_imm_word = len(microcode)
    emit(_mc_load_imm())
    emit(jmp_fetch())

    addr_ld_rel_word = len(microcode)
    emit_rel_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word())
    emit(jmp_fetch())

    addr_ld_abs_word = len(microcode)
    emit_abs_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word())
    emit(jmp_fetch())

    addr_ld_ind_word = len(microcode)
    emit_ind_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word())
    emit(jmp_fetch())

    # LD BYTE
    addr_ld_imm_byte = len(microcode)
    emit(_mc_load_imm())
    emit(jmp_fetch())

    addr_LD_REL_BYTE = len(microcode)
    emit_rel_prologue()
    emit(_mc_read_byte_to_dr())
    emit(_mc_load_from_dr_byte())
    emit(jmp_fetch())

    addr_LD_ABS_BYTE = len(microcode)
    emit_abs_prologue()
    emit(_mc_read_byte_to_dr())
    emit(_mc_load_from_dr_byte())
    emit(jmp_fetch())

    addr_LD_IND_BYTE = len(microcode)
    emit_ind_prologue()
    emit(_mc_read_byte_to_dr())
    emit(_mc_load_from_dr_byte())
    emit(jmp_fetch())

    # ST WORD
    addr_ST_REL_WORD = len(microcode)
    emit_rel_prologue()
    emit(dp_mc(write_memory_word=True))
    emit(jmp_fetch())

    addr_ST_ABS_WORD = len(microcode)
    emit_abs_prologue()
    emit(dp_mc(write_memory_word=True))
    emit(jmp_fetch())

    addr_ST_IND_WORD = len(microcode)
    emit_ind_prologue()
    emit(dp_mc(write_memory_word=True))
    emit(jmp_fetch())

    # ST BYTE
    addr_ST_REL_BYTE = len(microcode)
    emit_rel_prologue()
    emit(dp_mc(write_memory_byte=True))
    emit(jmp_fetch())

    addr_ST_ABS_BYTE = len(microcode)
    emit_abs_prologue()
    emit(dp_mc(write_memory_byte=True))
    emit(jmp_fetch())

    addr_ST_IND_BYTE = len(microcode)
    emit_ind_prologue()
    emit(dp_mc(write_memory_byte=True))
    emit(jmp_fetch())

    # alu
    def emit_alu_group(op):
        a_imm = len(microcode)
        emit(_mc_alu_imm(op))
        emit(jmp_fetch())

        a_rel = len(microcode)
        emit_rel_prologue()
        emit(_mc_read_word_to_dr())
        emit(_mc_alu_mem(op))
        emit(jmp_fetch())

        a_abs = len(microcode)
        emit_abs_prologue()
        emit(_mc_read_word_to_dr())
        emit(_mc_alu_mem(op))
        emit(jmp_fetch())

        a_ind = len(microcode)
        emit_ind_prologue()
        emit(_mc_read_word_to_dr())
        emit(_mc_alu_mem(op))
        emit(jmp_fetch())

        return a_imm, a_rel, a_abs, a_ind

    addr_ADD_IMM, addr_ADD_REL, addr_ADD_ABS, addr_ADD_IND = emit_alu_group("ADD")
    addr_SUB_IMM, addr_SUB_REL, addr_SUB_ABS, addr_SUB_IND = emit_alu_group("SUB")
    addr_AND_IMM, addr_AND_REL, addr_AND_ABS, addr_AND_IND = emit_alu_group("AND")
    addr_OR_IMM, addr_OR_REL, addr_OR_ABS, addr_OR_IND = emit_alu_group("OR")

    # in
    addr_IN_ABS = len(microcode)
    emit(dp_mc(latch_input_address=True))
    emit(
        dp_mc(
            read_input=True,
            in_or_mem_mux_sel=False,
            sa_or_alu_mux_sel=True,
            alu_operation="RGHT",
            latch_acc=True,
        )
    )
    emit(jmp_fetch())

    addr_IN_IND = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(dp_mc(latch_input_address=True))
    emit(
        dp_mc(
            read_input=True,
            in_or_mem_mux_sel=False,
            sa_or_alu_mux_sel=True,
            alu_operation="RGHT",
            latch_acc=True,
        )
    )
    emit(jmp_fetch())

    # out
    addr_OUT_ABS = len(microcode)
    emit(dp_mc(latch_output_address=True))
    emit(dp_mc(write_output=True))
    emit(jmp_fetch())

    addr_OUT_IND = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(dp_mc(latch_output_address=True))
    emit(dp_mc(write_output=True))
    emit(jmp_fetch())

    # jmp
    addr_JMP_REL = len(microcode)
    emit(
        dp_mc(
            ext_data_mux_sel=False,
            next_or_offset_mux_sel=True,
            add_operation=True,
            latch_pc=True,
        )
    )
    emit(jmp_fetch())

    addr_JMP_IND = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(
        dp_mc(
            ext_data_mux_sel=False,
            next_or_offset_mux_sel=True,
            add_operation=True,
            latch_pc=True,
        )
    )
    emit(jmp_fetch())

    # Conditional branches

    addr_bzs_rel = emit_cond_branch_rel(SEL_NZ)
    addr_bzs_ind = emit_cond_branch_ind(SEL_NZ)
    addr_bzns_rel = emit_cond_branch_rel(SEL_Z)
    addr_bzns_ind = emit_cond_branch_ind(SEL_Z)
    addr_bcs_rel = emit_cond_branch_rel(SEL_NC)
    addr_bcs_ind = emit_cond_branch_ind(SEL_NC)
    addr_bcns_rel = emit_cond_branch_rel(SEL_C)
    addr_bcns_ind = emit_cond_branch_ind(SEL_C)
    addr_bvs_rel = emit_cond_branch_rel(SEL_NV)
    addr_bvs_ind = emit_cond_branch_ind(SEL_NV)
    addr_bvns_rel = emit_cond_branch_rel(SEL_V)
    addr_bvns_ind = emit_cond_branch_ind(SEL_V)
    addr_BNS_REL = emit_cond_branch_rel(SEL_NN)
    addr_bns_ind = emit_cond_branch_ind(SEL_NN)
    addr_bnns_rel = emit_cond_branch_rel(SEL_N)
    addr_bnns_ind = emit_cond_branch_ind(SEL_N)

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
        opcodes["ld.b_relative"]: addr_LD_REL_BYTE,
        opcodes["ld.b_absolute"]: addr_LD_ABS_BYTE,
        opcodes["ld.b_indirect"]: addr_LD_IND_BYTE,
        opcodes["st.w_relative"]: addr_ST_REL_WORD,
        opcodes["st.w_absolute"]: addr_ST_ABS_WORD,
        opcodes["st.w_indirect"]: addr_ST_IND_WORD,
        opcodes["st.b_relative"]: addr_ST_REL_BYTE,
        opcodes["st.b_absolute"]: addr_ST_ABS_BYTE,
        opcodes["st.b_indirect"]: addr_ST_IND_BYTE,
        opcodes["add_immediate"]: addr_ADD_IMM,
        opcodes["add_relative"]: addr_ADD_REL,
        opcodes["add_absolute"]: addr_ADD_ABS,
        opcodes["add_indirect"]: addr_ADD_IND,
        opcodes["sub_immediate"]: addr_SUB_IMM,
        opcodes["sub_relative"]: addr_SUB_REL,
        opcodes["sub_absolute"]: addr_SUB_ABS,
        opcodes["sub_indirect"]: addr_SUB_IND,
        opcodes["and_immediate"]: addr_AND_IMM,
        opcodes["and_relative"]: addr_AND_REL,
        opcodes["and_absolute"]: addr_AND_ABS,
        opcodes["and_indirect"]: addr_AND_IND,
        opcodes["or_immediate"]: addr_OR_IMM,
        opcodes["or_relative"]: addr_OR_REL,
        opcodes["or_absolute"]: addr_OR_ABS,
        opcodes["or_indirect"]: addr_OR_IND,
        # IO
        opcodes["in_absolute"]: addr_IN_ABS,
        opcodes["in_indirect"]: addr_IN_IND,
        opcodes["out_absolute"]: addr_OUT_ABS,
        opcodes["out_indirect"]: addr_OUT_IND,
        # jumps
        opcodes["jmp_relative"]: addr_JMP_REL,
        opcodes["jmp_indirect"]: addr_JMP_IND,
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
        opcodes["bns_relative"]: addr_BNS_REL,
        opcodes["bns_indirect"]: addr_bns_ind,
        opcodes["bnns_relative"]: addr_bnns_rel,
        opcodes["bnns_indirect"]: addr_bnns_ind,
    }

    control_unit = ControlUnit(microcode, datapath, dispatch_table)
    return control_unit, datapath


def parse_config(config_file):
    with open(config_file) as f:
        return yaml.safe_load(f.read())


def log_template(template, control_unit):
    pass


def main(bin, config_file):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = parse_config(config_file)
    input_interface = []
    output_interface = []
    if "devices" in config.keys():
        for elem in config["devices"]:
            device = Device(input_buffer=elem["in"], output_buffer=elem["out"])
            input_interface.append(device)
            output_interface.append(device)
    control_unit, datapath = setup_machine_simulation(
        memory_size=config.get("memory_size", 1024), input_interface=input_interface, output_interface=output_interface
    )

    load_program_into_memory(datapath, bin)
    control_unit.run(config.get("limit", 4096))
    logging.info(output_interface[0].output_buffer)


if __name__ == "__main__":
    assert len(sys.argv) == 3, "Wrong arguments: machine.py <input_file> --conf=<config_file>"
    main(sys.argv[1], sys.argv[2].replace("--conf=", ""))
