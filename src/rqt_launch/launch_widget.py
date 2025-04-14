# coding=utf-8
# Software License Agreement (BSD License)
#
# Copyright (c) 2012, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: Isaac Saito

import os
import shlex
import sys

from python_qt_binding import loadUi
from python_qt_binding.QtCore import QModelIndex, QSettings, Signal
from python_qt_binding.QtGui import QStandardItem, QStandardItemModel
from python_qt_binding.QtWidgets import QDialog
from rosgraph import rosenv
import roslaunch
from roslaunch.core import RLException
import rospkg
import rospy

# from rqt_console.console_widget import ConsoleWidget
from rqt_launch.node_proxy import NodeProxy
from rqt_launch.node_controller import NodeController
from rqt_launch.node_delegate import NodeDelegate
from rqt_launch.status_indicator import StatusIndicator
from rqt_py_common.rqt_roscomm_util import RqtRoscommUtil


class LaunchWidget(QDialog):

    # To be connected to PluginContainerWidget
    sig_sysmsg = Signal(str)

    def __init__(self, parent):
        """
        @type parent: LaunchMain
        """
        super(LaunchWidget, self).__init__()
        self._parent = parent

        self._config = None
        self._settings = QSettings('ros', 'rqt_launch')
        self._settings.sync()
        self._package_update = False
        self._launchfile_update = False

        # TODO: should be configurable from gui
        self._port_roscore = 11311

        self._run_id = None

        self._rospack = rospkg.RosPack()
        ui_file = os.path.join(
            self._rospack.get_path('rqt_launch'), 'resource', 'launch_widget.ui'
        )
        loadUi(ui_file, self)

        # row=0 allows any number of rows to be added.
        self._datamodel = QStandardItemModel(0, 1)

        master_uri = rosenv.get_master_uri()
        rospy.loginfo('LaunchWidget master_uri={}'.format(master_uri))
        self._delegate = NodeDelegate(master_uri, self._rospack)
        self._treeview.setModel(self._datamodel)
        self._treeview.setItemDelegate(self._delegate)

        # NodeController used in controller class for launch operation.
        self._node_controllers = []

        self._pushbutton_load_params.clicked.connect(self._parent.load_params)
        self._pushbutton_start_all.clicked.connect(self._parent.start_all)
        self._pushbutton_stop_all.clicked.connect(self._parent.stop_all)
        self._pushbutton_refresh.clicked.connect(
            self._update_pkgs_contain_launchfiles
        )
        # Bind package selection with .launch file selection.
        self._combobox_pkg.currentIndexChanged[str].connect(
            self._refresh_launchfiles
        )
        # Bind a launch file selection with launch GUI generation.
        self._combobox_launchfile_name.currentIndexChanged[str].connect(
            self._load_launchfile_slot
        )
        self._lineedit_args.editingFinished.connect(self._store_launchargs)
        self._lineedit_args.editingFinished.connect(self._update_pkgs_contain_launchfiles)
        self._load_launchargs()
        self._update_pkgs_contain_launchfiles()

    def _load_launchfile_slot(self, launchfile_name):
        # Not yet sure why, but everytime combobox.currentIndexChanged occurs,
        # this method gets called twice with launchfile_name=='' in 1st call.
        if (
            launchfile_name is None
            or launchfile_name == ''
            or self._launchfile_update
        ):
            return
        self._settings.setValue('launchfile_name', launchfile_name)
        self._settings.sync()

        _config = None

        rospy.logdebug(
            '_load_launchfile_slot launchfile_name={}'.format(launchfile_name)
        )

        try:
            _config = self._create_launchconfig(
                launchfile_name, self._port_roscore
            )
            # TODO: folder_name_launchfile should be able to specify arbitrarily
            # _create_launchconfig takes 3rd arg for it.

        except IndexError as e:
            msg = 'IndexError={} launchfile={}'.format(e, launchfile_name)
            rospy.logerr(msg)
            self.sig_sysmsg.emit(msg)
            return
        except RLException as e:
            msg = 'RLException={} launchfile={}'.format(e, launchfile_name)
            rospy.logerr(msg)
            self.sig_sysmsg.emit(msg)
            return

        self._create_widgets_for_launchfile(_config)

    def _create_launchconfig(
        self, launchfile_name, port_roscore, folder_name_launchfile='launch'
    ):
        """
        @rtype: ROSLaunchConfig
        @raises RLException: raised by roslaunch.config.load_config_default.
        """

        pkg_name = self._combobox_pkg.currentText()

        try:
            launchfile = os.path.join(
                self._rospack.get_path(pkg_name),
                folder_name_launchfile,
                launchfile_name,
            )
        except IndexError as e:
            raise RLException('IndexError: {}'.format(e))

        launchargs = shlex.split(self._lineedit_args.text())

        try:
            launch_config = roslaunch.config.load_config_default(
                [(launchfile, launchargs)], port_roscore
            )
        except rospkg.common.ResourceNotFound as e:
            raise RLException(f'ResourceNotFound: {e}')
        except FileNotFoundError as e:
            raise RLException(f'FileNotFoundError: {e}')
        except RLException as e:
            raise e

        return launch_config

    def _create_widgets_for_launchfile(self, config):
        self._config = config

        # Delete old nodes' GUIs.
        del self._node_controllers[:]
        self._delegate.clear_node_widgets()
        # reset the data model
        self._datamodel.clear()
        self._datamodel.setColumnCount(1)
        self._datamodel.setRowCount(len(self._config.nodes))

        # Loop per xml element
        for i, node in enumerate(self._config.nodes):
            proxy = NodeProxy(self._run_id, self._config.master.uri, node)

            nodewidget_index = self._datamodel.index(i, 0, QModelIndex())
            node_widget = self._delegate.create_node_widget(
                nodewidget_index, proxy.config, StatusIndicator()
            )

            # TODO: use tree view delegates correctly instead of
            # empty QStandardItemModel
            self._datamodel.setItem(i, QStandardItem())
            self._treeview.setIndexWidget(nodewidget_index, node_widget)

            node_controller = NodeController(proxy, node_widget)
            self._node_controllers.append(node_controller)

            rospy.logdebug(
                'loop #%d proxy.config.namespace=%s ' + 'proxy.config.name=%s',
                i,
                proxy.config.namespace,
                proxy.config.name,
            )

        self._parent.set_node_controllers(self._node_controllers)

    def _update_pkgs_contain_launchfiles(self):
        """
        Inspired by rqt_msg.MessageWidget._update_pkgs_contain_launchfiles
        """
        self._package_update = True
        packages = sorted(
            [
                pkg_tuple[0]
                for pkg_tuple in RqtRoscommUtil.iterate_packages('launch')
            ]
        )
        self._package_list = packages
        rospy.logdebug('pkgs={}'.format(self._package_list))
        previous_package = self._settings.value('package', '')
        self._combobox_pkg.clear()
        self._combobox_pkg.addItems(self._package_list)
        if previous_package in self._package_list:
            index = self._package_list.index(previous_package)
        else:
            index = 0
        self._package_update = False
        self._combobox_pkg.setCurrentIndex(index)

    def _refresh_launchfiles(self, package=None):
        """
        Inspired by rqt_msg.MessageWidget._refresh_msgs
        """
        if package is None or len(package) == 0 or self._package_update:
            return
        self._launchfile_update = True
        previous_launchfile = self._settings.value('launchfile_name', '')
        self._settings.setValue('package', package)
        self._settings.sync()
        self._launchfile_instances = []  # Launch[]
        # TODO: RqtRoscommUtil.list_files's 2nd arg 'subdir' should NOT be
        # hardcoded later.
        _launch_instance_list = RqtRoscommUtil.list_files(package, 'launch')

        rospy.logdebug(
            '_refresh_launches package={} instance_list={}'.format(
                package, _launch_instance_list
            )
        )

        self._launchfile_instances = [
            x.split('/')[1] for x in _launch_instance_list
        ]

        self._combobox_launchfile_name.clear()
        self._combobox_launchfile_name.addItems(self._launchfile_instances)
        if previous_launchfile in self._launchfile_instances:
            index = self._launchfile_instances.index(previous_launchfile)
        else:
            index = 0
        self._launchfile_update = False
        self._combobox_launchfile_name.setCurrentIndex(index)

    def _store_launchargs(self):
        self._settings.setValue('launchargs', self._lineedit_args.text())
        self._settings.sync()

    def _load_launchargs(self):
        self._lineedit_args.setText(self._settings.value('launchargs', ''))

    def load_parameters(self):
        """
        Loads all global parameters into roscore.
        """
        run_id = (
            self._run_id
            if self._run_id is not None
            else roslaunch.rlutil.get_or_generate_uuid(None, True)
        )
        runner = roslaunch.ROSLaunchRunner(run_id, self._config)
        runner._load_parameters()

        msg = 'Loaded %d parameters to parameter server.' % len(
            self._config.params
        )
        self.sig_sysmsg.emit(msg)
        rospy.logdebug(msg)

    def save_settings(self, plugin_settings, instance_settings):
        # instance_settings.set_value('splitter', self._splitter.saveState())
        pass

    def restore_settings(self, plugin_settings, instance_settings):
        # if instance_settings.contains('splitter'):
        #     self._splitter.restoreState(instance_settings.value('splitter'))
        # else:
        #     self._splitter.setSizes([100, 100, 200])
        pass


if __name__ == '__main__':
    # main should be used only for debug purpose.
    # This launches this QWidget as a standalone rqt gui.
    from rqt_gui.main import Main

    main = Main()
    sys.exit(main.main(sys.argv, standalone='rqt_launch'))
