# Operator-mode state machine. Autonomy never enables itself.

uint8 MANUAL=0
uint8 AUTONOMY_ARMED=1
uint8 AUTONOMOUS=2
uint8 STOPPED=3

std_msgs/Header header

uint8 state
string state_name

# True when the operator currently asserts autonomy enable (ARMED or AUTONOMOUS).
bool operator_enable

# Increments every time the operator explicitly enables autonomy. The safety
# supervisor requires a new value before re-entering AUTONOMOUS after any stop.
uint32 enable_sequence
