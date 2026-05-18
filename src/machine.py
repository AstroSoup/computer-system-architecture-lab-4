class Datapath:
    # datapath elements
    acc = 0 # 32-bit GP register
    shadow_acc = 0 # 32-bit shadow register for acc

    ar = 0 # 23-bit address register
    shadow_ar = 0 # 23-bit shadow register for ar
    pc = 0 # 23-bit program counter

    dr = 0 # 32-bit data register, needed for instruction decoding and loading byte sized data from memory

    input_interface = None # an address space of input devices abstraction
    output_interface = None # an address space of output devices abstraction

    memory = None # an array of bytes representing memory


    # service elements (not actually elements of the datapath, but used for convenience)
    
    # dr related
    ext_data_mux_out = None

    dr_out = None

    memory_out = None

    # ar related
    rel_or_abs_mux_out = None
    data_or_inst_mux_out = None
    sh_ar_or_addr_mux_out = None

    ar_out = None
    shadow_ar_out = None

    # pc related
    next_or_offset_mux_out = None
    
    pc_out = None

    # left and right alu inputs
    ext_acc_mux_out = None
    in_or_mem_mux_out = None
    # acc related
    sa_or_alu_mux_out = None

    acc_out = None
    shadow_acc_out = None

    # outputs of complex combinational logic
    add_pc_out = None
    alu_out = None

    # devices chosen by IO signals from devices address space
    input_device = None
    output_device = None

    input_out = None

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
    # input addresses are capped at 0x7FFFFF so we can address all IO devices from the instruction directly without need for indirect access for any of them
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
        if operation == 'ADD':
            self.alu_out = self.ext_acc_mux_out + self.in_or_mem_mux_out
        elif operation == 'SUB':
            self.alu_out = self.ext_acc_mux_out - self.in_or_mem_mux_out
        elif operation == 'AND':
            self.alu_out = self.ext_acc_mux_out & self.in_or_mem_mux_out
        elif operation == 'OR':
            self.alu_out = self.ext_acc_mux_out | self.in_or_mem_mux_out
        elif operation == 'NOT':
            self.alu_out = ~self.ext_acc_mux_out
        elif operation == 'CLR':
            self.alu_out = 0
        elif operation == 'INC':
            self.alu_out = self.ext_acc_mux_out + 1
        elif operation == 'DEC':
            self.alu_out = self.ext_acc_mux_out - 1
        elif operation == 'NEG':
            self.alu_out = -self.ext_acc_mux_out
        elif operation == 'LFT':
            self.alu_out = self.ext_acc_mux_out
        elif operation == 'RGHT':
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
            if imm & 0x400000: # sign extend if negative
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
        self.memory[self.ar_out]     =  self.acc_out & 0xFF
        self.memory[self.ar_out + 1] = (self.acc_out >> 8)  & 0xFF
        self.memory[self.ar_out + 2] = (self.acc_out >> 16) & 0xFF
        self.memory[self.ar_out + 3] = (self.acc_out >> 24) & 0xFF

    
    def signal_write_memory_byte(self):
        self.memory[self.ar_out] = self.acc_out & 0xFF
    
    def signal_write2_memory_word(self):
        self.memory[self.shadow_ar_out]     =  self.shadow_acc_out & 0xFF
        self.memory[self.shadow_ar_out + 1] = (self.shadow_acc_out >> 8)  & 0xFF
        self.memory[self.shadow_ar_out + 2] = (self.shadow_acc_out >> 16) & 0xFF
        self.memory[self.shadow_ar_out + 3] = (self.shadow_acc_out >> 24) & 0xFF

    def signal_write2_memory_byte(self):
        self.memory[self.shadow_ar_out] = self.shadow_acc_out & 0xFF

    def signal_read_memory_word(self):
        self.memory_out = self.memory[self.ar_out] \
            | (self.memory[self.ar_out + 1] << 8) \
            | (self.memory[self.ar_out + 2] << 16) \
            | (self.memory[self.ar_out + 3] << 24) 

    def signal_read_memory_byte(self):
        self.memory_out = self.memory[self.ar_out] & 0xFF

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
        assert self.input_device.has_next() == True, "Input is depleted, cannot read from input device"

        self.input_out = self.input_device.read()


