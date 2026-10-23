"""Canonical topic and service names. Nodes use these so the command chain is auditable."""

# Command chain (in order). Only motion_arbitration may publish SAFE_CMD_VEL.
CMD_VEL_NAV = "/cmd_vel_nav"
GATED_CMD = "/safety/gated_cmd"
LIMITED_CMD = "/control/limited_cmd"
SAFE_CMD_VEL = "/safe_cmd_vel"

# Safety
SAFETY_STATUS = "/safety/status"
WATCHDOG_STATUS = "/watchdog/status"
WATCHDOG_ESTOP = "/safety/watchdog_estop"
ESTOP_INPUT = "/safety/estop"
STOPPING_DISTANCE = "/safety/stopping_distance"
GEOFENCE_STATUS = "/geofence/status"
HEARTBEAT = "/system/heartbeat"

# Operator
OPERATOR_STATE = "/autonomy/operator_state"
AUTONOMY_ENABLE = "/autonomy/enable"
AUTONOMY_DISABLE = "/autonomy/disable"

# Health
LOCALIZATION_HEALTH = "/localization/health"
PERCEPTION_HEALTH = "/perception/health"
LIDAR_HEALTH = "/sensors/lidar/health"
IMU_HEALTH = "/sensors/imu/health"
GNSS_HEALTH = "/sensors/gnss/health"
COMPUTE_HEALTH = "/system/compute/health"

# Vehicle abstraction layer
VEHICLE_STATUS = "/vehicle/status"
TRACK_FEEDBACK = "/vehicle/track_feedback"

# Simulation only
SIM_TRACK_DEMAND = "/sim/track_demand"
GROUND_TRUTH_ODOM = "/ground_truth/odom"
GROUND_TRUTH_SLIP = "/ground_truth/track_slip"
