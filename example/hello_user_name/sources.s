.text
_start:
    ld.w #welcome_msg
    add #4
    st.w ptr

    welcome_loop:
        ld.b (ptr)
        out $0
        ld.w ptr
        inc
        st.w ptr
        sub #welcome_msg
        sub #4
        sub welcome_msg
        bzns welcome_loop


    ld.w #hello
    add #4
    add hello
    st.w ptr


    in $0
    st.w name_len


    loop_name:
        in $0
        st.b (ptr)
        ld.w ptr
        inc
        st.w ptr
        sub #hello
        sub #4
        sub hello
        sub name_len
        bzns loop_name
    
    ld.w name_len
    add hello
    st.w hello

    ld.w #hello
    add #4
    st.w ptr


    loop_hello:
        ld.b (ptr)
        out $0
        ld.w ptr
        inc
        st.w ptr
        sub #hello
        sub #4
        sub hello
        bzns loop_hello
    
    ld.b exc
    out $0

    halt

.data
ptr: .word 0
exc: .byte "!"
welcome_msg: .word 18
.byte "What is your name?"
name_len: .word 0

hello: .word 7
.byte "Hello, "
