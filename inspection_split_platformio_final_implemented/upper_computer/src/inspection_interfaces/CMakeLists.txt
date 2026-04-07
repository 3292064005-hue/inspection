cmake_minimum_required(VERSION 3.8)
project(inspection_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/InspectionResult.msg"
  "msg/SortCommand.msg"
  "msg/StationState.msg"
  "msg/CountStats.msg"
  "msg/FaultEvent.msg"
  "msg/ControlCommand.msg"
  "msg/CaptureRequest.msg"
  "msg/DiagnosticsSnapshot.msg"
  "msg/SupervisorStateEnvelope.msg"
  "msg/ActionExecutorEvent.msg"
  "srv/StartInspection.srv"
  "srv/ResetFault.srv"
  "srv/SwitchRecipe.srv"
  "action/StartBatch.action"
  "action/ResetStation.action"
  "action/RunCalibration.action"
  "action/ExecuteReplay.action"
  "action/ExportBatch.action"
  "action/RunBenchmark.action"
  "action/SwitchRecipeWithValidation.action"
  DEPENDENCIES builtin_interfaces std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
