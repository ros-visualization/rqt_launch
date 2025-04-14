# coding=utf-8

import rospy
from roscpp.srv import SetLoggerLevel, SetLoggerLevelRequest


# Provides callback functions for the start and stop buttons
class NodeController(object):
    """
    Containing both proxy and gui instances, this class gives a control of
    a node on both ROS & GUI sides.
    """

    SET_LOG_LEVEL_TIMOUT_S = 5.0
    DEFAULT_LOG_LEVEL = 'info'

    def __init__(self, proxy, gui):
        """
        @type proxy: rqt_launch.NodeProxy
        @type gui: QWidget
        """
        self._proxy = proxy

        self._gui = gui
        self._gui.set_node_controller(self)

        self._gui._pushbutton_start_stop_node.toggled.connect(
            self.start_stop_slot
        )
        log_level = self._gui._comboBox_log_level.currentIndexChanged.connect(
            self._update_log_level
        )

    def start_stop_slot(self, signal):
        """
        Works as a slot particularly intended to work for
        QAbstractButton::toggled(checked). Internally calls
        NodeController.start / stop depending on `signal`.

        @type signal: bool
        """
        if self._proxy.is_running():
            self.stop()
            rospy.logdebug('---start_stop_slot stOP')
        else:
            self.start()
            rospy.logdebug('==start_stop_slot StART')

    def start(self, restart=True):
        """
        Start a ROS node as a new _process.
        """
        rospy.logdebug('Controller.start restart={}'.format(restart))

        # Should be almost unreachable under current design where this 'start'
        # method only gets called when _proxy.is_running() returns false.

        if self._proxy.is_running():
            if not restart:
                # If the node is already running and restart isn't desired,
                # do nothing further.
                return
            # TODO: Need to consider...is stopping node here
            # (i.e. in 'start' method) good?
            self.stop()

        # If the launch_prefix has changed, then the _process must be recreated
        if (
            self._proxy.config.launch_prefix
            != self._gui._lineEdit_launch_args.text()
        ):
            self._proxy.config.launch_prefix = (
                self._gui._lineEdit_launch_args.text()
            )
            self._proxy.recreate_process()

        self._gui.set_node_started(False)
        self._gui.label_status.set_starting()
        self._proxy.start_process()
        self._gui.label_status.set_running()
        self._gui.label_spawncount.setText(self._get_spawn_count_text())
        log_level = self._gui._comboBox_log_level.currentIndex()
        if log_level > 0:
            self._update_log_level(log_level)

    def stop(self):
        """
        Stop a ROS node's _process.
        """

        # TODO: Need to check if the node is really running.

        # if self._proxy.is_running():
        self._gui.set_node_started(True)
        self._gui.label_status.set_stopping()
        self._proxy.stop_process()
        self._gui.label_status.set_stopped()

    def check_process_status(self):
        if self._proxy.has_died():
            rospy.logerr("Process died: {}".format(self._proxy.get_proc_name()))
            self._proxy.stop_process()
            self._gui.set_node_started(True)
            if self._proxy._process.exit_code == 0:
                self._gui.label_status.set_stopped()
            else:
                self._gui.label_status.set_died()

            # Checks if it should be respawned
            if self._gui.respawn_toggle.isChecked():
                rospy.loginfo(
                    "Respawning _process: {}".format(self._proxy._process.name)
                )
                self._gui.label_status.set_starting()
                self._proxy.start_process()
                self._gui.label_status.set_running()
                self._gui.label_spawncount.setText(self._get_spawn_count_text())

    def get_node_widget(self):
        """
        @rtype: QWidget
        """
        return self._gui

    def is_node_running(self):
        return self._proxy.is_running()

    def _get_spawn_count_text(self):
        return "({})".format(self._proxy.get_spawn_count())

    def _update_log_level(self, log_level):
        if not self.is_node_running():
            return
        if log_level == 0:
            level = self.DEFAULT_LOG_LEVEL
        else:
            level = ['debug', 'info', 'warn', 'error', 'fatal'][log_level - 1]
        self._set_logger_level(self._gui.get_node_name(), level)

    @staticmethod
    def _set_logger_level(node, level):
        service = rospy.ServiceProxy(
            '{}/set_logger_level'.format(node), SetLoggerLevel
        )
        try:
            service.wait_for_service(
                timeout=NodeController.SET_LOG_LEVEL_TIMOUT_S
            )
            service(SetLoggerLevelRequest(logger='rosout', level=level))
        except (rospy.ROSException, rospy.service.ServiceException):
            rospy.logerr("Setting logger level failed.")