SEL_N  = 0b000   # branch if N
SEL_Z  = 0b001   # branch if Z
SEL_V  = 0b010   # branch if V
SEL_C  = 0b011   # branch if C
SEL_NN = 0b100   # branch if not N
SEL_NZ = 0b101   # branch if not Z
SEL_NV = 0b110   # branch if not V
SEL_NC = 0b111   # branch if not C


class ControlUnit:
    mpc = 0
    microcode_memory = None
    nzvc = {'N': False, 'Z': False, 'V': False, 'C': False}
    tick = 0
    datapath = None
    running = False

    opcode_table = None


    def __init__(self, microcode_memory, datapath, opcode_table):
        self.microcode_memory = microcode_memory
        self.datapath = datapath
        self.opcode_table = opcode_table

    def run(self):
        self.running = True
        while self.running:
            self.process_next_tick()

    def process_next_tick(self):
        # mIR latches the microinstruction from microcode memory
        mir = self.microcode_memory[self.mpc]

        if mir['type'] == 'dp':
            # DP decoder fires; CF decoder defaults to mPC+1
            self._execute_dp(mir)
        else:
            # CF decoder fires; DP decoder output is masked off
            self._execute_cf(mir)


        self.datapath.sync()
        self.tick += 1

    def _execute_dp(self, mc):
        # Drives all datapath control lines combinatorially from the DP field.
        # mPC advances by +1 (the default sequential path in the scheme).
        dp = self.datapath
        if (mc['write_memory_word']):
            dp.signal_write_memory_word()
        if (mc['write_memory_byte']):
            dp.signal_write_memory_byte()

        if (mc['write2_memory_word']):
            dp.signal_write2_memory_word()
        if (mc['write2_memory_byte']):
            dp.signal_write2_memory_byte()

        if mc['read_memory_word']:
            dp.signal_read_memory_word()
        if mc['read_memory_byte']:
            dp.signal_read_memory_byte()

        if mc['write_output']:
            dp.signal_write_output()
        if mc['read_input']:
            dp.signal_read_input()

        dp.signal_ext_data_mux(mc['ext_data_mux_sel'])
        dp.signal_rel_or_abs_mux(mc['rel_or_abs_mux_sel'])
        dp.signal_data_or_inst_mux(mc['data_or_inst_mux_sel'])
        dp.signal_sh_ar_or_addr_mux(mc['sh_ar_or_addr_mux_sel'])
        dp.signal_next_or_offset_mux(mc['next_or_offset_mux_sel'])
        dp.signal_ext_acc_mux(mc['ext_acc_mux_sel'])
        dp.signal_in_or_mem_mux(mc['in_or_mem_mux_sel'])
        dp.signal_sa_or_alu_mux(mc['sa_or_alu_mux_sel'])

        if mc['alu_operation'] is not None:
            dp.alu_perform_operation(mc['alu_operation'])
            self._update_nzvc(dp.alu_out)
        if mc['add_operation']:
            dp.add_perform_operation()

        if mc['latch_dr']:       
            dp.signal_latch_dr()
        if mc['latch_input_address']: 
            dp.signal_latch_input_address()
        if mc['latch_output_address']:
            dp.signal_latch_output_address()
        if mc['latch_acc']:           
            dp.signal_latch_acc()
        if mc['latch_shadow_acc']:    
            dp.signal_latch_shadow_acc()
        if mc['latch_ar']:            
            dp.signal_latch_ar()
        if mc['latch_shadow_ar']:     
            dp.signal_latch_shadow_ar()
        if mc['latch_pc']:            
            dp.signal_latch_pc()

        self.mpc += 1

    def _execute_cf(self, mc):
        if mc['halt']:
            self.running = False
        elif mc['jmp']:
            assert mc['address'] is not None, 'jumps need address'
            if mc['cmp']:
                assert mc['sel_cmp'] is not None, 'comparison microinstructions need the comparison attribute selector'
                if (self._check_condition(mc['sel_cmp'])):
                    self.mpc = mc['address']
                else: 
                    self.mpc += 1
            else:
                self.mpc = mc['address']
        elif mc['dispatch']:
            address = self.opcode_table[self.datapath.dr_out >> 23 & 0x1FF]
            self.mpc = address
            

    def _check_condition(self, sel_cmp):
        flag_sel = sel_cmp & 0b011
        polarity_xor = (sel_cmp >> 2) & 1

        flags = [self.nzvc['N'], self.nzvc['Z'], self.nzvc['V'], self.nzvc['C']]
        selected = flags[flag_sel]

        return selected ^ bool(polarity_xor)

    def _update_nzvc(self, result):
        unsigned = result & 0xFFFFFFFF
        signed   = result if result < 0x80000000 else result - 0x100000000
        self.nzvc['Z'] = unsigned == 0
        self.nzvc['N'] = signed < 0
        self.nzvc['C'] = result != unsigned
        self.nzvc['V'] = result > 0x7FFFFFFF or result < -0x80000000


