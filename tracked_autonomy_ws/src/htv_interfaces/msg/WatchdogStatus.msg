# Output of the independent watchdog.

uint8 SEVERITY_NONE=0
uint8 SEVERITY_MINOR=1
uint8 SEVERITY_MAJOR=2
uint8 SEVERITY_CRITICAL=3

std_msgs/Header header

bool ok
uint8 worst_severity
string[] stale_nodes
string[] monitored_nodes
