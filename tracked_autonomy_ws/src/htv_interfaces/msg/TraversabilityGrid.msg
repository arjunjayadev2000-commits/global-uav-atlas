# Heavy-vehicle traversability map. Cells are stored row-major starting at
# info.origin, matching nav_msgs/OccupancyGrid conventions.

std_msgs/Header header
nav_msgs/MapMetaData info
TraversabilityCell[] cells