def dp_mc(
    # mux selectors
    ext_data_mux_sel        = False,
    rel_or_abs_mux_sel      = False,
    data_or_inst_mux_sel    = False,
    sh_ar_or_addr_mux_sel   = False,
    next_or_offset_mux_sel  = False,
    ext_acc_mux_sel         = False,
    in_or_mem_mux_sel       = True,
    sa_or_alu_mux_sel       = False,
    # operations
    alu_operation           = None,
    add_operation           = False,
    # latches
    latch_dr                = False,
    latch_input_address     = False,
    latch_output_address    = False,
    latch_acc               = False,
    latch_shadow_acc        = False,
    latch_ar                = False,
    latch_shadow_ar         = False,
    latch_pc                = False,
    # mem
    read_memory_word        = False,
    read_memory_byte        = False,
    write_memory_word       = False,
    write_memory_byte       = False,
    write2_memory_byte      = False,
    write2_memory_word      = False,
    # IO
    write_output            = False,
    read_input              = False,

):
    """DP microinstruction: drives datapath control lines. mPC advances by +1."""
    return {'type': 'dp', **locals()}


def cf_mc(
    halt = False,
    jmp = False,
    cmp = False,
    sel_cmp = None,
    address = None,
    dispatch = False,

):
    return {'type': 'cf', **locals()}



def load_program_into_memory(datapath, program):
    magic_number = program[0 : 32]
    if int(magic_number, 2) != 0x600DCAFE:
        raise ValueError(f"Invalid magic number: {magic_number}, expected 0x600DCAFE, found: {int(magic_number, 2):#0{10}x}")
    """
        32 bits for magic number,
        32 bits for entry point,
        at least 1 section consisting of
          32 bits section start marker and 
          32 bits section size 
        and a 32 bits end of header marker 
    """
    assert len(program) >= 160, f"Program too short: {len(program)} bits, expected at least 160 bits for header"
    entry_point = int(program[32:64], 2)
    datapath.pc = entry_point

    pointer = 2
    word_size = 32
    byte_size = 8

    section_info = []

    while (int(program[pointer * word_size:(pointer + 1) * word_size], 2) != 0xBAADCAFE):
        assert (pointer + 2) * word_size <= len(program), "End of header not found, missing 0xBAADCAFE"
        
        section_start = program[pointer * word_size:(pointer + 1) * word_size]
        section_size  = program[(pointer + 1) * word_size:(pointer + 2) * word_size]

        section_info.append((int(section_start, 2), int(section_size, 2)))
        pointer += 2

    pointer += 1
    pointer *= word_size // byte_size

    for section_start, section_size in section_info:
        section_data = program[pointer * byte_size:(pointer + section_size) * byte_size]
        assert len(section_data) == section_size * byte_size, \
            f"Section data size mismatch: expected {section_size * byte_size} bits, found {len(section_data)} bits"
        
        for i in range(section_size):
            assert (section_start + i) < len(datapath.memory), \
                f"Section data exceeds memory bounds: section start {section_start}, section size {section_size}, memory size {len(datapath.memory)}"
            byte = section_data[i * byte_size:(i + 1) * byte_size]
            datapath.memory[section_start + i] = int(byte, 2)

        pointer += section_size


# common microinstructions for reuse.
def _mc_set_ar_abs_from_dr():
    """AR ← DR[22:0]  (absolute; latch_ar masks to 23 bits)."""
    return dp_mc(
        ext_data_mux_sel      = True,  # ext_data_mux_out = dr_out (full word)
        rel_or_abs_mux_sel    = True,  # select ext_data_mux_out
        data_or_inst_mux_sel  = True,  # select rel_or_abs_mux_out
        sh_ar_or_addr_mux_sel = True,  # select data_or_inst_mux_out
        latch_ar              = True,  # AR ← result & 0x7FFFFF
    )
 
