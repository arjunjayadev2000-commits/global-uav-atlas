# Localization quality summary consumed by the safety supervisor and planner.

std_msgs/Header header

bool valid

# 1-sigma horizontal position uncertainty [m].
float32 position_uncertainty

# 1-sigma heading uncertainty [rad].
float32 heading_uncertainty

bool gnss_available
bool imu_available
bool odometry_available
