##################################################################################################
#
#  H264EncoderTools - standalone x264 encoding helper for TAVPAGConvertor.
#
#  This executable links the GPL-licensed libx264 and runs as a SEPARATE process from the
#  Apache-2.0-licensed PAGConvertor, keeping the two licenses isolated.
#
#  Platform support:
#    - macOS (x86_64 / arm64 / universal via CMAKE_OSX_ARCHITECTURES)
#    - Linux x86_64 / arm64
#
#  Required x264 static library (choose one):
#    -D X264_LIBRARY=/path/to/libx264.a
#    -D X264_INCLUDE_DIR=/path/to/x264/include
#
##################################################################################################

cmake_minimum_required(VERSION 3.13)
project(H264EncoderTools)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if (NOT X264_INCLUDE_DIR)
    set(X264_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/x264/include)
endif ()

if (NOT X264_LIBRARY)
    if (APPLE)
        set(X264_LIBRARY ${CMAKE_CURRENT_SOURCE_DIR}/x264/mac/libx264.a)
    elseif (CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
        set(X264_LIBRARY ${CMAKE_CURRENT_SOURCE_DIR}/x264/linux_arm64/libx264.a)
    else ()
        set(X264_LIBRARY ${CMAKE_CURRENT_SOURCE_DIR}/x264/linux/libx264.a)
    endif ()
endif ()

if (NOT EXISTS ${X264_INCLUDE_DIR}/x264.h)
    message(FATAL_ERROR "x264 headers not found at ${X264_INCLUDE_DIR}. "
            "Pass -DX264_INCLUDE_DIR=/path/to/x264/include")
endif ()

if (NOT EXISTS ${X264_LIBRARY})
    message(FATAL_ERROR "x264 static library not found at ${X264_LIBRARY}. "
            "Pass -DX264_LIBRARY=/path/to/libx264.a")
endif ()

add_executable(H264EncoderTools main.cpp)
target_include_directories(H264EncoderTools PRIVATE ${X264_INCLUDE_DIR})
target_link_libraries(H264EncoderTools PRIVATE ${X264_LIBRARY})

if (APPLE)
    # x264 on Apple platforms may need a few system frameworks.
    target_link_libraries(H264EncoderTools PRIVATE
            "-framework CoreFoundation"
            "-framework CoreServices")
endif ()

if (UNIX AND NOT APPLE)
    find_package(Threads REQUIRED)
    target_link_libraries(H264EncoderTools PRIVATE Threads::Threads)
    # dlopen for x264 asm
    target_link_libraries(H264EncoderTools PRIVATE dl)
endif ()
