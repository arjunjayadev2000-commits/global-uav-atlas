# Geofence evaluation for the vehicle footprint.

std_msgs/Header header

# Vehicle is inside the operating area with the soft margin respected.
bool valid

# Vehicle footprint has crossed the hard boundary (severe).
bool breached

# Signed distance from the footprint to the boundary [m]; negative = outside.
float64 distance_to_boundary
string fence_name
