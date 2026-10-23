# The ONLY motion command accepted by a LegacyTrackedVehicleInterface.
#
# This message is the abstraction boundary between the autonomy software and the
# vehicle abstraction layer. It is expressed purely in body-frame kinematics; it
# carries no knowledge of how a particular platform produces motion.
#
# Published exclusively by motion_arbitration on /safe_cmd_vel.

# Requested forward speed of base_link along +x [m/s]. Negative = reverse.
float64 linear_velocity

# Requested yaw rate about +z [rad/s]. Positive = counter-clockwise (left turn).
float64 yaw_rate

# Time the command was produced. Consumers MUST reject commands older than their
# configured command timeout and treat them as a stop request.
builtin_interfaces/Time timestamp

# Motion permission asserted by the safety chain. When false the command MUST be
# treated as a stop request regardless of the velocity fields.
bool enable_motion
