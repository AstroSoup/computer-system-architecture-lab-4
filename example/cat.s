.data
len: .word 0

.text
.org 0x200
_start:
    in $0
    bzs exit

    st.w len

    loop:
        in $0
        out $0

        ld.w len
        dec
        st.w len
        
        bzns loop

    exit:
        halt