def _mc_set_ar_rel_from_dr():
    """AR ← PC + sign_extend(DR[22:0])  (PC-relative)."""
    return dp_mc(
        ext_data_mux_sel       = False, # ext_data_mux_out = sign_extend(DR[22:0])
        next_or_offset_mux_sel = True,  # adder right input = offset
        add_operation          = True,  # add_pc_out = pc_out + offset
        rel_or_abs_mux_sel     = False, # select add_pc_out
        data_or_inst_mux_sel   = True,  # select rel_or_abs_mux_out
        sh_ar_or_addr_mux_sel  = True,  # select data_or_inst_mux_out
        latch_ar               = True,
    )
 
def _mc_read_word_to_dr():
    """DR ← mem[AR]  (32-bit word)."""
    return dp_mc(read_memory_word=True, latch_dr=True)
 
def _mc_read_byte_to_dr():
    """DR ← zero_extend(mem[AR][7:0])."""
    return dp_mc(read_memory_byte=True, latch_dr=True)
 
# TODO: REFACTOR INTO ONE INSTRUCTION mc_load_from_dr
def _mc_load_from_dr_word():
    """acc ← DR  (full 32-bit value from a prior word memory read)."""
    return dp_mc(
        ext_data_mux_sel  = True,   # dr_out (full 32-bit)
        in_or_mem_mux_sel = True,
        sa_or_alu_mux_sel = True,
        alu_operation     = 'RGHT',
        latch_acc         = True,
    )
 
def _mc_load_from_dr_byte():
    """acc ← DR[7:0]  (zero-extended; byte was already isolated by read_memory_byte)."""
    return dp_mc(
        ext_data_mux_sel  = True,   # dr_out — upper bits are 0 from read_memory_byte
        in_or_mem_mux_sel = True,
        sa_or_alu_mux_sel = True,
        alu_operation     = 'RGHT',
        latch_acc         = True,
    )
 
def _mc_load_imm():
    """acc ← sign_extend(DR[22:0])  — immediate encoded in instruction word."""
    return dp_mc(
        ext_data_mux_sel  = False,  # sign_extend(DR[22:0])
        in_or_mem_mux_sel = True,
        sa_or_alu_mux_sel = True,
        alu_operation     = 'RGHT',
        latch_acc         = True,
    )
 
def _mc_alu_imm(op):
    """acc ← op(acc, sign_extend(DR[22:0]))."""
    return dp_mc(
        ext_data_mux_sel  = False,
        in_or_mem_mux_sel = True,
        sa_or_alu_mux_sel = True,
        alu_operation     = op,
        latch_acc         = True,
    )
 
def _mc_alu_mem(op):
    """acc ← op(acc, DR)  — DR holds a value loaded from memory."""
    return dp_mc(
        ext_data_mux_sel  = True,
        in_or_mem_mux_sel = True,
        sa_or_alu_mux_sel = True,
        alu_operation     = op,
        latch_acc         = True,
    )
 
 

