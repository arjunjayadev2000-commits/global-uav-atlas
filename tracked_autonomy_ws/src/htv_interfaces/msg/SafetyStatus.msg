# Safety supervisor state. Published at a fixed rate on /safety/status; its
# freshness is itself a heartbeat used by downstream consumers.

uint8 POWER_OFF=0
uint8 INITIALIZING=1
uint8 STANDBY=2
uint8 READY=3
uint8 AUTONOMOUS=4
uint8 DEGRADED=5
uint8 CONTROLLED_STOP=6
uint8 EMERGENCY_STOP=7
uint8 FAULT=8

std_msgs/Header header

uint8 state
string state_name

# True only in AUTONOMOUS and DEGRADED.
bool motion_allowed

# Multiplier [0, 1] applied to configured speed limits by the command limiter.
float64 speed_scale

bool emergency_stop_latched

# Individual entry conditions for AUTONOMOUS.
bool localization_valid
bool perception_valid
bool vehicle_interface_ready
bool safety_system_ready
bool operator_enable
bool geofence_valid

# Human-readable reasons for the current state (inhibits, faults).
string[] reasons

uint32 intervention_count
