cmake_minimum_required(VERSION 3.20)
project(lowlevel_win32_native LANGUAGES CXX)

add_library(lowlevel_win32_native SHARED win32_desktop_bridge.cpp)
target_compile_features(lowlevel_win32_native PRIVATE cxx_std_20)
target_compile_definitions(lowlevel_win32_native PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_link_libraries(lowlevel_win32_native PRIVATE user32)

if(MSVC)
  target_compile_options(lowlevel_win32_native PRIVATE /W4 /WX /permissive- /EHsc /utf-8)
endif()

set_target_properties(lowlevel_win32_native PROPERTIES
  OUTPUT_NAME "lowlevel_win32_native"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin"
)

add_executable(lowlevel_mcp_supervisor WIN32 mcp_supervisor.cpp)
target_compile_features(lowlevel_mcp_supervisor PRIVATE cxx_std_20)
target_compile_definitions(lowlevel_mcp_supervisor PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
if(MSVC)
  target_compile_options(lowlevel_mcp_supervisor PRIVATE /W4 /WX /permissive- /EHsc /utf-8)
endif()
set_target_properties(lowlevel_mcp_supervisor PROPERTIES
  OUTPUT_NAME "lowlevel_mcp_supervisor"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin"
)
