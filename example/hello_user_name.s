.text
_start:
    ld #welcome_msg
    inc
    st ptr

    welcome_loop:
        ld (ptr)
        out #0
        ld ptr
        inc
        st ptr
        ld welcome_msg
        dec
        st welcome_msg
        bnz welcome_loop


    ld #hello
    inc
    add hello
    st ptr


    in #0
    st name_len
    add hello
    st hello

    loop_name:
        in #0
        st (ptr)
        ld ptr
        inc
        st ptr
        ld name_len
        dec
        st name_len
        bnz loop_name
    
    ld hello
    inc
    st ptr

    loop_hello:
        ld (ptr)
        out #0
        ld ptr
        inc
        st ptr
        ld hello
        dec
        st hello
        bnz loop_hello
    
    ld exc
    out #0
    halt

.data
ptr: .word 0
exc: .byte "!"
welcome_msg: .word 18
.byte "What is your name?"
name_len: .word 0

hello: .word 7
.byte "Hello, "