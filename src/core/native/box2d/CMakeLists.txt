cmake_minimum_required(VERSION 3.22)
project(stride2d_box2d C)

# The Box2D shim (box2d_shim.c: the pb2_* functions) on top of Box2D-Packed.
# Box2D-Packed is NOT part of this repository: build.py clones https://github.com/crustos/box2d beside it.
#   parent/
#     Stride2D/   this repository
#     box2d/      https://github.com/crustos/box2d
# Pass -DSTRIDE2D_BOX2D_DIR=/path/to/box2d to use a checkout somewhere else.
#
# Output: libstride2d_box2d_static.a + libbox2d.a (the player links these into ONE executable, no .NET),
#         libstride2d_box2d.so (the .NET reference run P/Invokes this).

option(STRIDE2D_AVX2 "Compile Box2D with AVX2 (faster; needs an AVX2 CPU; default is portable)" OFF)

set(CMAKE_C_STANDARD 11)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(BOX2D_SAMPLES OFF CACHE BOOL "" FORCE)
set(BOX2D_UNIT_TESTS OFF CACHE BOOL "" FORCE)
set(BOX2D_BENCHMARKS OFF CACHE BOOL "" FORCE)
set(BOX2D_DOCS OFF CACHE BOOL "" FORCE)
set(BOX2D_VALIDATE OFF CACHE BOOL "" FORCE)
set(BOX2D_AVX2 ${STRIDE2D_AVX2} CACHE BOOL "" FORCE)

set(STRIDE2D_BOX2D_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../../box2d" CACHE PATH "Box2D-Packed checkout")
get_filename_component(STRIDE2D_BOX2D_DIR "${STRIDE2D_BOX2D_DIR}" ABSOLUTE)
if(NOT EXISTS "${STRIDE2D_BOX2D_DIR}/CMakeLists.txt")
  message(FATAL_ERROR "Box2D-Packed not found at ${STRIDE2D_BOX2D_DIR}. Run `python3 build.py deps`.")
endif()
add_subdirectory(${STRIDE2D_BOX2D_DIR} ${CMAKE_BINARY_DIR}/box2d EXCLUDE_FROM_ALL)

foreach(kind SHARED STATIC)
  if(kind STREQUAL "SHARED")
    set(tgt stride2d_box2d)
  else()
    set(tgt stride2d_box2d_static)
  endif()
  add_library(${tgt} ${kind} box2d_shim.c)
  target_link_libraries(${tgt} PUBLIC box2d)
  target_include_directories(${tgt} PRIVATE ${STRIDE2D_BOX2D_DIR}/include)
  if(NOT MSVC)
    target_link_libraries(${tgt} PUBLIC m)
    target_compile_options(${tgt} PRIVATE -Wall -Wextra -ffp-contract=off)
  endif()
endforeach()
set_target_properties(stride2d_box2d PROPERTIES C_VISIBILITY_PRESET hidden)
