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
    def signal_latch_dr_byte(self):
        self.dr = self.memory[self.ar_out] & 0xFF
    def signal_latch_dr_word(self):
        self.dr = self.memory[self.ar_out] \
            | (self.memory[self.ar_out + 1] << 8) \
            | (self.memory[self.ar_out + 2] << 16) \
            | (self.memory[self.ar_out + 3] << 24) 

    # IO signals
    # input addresses are capped at 0x7FFFFF so we can address all IO devices from the instruction directly without need for inderect access for any of them
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
            assert self.input_device.has_next() == True, "Input is depleted, cannot read from input device"
            self.in_or_mem_mux_out = self.input_device.read()
    
    def signal_sa_or_alu_mux(self, sel):
        if sel:
            self.sa_or_alu_mux_out = self.alu_out
        else:
            self.sa_or_alu_mux_out = self.shadow_acc_out

    def sync(self):
        self.ar_out = self.ar
        self.shadow_ar_out = self.shadow_ar
        self.pc_out = self.pc
        self.acc_out = self.acc
        self.shadow_acc_out = self.shadow_acc
        self.dr_out = self.dr


class ControlUnit:
    """
    We have 2 types of microcommands: 
    - datapath microcommands, which control the datapath elements and signals
    - control flow microcommands, which control the flow of microcommands
    """
    mpc = 0
    microcode_memory = None
    nzvc = {'N': False, 'Z': False, 'V': False, 'C': False}
    tick = 0
    datapath = None
    running = False

    def __init__(self, microcode_memory, datapath):
        self.microcode_memory = microcode_memory
        self.datapath = datapath

    def run(self):
        self.running = True
        while self.running:
            self.process_next_tick()

    def process_next_tick(self):
        microcommand = self.microcode_memory[self.mpc]
        if microcommand['type'] == 'datapath':
            self.execute_datapath_microcommand(microcommand)
        else:
            self.execute_control_flow_microcommand(microcommand)
        self.tick += 1

    def execute_datapath_microcommand(self, mc):
        dp = self.datapath

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

        if mc['latch_dr_word']:
            dp.signal_latch_dr_word()
        if mc['latch_dr_byte']:
            dp.signal_latch_dr_byte()
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
        dp.sync()

        self.mpc += 1


    def execute_control_flow_microcommand(self, mc):
        op = mc['op']
        if op == 'halt':
            self.running = False
            print(f"Execution halted. Ticks: {self.tick}")

        elif op == 'jump':
            self.mpc = mc['addr']

        elif op == 'dispatch':
            opcode = (self.datapath.dr_out >> 26) & 0x3F
            if opcode not in mc['table']:
                raise ValueError(f"Unknown opcode: {opcode:#04x} at tick {self.tick}")
            self.mpc = mc['table'][opcode]

        elif op == 'branch':
            if self._check_condition(mc['condition']):
                self.mpc = mc['true_addr']
            else:
                self.mpc = mc['false_addr']

    def _check_condition(self, condition):
        n = self.nzvc
        return {
            'Z':  n['Z'],
            'NZ': not n['Z'],
            'N':  n['N'],
            'NN': not n['N'],
            'V':  n['V'],
            'NV': not n['V'],
            'C':  n['C'],
            'NC': not n['C'],
        }[condition]

    def _update_nzvc(self, result):
        unsigned = result & 0xFFFFFFFF
        signed   = result if result < 0x80000000 else result - 0x100000000
        self.nzvc['Z'] = unsigned == 0
        self.nzvc['N'] = signed < 0
        self.nzvc['C'] = result != unsigned
        self.nzvc['V'] = result > 0x7FFFFFFF or result < -0x80000000



def datapath_mc(
    # mux selectors
    ext_data_mux_sel = False,
    rel_or_abs_mux_sel = False,
    data_or_inst_mux_sel = False,
    sh_ar_or_addr_mux_sel = False,
    next_or_offset_mux_sel = False,
    ext_acc_mux_sel = False,
    in_or_mem_mux_sel = False,
    sa_or_alu_mux_sel = False,
    # operations
    alu_operation = None,
    add_operation = False,
    # latches
    latch_dr_word = False,
    latch_dr_byte = False,
    latch_input_address = False,
    latch_output_address = False,
    latch_acc = False,
    latch_shadow_acc = False,
    latch_ar = False,
    latch_shadow_ar = False,
    latch_pc = False,
):
    return {'type': 'datapath', **locals()}


# control flow microcommands
def mc_halt():
    return {'type': 'control', 'op': 'halt'}

def mc_jump(addr):
    return {'type': 'control', 'op': 'jump', 'addr': addr}

def mc_dispatch(table):
    return {'type': 'control', 'op': 'dispatch', 'table': table}

def mc_branch(condition, true_addr, false_addr):
    # condition: 'Z', 'NZ', 'N', 'NN', 'V', 'NV', 'C', 'NC'
    return {'type': 'control', 'op': 'branch',
            'condition': condition,
            'true_addr': true_addr,
            'false_addr': false_addr}




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
    # loading entry point into pc
    datapath.pc = entry_point

    pointer = 2
    word_size = 32
    byte_size = 8

    section_info = []

    while (int(program[pointer * word_size:(pointer + 1) * word_size], 2) != 0xBAADCAFE):
        assert (pointer + 2) * word_size <= len(program), "End of header not found, missing 0xBAADCAFE"
        
        section_start = program[pointer * word_size:(pointer + 1) * word_size] # in bytes
        section_size = program[(pointer + 1) * word_size:(pointer + 2) * word_size] # in bytes

        section_info.append((int(section_start, 2), int(section_size, 2)))
        
        pointer += 2

    pointer += 1 # skip the end of header marker
    pointer *= word_size // byte_size # convert pointer from word index to byte index

    for section_start, section_size in section_info:
        section_data = program[pointer * byte_size:(pointer + section_size) * byte_size]
        assert len(section_data) == section_size * byte_size, f"Section data size mismatch: expected {section_size * byte_size} bits, found {len(section_data)} bits"
        
        for i in range(section_size):
            assert (section_start + i) < len(datapath.memory), f"Section data exceeds memory bounds: section start {section_start}, section size {section_size}, memory size {len(datapath.memory)}"
            byte = section_data[i * byte_size:(i + 1) * byte_size]
            datapath.memory[section_start + i] = int(byte, 2)

        pointer += section_size








def main():
    pass
