# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.build
# Role: Build the experimental standalone engine; not a production activation.
# Inputs: src/engine.cpp and a C++17 toolchain. Outputs: rakuxq-engine executable.
# Provenance: Project-authored, AI-assisted. State: experimental; evidence lives in CI.
cmake_minimum_required(VERSION 3.16)
project(rakuxq_native VERSION 0.1.0 LANGUAGES CXX)
find_package(Threads REQUIRED)
add_executable(rakuxq-engine src/engine.cpp)
target_compile_features(rakuxq-engine PRIVATE cxx_std_17)
target_link_libraries(rakuxq-engine PRIVATE Threads::Threads)
if(MSVC)
  target_compile_options(rakuxq-engine PRIVATE /W4 /EHsc /utf-8)
else()
  target_compile_options(rakuxq-engine PRIVATE -Wall -Wextra -Wpedantic)
endif()
