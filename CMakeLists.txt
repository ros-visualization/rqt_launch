cmake_minimum_required(VERSION 3.5)
project(rqt_launch)
# Load catkin and all dependencies required for this package
find_package(catkin REQUIRED COMPONENTS rqt_py_common)
catkin_package()
catkin_python_setup()

install(FILES plugin.xml
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

install(DIRECTORY resource
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

install(DIRECTORY launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

catkin_install_python(PROGRAMS scripts/${PROJECT_NAME}
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
