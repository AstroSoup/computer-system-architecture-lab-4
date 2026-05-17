.data:
len: .word 0

.text
_start:
    in #0
    bez exit

    st len

    loop:
        in #0
        out #0

        ld len
        dec
        st len
        
        bnz loop

    exit:
        halt
