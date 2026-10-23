# SIMULATION ONLY. Track-speed demand from SimulatedLegacyTrackedVehicleInterface to
# the simulated tracked-vehicle plant. Real hardware adapters do not use this
# message; it exists so the simulator can be swapped without touching autonomy.

builtin_interfaces/Time stamp

# Demanded sprocket surface speed of each track [m/s].
float64 left_track_velocity
float64 right_track_velocity

# Simulated service brake request (normal controlled deceleration to zero).
bool service_brake

# Simulated emergency brake request (maximum deceleration to zero).
bool emergency_brake
