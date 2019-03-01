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

from __future__ import print_function
from calvin.actor.actor import Actor, manage, condition
from calvin.utilities.calvinlogger import get_logger
from calvin.runtime.north.calvinsys import get_calvinsys

_log = get_logger(__name__)


class FakeShadow(Actor):
    """
    documentation:
    - forward a token unchanged like identity Starts as shadow and can be later changed
      to not be a shadow by having a fakeshadow requires (but needs to be migrated to
      reeval)
    ports:
    - direction: in
      help: a token
      name: token
    - direction: out
      help: the same token
      name: token
    requires:
    - mock.shadow
    """
    @manage(['dump', 'last', 'node_id', 'jumps', 'index'])
    def init(self, dump):
        self.dump = dump
        self.last = None
        self.node_id = get_calvinsys()._node.id
        self.jumps = 0
        self.index = 0

    def did_migrate(self):
        self.node_id = get_calvinsys()._node.id
        self.jumps += 1

    def did_replicate(self, index):
        self.index = index

    def log(self, data):
        print("%s<%s,%s>: %s" % (self.__class__.__name__, self.name, self.id, data))

    @condition(['token'], ['token'])
    def donothing(self, input):
        token = str(self.index) + ":" + str(self.jumps) + ":" + self.node_id + ":" + str(input)
        if self.dump:
            self.log(token)
        self.last = token
        return (token, )

    def report(self, **kwargs):
        return self.last

    action_priority = (donothing, )
    

    # test_set = [
    #     {
    #         'inports': {'token': [1, 2, 3]},
    #         'outports': {'token': [1, 2, 3]}
    #     }
    # ]