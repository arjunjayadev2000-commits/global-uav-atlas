# Track slip estimate. Used both for ground-truth slip from the simulator
# (/ground_truth/track_slip) and for on-line estimators.

std_msgs/Header header

# Longitudinal slip ratio of each track, 0 = no slip, 1 = full spin.
float64 left_slip
float64 right_slip

# Ratio between realised and kinematically-expected yaw rate (1 = ideal).
float64 yaw_rate_ratio

# Lateral skid velocity of base_link [m/s].
float64 lateral_velocity

# True when slip exceeds the configured excessive-slip threshold.
bool excessive
