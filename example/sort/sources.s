.text
_start:
    in $0
    st.w array_len
    ld.w #array
    st.w ptr
    input_loop:
        in $0
        st.w (ptr)
        ld.w ptr
        add #4
        st.w ptr
        sub #array
        sub array_len
        sub array_len
        sub array_len
        sub array_len
        bzns input_loop

    ld.w #array
    st.w outer_ptr

outer_loop:
    ld.w outer_ptr
    sub #array
    sub array_len
    sub array_len
    sub array_len
    sub array_len
    bzs sort_done

    ld.w outer_ptr
    st.w min_ptr

    ld.w outer_ptr
    add #4
    st.w inner_ptr

inner_loop:
    ld.w inner_ptr
    sub #array
    sub array_len
    sub array_len
    sub array_len
    sub array_len
    bzs inner_done

    ld.w (inner_ptr)
    sub (min_ptr)
    bns update_min
    jmp no_update

update_min:
    ld.w inner_ptr
    st.w min_ptr

no_update:
    ; inner_ptr += 4
    ld.w inner_ptr
    add #4
    st.w inner_ptr
    jmp inner_loop

inner_done:
    ld.w (min_ptr)
    st.w tmp

    ld.w (outer_ptr)
    st.w (min_ptr)

    ; array[outer_ptr] = tmp
    ld.w tmp
    st.w (outer_ptr)

    ld.w outer_ptr
    add #4
    st.w outer_ptr
    jmp outer_loop

sort_done:
    ld.w #array
    st.w out_ptr

output_loop:
    ld.w out_ptr
    sub #array
    sub array_len
    sub array_len
    sub array_len
    sub array_len
    bzs output_done

    ld.w (out_ptr)
    out $0

    ld.w out_ptr
    add #4
    st.w out_ptr
    jmp output_loop

output_done:
    halt

.data
ptr:       .word 0
min_ptr:   .word 0
outer_ptr: .word 0
inner_ptr: .word 0
out_ptr:   .word 0
tmp:       .word 0
array_len: .word 0
array:     .word 0