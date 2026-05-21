.text
_start:


loop:
    ld.w cur

    add sum
    st.w sum
    
    ld.w cur
    mul cur
    add sum_squared
    st.w sum_squared

    ld.w cur
    dec
    st.w cur
    bzns loop

ld.w sum
mul sum
st.w squared_sum

sub sum_squared
out $0

halt
    

.data
cur: .word 100
sum: .word 0
sum_squared: .word 0
squared_sum: .word 0
square: .word 0
counter: .word 0