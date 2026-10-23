# Generic subsystem health report (LiDAR, IMU, GNSS, perception, compute, ...).

uint8 LEVEL_OK=0
uint8 LEVEL_WARN=1
uint8 LEVEL_ERROR=2
uint8 LEVEL_STALE=3

std_msgs/Header header

# Subsystem name, e.g. "lidar", "imu", "gnss", "perception".
string name
bool valid
uint8 level
string detail
