.data
.org 0x00

hello: .word 5
.byte "Hello"
ptr: .word 0

.text
.org 0x00
_start:
ld #hello ; Loading an address through immedeate value operator used with label
inc
st ptr ; storing address of start of the string in ptr

loop:
    ld (ptr)+ ; loading char
    out #1; output char to device 1
    st ptr
    ld hello
    dec
    st hello
    bnz loop ; loop until string length is zero

halt

