.text
_start:
    clr
    st.w sum_lo
    st.w sum_hi
    in $0
    st.w len

loop:
    ld.w len
    bzs exit
    dec
    st.w len

    in $0
    st.w cur
    bns cur_is_negative

    ld.w sum_lo
    add cur
    st.w sum_lo
    bcns loop
    ld.w sum_hi
    inc
    st.w sum_hi
    jmp loop

cur_is_negative:
    ld.w sum_lo
    add cur
    st.w sum_lo
    bcs loop
    ld.w sum_hi
    dec
    st.w sum_hi
    jmp loop

exit:
    ld.w sum_hi
    out $0
    ld.w sum_lo
    out $0
    halt

.data
len: .word 0
cur:    .word 0
sum_lo: .word 0
sum_hi: .word 0