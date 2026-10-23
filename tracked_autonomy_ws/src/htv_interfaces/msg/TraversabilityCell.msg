# One cell of a TraversabilityGrid.

uint8 TRAVERSABLE=0
uint8 CAUTION=1
uint8 NON_TRAVERSABLE=2
uint8 UNKNOWN=3

# Normalised cost [0, 1]; 1 = lethal.
float32 traversability_cost
# Local slope [rad].
float32 slope
# Roughness (RMS height deviation) [m].
float32 roughness
# Mean ground elevation [m] in the grid frame.
float32 elevation
# Confidence [0, 1]; 0 = no observations.
float32 confidence
uint8 terrain_class
