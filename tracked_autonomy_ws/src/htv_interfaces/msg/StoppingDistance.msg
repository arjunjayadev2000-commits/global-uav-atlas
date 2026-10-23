# Output of the stopping-distance supervisor.

std_msgs/Header header

float64 velocity
float64 reaction_distance
float64 braking_distance
float64 safety_margin
float64 stopping_distance

# Effective deceleration used in the estimate [m/s^2].
float64 effective_deceleration
float64 terrain_slope
float64 traction_estimate
float64 terrain_confidence

# Free distance assumed available ahead [m].
float64 available_distance

# Maximum speed for which the vehicle can stop within available_distance [m/s].
float64 max_safe_velocity
