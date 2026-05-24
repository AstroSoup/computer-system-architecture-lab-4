.data
a: .word 0
b: .word 1

.text
_start:
    ld.w a
    inc
    st.w a
    ld.w b
    inc
    st.w b
    ld.w a
    inc
    st.w a
    ld.w b
    out $0
    ld.w a
    out $0
    halt
