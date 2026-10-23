cmake_minimum_required(VERSION 3.10)
project(htv_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)

set(msg_files
  "msg/SafeMotionCommand.msg"
  "msg/SimTrackDemand.msg"
  "msg/TrackState.msg"
  "msg/TrackSlipEstimate.msg"
  "msg/VehicleStatus.msg"
  "msg/LocalizationHealth.msg"
  "msg/SubsystemHealth.msg"
  "msg/SafetyStatus.msg"
  "msg/OperatorState.msg"
  "msg/Heartbeat.msg"
  "msg/WatchdogStatus.msg"
  "msg/GeofenceStatus.msg"
  "msg/StoppingDistance.msg"
  "msg/TraversabilityCell.msg"
  "msg/TraversabilityGrid.msg"
)

set(srv_files
  "srv/ResetEmergencyStop.srv"
  "srv/GetVehicleStatus.srv"
  "srv/InjectFailure.srv"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  DEPENDENCIES builtin_interfaces std_msgs geometry_msgs nav_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
