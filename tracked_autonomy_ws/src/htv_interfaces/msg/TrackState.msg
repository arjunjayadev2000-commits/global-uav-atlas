# Track feedback, analogous to sprocket encoders. Track speeds are NOT ground
# speeds: tracks slip, so odometry computed from this message drifts.

std_msgs/Header header

# Measured sprocket surface speed [m/s].
float64 left_track_velocity
float64 right_track_velocity

# Accumulated track travel since start [m].
float64 left_track_distance
float64 right_track_distance

# Simulated brake engaged (service or emergency).
bool brake_engaged
bool emergency_brake_engaged
