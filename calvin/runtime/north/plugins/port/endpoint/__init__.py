# -*- coding: utf-8 -*-

# Copyright (c) 2016 Ericsson AB
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

from calvin.runtime.north.plugins.port.endpoint.common import Endpoint

# Endpoint methods
_MODULES = {'local': ['LocalInEndpoint', 'LocalOutEndpoint'],
            'tunnel':  ['TunnelInEndpoint', 'TunnelOutEndpoint']}
from calvin.utilities.calvinlogger import get_logger
_log = get_logger(__name__)


for module, classes in _MODULES.items():
    module_obj = __import__(module, globals=globals())
    for class_ in classes:
        globals()[class_] = getattr(module_obj, class_)