def setup_machine_simulation(memory_size=1024, input_interface=[], output_interface=[]):
    datapath = Datapath(memory_size, input_interface, output_interface)
 

    # Opcode assignments

    OPCODE_NOP         = 0
    OPCODE_HALT        = 1
    OPCODE_CLR         = 2
    OPCODE_NOT         = 3
    OPCODE_INC         = 4
    OPCODE_DEC         = 5
 
    OPCODE_LD_IMM_WORD = 6
    OPCODE_LD_REL_WORD = 7
    OPCODE_LD_ABS_WORD = 8
    OPCODE_LD_IND_WORD = 9
 
    OPCODE_LD_IMM_BYTE = 52
    OPCODE_LD_REL_BYTE = 53
    OPCODE_LD_ABS_BYTE = 54
    OPCODE_LD_IND_BYTE = 55
 
    OPCODE_ST_REL_WORD = 11
    OPCODE_ST_ABS_WORD = 12
    OPCODE_ST_IND_WORD = 13
 
    OPCODE_ST_REL_BYTE = 56
    OPCODE_ST_ABS_BYTE = 57
    OPCODE_ST_IND_BYTE = 58
 
    OPCODE_ADD_IMM     = 14
    OPCODE_ADD_REL     = 15
    OPCODE_ADD_ABS     = 16
    OPCODE_ADD_IND     = 17
    OPCODE_SUB_IMM     = 18
    OPCODE_SUB_REL     = 19
    OPCODE_SUB_ABS     = 20
    OPCODE_SUB_IND     = 21
    OPCODE_AND_IMM     = 22
    OPCODE_AND_REL     = 23
    OPCODE_AND_ABS     = 24
    OPCODE_AND_IND     = 25
    OPCODE_OR_IMM      = 26
    OPCODE_OR_REL      = 27
    OPCODE_OR_ABS      = 28
    OPCODE_OR_IND      = 29
 
    OPCODE_IN_ABS      = 30
    OPCODE_IN_IND      = 31
    OPCODE_OUT_ABS     = 32
    OPCODE_OUT_IND     = 33
 
    OPCODE_JMP_REL     = 34
    OPCODE_JMP_IND     = 35
    OPCODE_BZS_REL     = 36
    OPCODE_BZS_IND     = 37
    OPCODE_BZNS_REL    = 38
    OPCODE_BZNS_IND    = 39
    OPCODE_BCS_REL     = 40
    OPCODE_BCS_IND     = 41
    OPCODE_BCNS_REL    = 42
    OPCODE_BCNS_IND    = 43
    OPCODE_BVS_REL     = 44
    OPCODE_BVS_IND     = 45
    OPCODE_BVNS_REL    = 46
    OPCODE_BVNS_IND    = 47
    OPCODE_BNS_REL     = 48
    OPCODE_BNS_IND     = 49
    OPCODE_BNNS_REL    = 50
    OPCODE_BNNS_IND    = 51
 

    microcode = []
    # TODO: add comments for microinstructions
    def emit(mc):
        addr = len(microcode)
        microcode.append(mc)
        return addr
 
    # fetch sequence
    fetch_addr = len(microcode)  # = 0
 
    emit(dp_mc(
        data_or_inst_mux_sel   = False,
        sh_ar_or_addr_mux_sel  = True,
        next_or_offset_mux_sel = False,
        add_operation          = True,
        latch_ar               = True,
        latch_pc               = True,
    ))
    emit(dp_mc(
        read_memory_word = True,
        latch_dr         = True,
    ))
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
        emit(dp_mc(
            ext_data_mux_sel       = False,
            next_or_offset_mux_sel = True,
            add_operation          = True,
            latch_pc               = True,
        ))
        emit(jmp_fetch())
        return a
 
    def emit_cond_branch_ind(inverted_sel):
        a = len(microcode)
        emit(cf_mc(jmp=True, cmp=True, sel_cmp=inverted_sel, address=fetch_addr))
        emit(_mc_set_ar_abs_from_dr())  # AR ← operand cell address
        emit(_mc_read_word_to_dr())     # DR ← relative offset from memory
        emit(dp_mc(
            ext_data_mux_sel       = False,
            next_or_offset_mux_sel = True,
            add_operation          = True,
            latch_pc               = True,
        ))
        emit(jmp_fetch())
        return a
 
 

    # NOP
    addr_NOP = len(microcode)
    emit(jmp_fetch())
 

    # HALT
    addr_HALT = len(microcode)
    emit(cf_mc(halt=True))
 

    # CLR
    addr_CLR = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation='CLR', latch_acc=True))
    emit(jmp_fetch())
 

    # NOT
    addr_NOT = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation='NOT', latch_acc=True))
    emit(jmp_fetch())
 

    # INC
    addr_INC = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation='INC', latch_acc=True))
    emit(jmp_fetch())
 

    # DEC
    addr_DEC = len(microcode)
    emit(dp_mc(sa_or_alu_mux_sel=True, alu_operation='DEC', latch_acc=True))
    emit(jmp_fetch())
 

    # LD WORD
    addr_LD_IMM_WORD = len(microcode)
    emit(_mc_load_imm())
    emit(jmp_fetch())
 
    addr_LD_REL_WORD = len(microcode)
    emit_rel_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word())
    emit(jmp_fetch())
 
    addr_LD_ABS_WORD = len(microcode)
    emit_abs_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word())
    emit(jmp_fetch())
 
    addr_LD_IND_WORD = len(microcode)
    emit_ind_prologue()
    emit(_mc_read_word_to_dr())
    emit(_mc_load_from_dr_word())
    emit(jmp_fetch())
 

    # LD BYTE
    addr_LD_IMM_BYTE = len(microcode)
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
 

    # ALU groups: ADD / SUB / AND / OR — IMM / REL / ABS / IND
    # All arithmetic is 32-bit.  For byte arithmetic use LD_BYTE + op + ST_BYTE.

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
 
    addr_ADD_IMM, addr_ADD_REL, addr_ADD_ABS, addr_ADD_IND = emit_alu_group('ADD')
    addr_SUB_IMM, addr_SUB_REL, addr_SUB_ABS, addr_SUB_IND = emit_alu_group('SUB')
    addr_AND_IMM, addr_AND_REL, addr_AND_ABS, addr_AND_IND = emit_alu_group('AND')
    addr_OR_IMM,  addr_OR_REL,  addr_OR_ABS,  addr_OR_IND  = emit_alu_group('OR')
 

    # IN_ABS  acc ← input_device[DR[22:0]]
    # T0: select input device from DR
    # T1: read one value from device into acc

    addr_IN_ABS = len(microcode)
    emit(dp_mc(latch_input_address=True))
    emit(dp_mc(
        read_input        = True,
        in_or_mem_mux_sel = False,      # in_or_mem_mux_out = input_out
        sa_or_alu_mux_sel = True,
        alu_operation     = 'RGHT',
        latch_acc         = True,
    ))
    emit(jmp_fetch())
 

    # IN_IND  acc ← input_device[mem[DR[22:0]]]
    # T0: AR ← DR[22:0]   (pointer cell)
    # T1: DR ← mem[AR]    (device index word)
    # T2: select input device from DR
    # T3: read from device into acc

    addr_IN_IND = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(dp_mc(latch_input_address=True))
    emit(dp_mc(
        read_input        = True,
        in_or_mem_mux_sel = False,
        sa_or_alu_mux_sel = True,
        alu_operation     = 'RGHT',
        latch_acc         = True,
    ))
    emit(jmp_fetch())
 

    # OUT_ABS  output_device[DR[22:0]] ← acc

    addr_OUT_ABS = len(microcode)
    emit(dp_mc(latch_output_address=True))
    emit(dp_mc(write_output=True))
    emit(jmp_fetch())
 

    # OUT_IND  output_device[mem[DR[22:0]]] ← acc

    addr_OUT_IND = len(microcode)
    emit(_mc_set_ar_abs_from_dr())
    emit(_mc_read_word_to_dr())
    emit(dp_mc(latch_output_address=True))
    emit(dp_mc(write_output=True))
    emit(jmp_fetch())
 

    # JMP_REL  PC ← PC + sign_extend(DR[22:0])

    addr_JMP_REL = len(microcode)
    emit(dp_mc(
        ext_data_mux_sel       = False,
        next_or_offset_mux_sel = True,
        add_operation          = True,
        latch_pc               = True,
    ))
    emit(jmp_fetch())
 

    # JMP_IND  PC ← PC + sign_extend(mem[DR[22:0]][22:0])
    # The pointer cell holds a signed PC-relative offset (not an absolute
    # address) — the adder only supports PC ← PC + offset.

    addr_JMP_IND = len(microcode)
    emit(_mc_set_ar_abs_from_dr())  # AR ← operand cell address
    emit(_mc_read_word_to_dr())     # DR ← relative offset
    emit(dp_mc(
        ext_data_mux_sel       = False,
        next_or_offset_mux_sel = True,
        add_operation          = True,
        latch_pc               = True,
    ))
    emit(jmp_fetch())
 

    # Conditional branches

    addr_BZS_REL  = emit_cond_branch_rel(SEL_NZ)
    addr_BZS_IND  = emit_cond_branch_ind(SEL_NZ)
    addr_BZNS_REL = emit_cond_branch_rel(SEL_Z)
    addr_BZNS_IND = emit_cond_branch_ind(SEL_Z)
    addr_BCS_REL  = emit_cond_branch_rel(SEL_NC)
    addr_BCS_IND  = emit_cond_branch_ind(SEL_NC)
    addr_BCNS_REL = emit_cond_branch_rel(SEL_C)
    addr_BCNS_IND = emit_cond_branch_ind(SEL_C)
    addr_BVS_REL  = emit_cond_branch_rel(SEL_NV)
    addr_BVS_IND  = emit_cond_branch_ind(SEL_NV)
    addr_BVNS_REL = emit_cond_branch_rel(SEL_V)
    addr_BVNS_IND = emit_cond_branch_ind(SEL_V)
    addr_BNS_REL  = emit_cond_branch_rel(SEL_NN)
    addr_BNS_IND  = emit_cond_branch_ind(SEL_NN)
    addr_BNNS_REL = emit_cond_branch_rel(SEL_N)
    addr_BNNS_IND = emit_cond_branch_ind(SEL_N)
 

    dispatch_table = {
        OPCODE_NOP:         addr_NOP,
        OPCODE_HALT:        addr_HALT,
        OPCODE_CLR:         addr_CLR,
        OPCODE_NOT:         addr_NOT,
        OPCODE_INC:         addr_INC,
        OPCODE_DEC:         addr_DEC,
 
        OPCODE_LD_IMM_WORD: addr_LD_IMM_WORD,
        OPCODE_LD_REL_WORD: addr_LD_REL_WORD,
        OPCODE_LD_ABS_WORD: addr_LD_ABS_WORD,
        OPCODE_LD_IND_WORD: addr_LD_IND_WORD,
 
        OPCODE_LD_IMM_BYTE: addr_LD_IMM_BYTE,
        OPCODE_LD_REL_BYTE: addr_LD_REL_BYTE,
        OPCODE_LD_ABS_BYTE: addr_LD_ABS_BYTE,
        OPCODE_LD_IND_BYTE: addr_LD_IND_BYTE,
 
        OPCODE_ST_REL_WORD: addr_ST_REL_WORD,
        OPCODE_ST_ABS_WORD: addr_ST_ABS_WORD,
        OPCODE_ST_IND_WORD: addr_ST_IND_WORD,
 
        OPCODE_ST_REL_BYTE: addr_ST_REL_BYTE,
        OPCODE_ST_ABS_BYTE: addr_ST_ABS_BYTE,
        OPCODE_ST_IND_BYTE: addr_ST_IND_BYTE,
 
        OPCODE_ADD_IMM: addr_ADD_IMM,
        OPCODE_ADD_REL: addr_ADD_REL,
        OPCODE_ADD_ABS: addr_ADD_ABS,
        OPCODE_ADD_IND: addr_ADD_IND,
 
        OPCODE_SUB_IMM: addr_SUB_IMM,
        OPCODE_SUB_REL: addr_SUB_REL,
        OPCODE_SUB_ABS: addr_SUB_ABS,
        OPCODE_SUB_IND: addr_SUB_IND,
 
        OPCODE_AND_IMM: addr_AND_IMM,
        OPCODE_AND_REL: addr_AND_REL,
        OPCODE_AND_ABS: addr_AND_ABS,
        OPCODE_AND_IND: addr_AND_IND,
 
        OPCODE_OR_IMM:  addr_OR_IMM,
        OPCODE_OR_REL:  addr_OR_REL,
        OPCODE_OR_ABS:  addr_OR_ABS,
        OPCODE_OR_IND:  addr_OR_IND,
 
        OPCODE_IN_ABS:  addr_IN_ABS,
        OPCODE_IN_IND:  addr_IN_IND,
 
        OPCODE_OUT_ABS: addr_OUT_ABS,
        OPCODE_OUT_IND: addr_OUT_IND,
 
        OPCODE_JMP_REL:  addr_JMP_REL,
        OPCODE_JMP_IND:  addr_JMP_IND,
 
        OPCODE_BZS_REL:  addr_BZS_REL,
        OPCODE_BZS_IND:  addr_BZS_IND,
        OPCODE_BZNS_REL: addr_BZNS_REL,
        OPCODE_BZNS_IND: addr_BZNS_IND,
        OPCODE_BCS_REL:  addr_BCS_REL,
        OPCODE_BCS_IND:  addr_BCS_IND,
        OPCODE_BCNS_REL: addr_BCNS_REL,
        OPCODE_BCNS_IND: addr_BCNS_IND,
        OPCODE_BVS_REL:  addr_BVS_REL,
        OPCODE_BVS_IND:  addr_BVS_IND,
        OPCODE_BVNS_REL: addr_BVNS_REL,
        OPCODE_BVNS_IND: addr_BVNS_IND,
        OPCODE_BNS_REL:  addr_BNS_REL,
        OPCODE_BNS_IND:  addr_BNS_IND,
        OPCODE_BNNS_REL: addr_BNNS_REL,
        OPCODE_BNNS_IND: addr_BNNS_IND,
    }
 
    control_unit = ControlUnit(microcode, datapath, dispatch_table)
    return control_unit, datapath


def main():
    pass