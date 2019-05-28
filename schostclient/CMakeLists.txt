cmake_minimum_required(VERSION 3.7)
project(OpenGLPlayground)

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} CMakeModules/)
cmake_policy(SET CMP0037 OLD)
set(CMAKE_BUILD_TYPE Debug)

set(executable output)
set(SrcDIR ./src)
set(IncludeDIR ./include)

set(THREADS_PREFER_PTHREAD_FLAD ON)
find_package(Threads REQUIRED)

file(GLOB SourceFiles 
	${SrcDIR}/*	
)

include_directories(${WinSDK})

add_executable(${executable} ${SourceFiles})

link_libraries(Project ${WinSDK})
set_target_properties(${executable} PROPERTIES
    CXX_STANDARD 17
    CXX_EXTENSIONS OFF
)
