# -*- coding: utf-8 -*-

# Copyright (c) 2015 Ericsson AB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class EnvironmentalBase(object):

    """
    Base class for environmental sensor
    """
    def __init__(self, node, actor):
        super(EnvironmentalBase, self).__init__()
        self._node = node
        self._actor = actor

    def get_temperature(self):
        """
        returns: float with current temperature in degress Celsius
        """
        raise NotImplementedError()

    def get_humidity(self):
        """
        returns: float with percentage of relative humidity
        """
        raise NotImplementedError()

    def get_pressure(self):
        """
        returns: float with pressure in millibars
        """
        raise NotImplementedError()
