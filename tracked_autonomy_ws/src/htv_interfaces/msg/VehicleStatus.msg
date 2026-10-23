# Status of a LegacyTrackedVehicleInterface implementation.

uint8 STATE_UNINITIALIZED=0
uint8 STATE_DISABLED=1
uint8 STATE_ENABLED=2
uint8 STATE_STOPPING=3
uint8 STATE_EMERGENCY_STOP=4
uint8 STATE_FAULT=5

std_msgs/Header header

uint8 state
string state_name

# Name of the backend in use, e.g. "simulated". A hardware adapter reports its own.
string backend

# True when the interface could execute motion if enabled (feedback fresh, no fault).
bool ready
bool enabled
bool emergency_stop_latched
bool brake_engaged

# True when measured motion is below the standstill threshold.
bool stopped

# Feedback-derived body motion (track kinematics, not ground truth).
float64 measured_linear_velocity
float64 measured_yaw_rate
float64 left_track_velocity
float64 right_track_velocity

# Last accepted command after interface-side validation.
float64 commanded_linear_velocity
float64 commanded_yaw_rate

# Age of the last received command / feedback [s]. Negative = never received.
float64 command_age
float64 feedback_age

uint32 rejected_command_count
string[] faults
