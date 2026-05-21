.data
.org 0x00
hello: .word 11
.byte "hello world"
ptr: .word 0

.text
_start:
    ld.w #hello ; Loading an address through immedeate value operator used with label
    add #4
    st.w ptr ; storing address of start of the string in ptr

    loop:
        ld.b (ptr) ; loading char
        out $0; output char to device 0
        ld.w ptr
        inc
        st.w ptr
        sub #4
        sub hello
        bzns loop ; loop until string length is zero

.text
    halt
