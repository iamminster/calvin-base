# -*- coding: utf-8 -*-

# Copyright (c) 2018 Ericsson AB
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


import json
import re

from calvin.common import calvinresponse
from calvin.common.calvin_callback import CalvinCB
from calvin.common.calvinlogger import get_logger
from .routes import register, handler
from calvin.common.attribute_resolver import format_index_string

_log = get_logger(__name__)


# USED BY: GUI, CSWEB, CSCONTROL
# FIXME: Can't be access controlled, as it is needed to find authorization server
#        PP 2019-04-29: Resolve by providing separate query path for authorization server
# 
@handler(method="GET", path="/index/{path}", optional=[r"\?root_prefix_level=(\d+)"])
def handle_get_index(self, handle, match, data, hdr):
    """
    GET /index/{key}?root_prefix_level={level}
    Fetch values under index key
    Response status code: OK or NOT_FOUND
    Response: {"result": <list of strings>}
    """
    kwargs = {}
    if match.group(3) is not None:
        kwargs['root_prefix_level'] = int(match.group(3))
    self.node.storage.get_index(
        match.group(1), cb=CalvinCB(self.get_index_cb, handle), **kwargs)

@register
def get_index_cb(self, handle, value, *args, **kwargs):
    """ Index operation response
    """
    _log.debug("get index cb (in control) %s" % (value))
    self.send_response(handle, None if value is None else json.dumps({'result': value}),
                       status=calvinresponse.NOT_FOUND if value is None else calvinresponse.OK)

# DEPRECATED: Move to debug API
@handler(method="GET", path="/dumpstorage")

def handle_dump_storage(self, handle, match, data, hdr):
    """
    GET /dumpstorage
    Dump storage to temporary file in /tmp when available
    Response status code: OK
    Response: none
    """
    name = self.node.storage.dump()
    self.send_response(handle, json.dumps(name), status=calvinresponse.OK)



@register
def storage_cb(self, key, value, handle):
    missing = calvinresponse.isfailresponse(value)
    self.send_response(handle, None if missing else json.dumps(value),
                       status=calvinresponse.NOT_FOUND if missing else calvinresponse.OK)

# USED BY: GUI, CSWEB, CSCONTROL, NODECONTROL
@handler(method="GET", path="/node/{node_id}")

def handle_get_node(self, handle, match, data, hdr):
    """
    GET /node/{node-id}
    Get information on node node-id
    Response status code: OK or NOT_FOUND
    Response:
    {
        "attributes": {...},
        "control_uri": "http(s)://<address>:<controlport>",
        "uri": "calvinip://<address>:<port>"
    }
    """
    self.node.storage.get_node(match.group(1), CalvinCB(
        func=self.storage_cb, handle=handle))

# USED BY: CSWEB, CSCONTROL
@handler(method="GET", path="/application/{application_id}")

def handle_get_application(self, handle, match, data, hdr):
    """
    GET /application/{application-id}
    Get information on application application-id
    Response status code: OK or NOT_FOUND
    Response:
    {

         "origin_node_id": <node id>,
         "actors": <list of actor ids>
         "name": <name or id of this application>
    }
    """
    self.node.storage.get_application(match.group(1), CalvinCB(
        func=self.storage_cb, handle=handle))


# USED BY: GUI, CSWEB, CSCONTROL
@handler(method="GET", path="/actor/{actor_id}")

def handle_get_actor(self, handle, match, data, hdr):
    """
    GET /actor/{actor-id}
    Get information on actor
    Response status code: OK or NOT_FOUND
    Response:
    {

        "inports": list inports
        "node_id": <node-id>,
        "type": <actor type>,
        "name": <actor name>,
        "outports": list of outports
    }
    """
    self.node.storage.get_actor(match.group(1), CalvinCB(
        func=self.storage_cb, handle=handle))

# USED BY: CSWEB
#  # Disabled in original code
@handler(method="GET", path="/actor/{actor_id}/port/{port_id}")
def handle_get_port(self, handle, match, data, hdr):
    """
        GET /actor/{actor-id}/port/{port-id}
        Get information on port {port-id} of actor {actor-id}
        Response status code: OK or NOT_FOUND
    """
    self.node.storage.get_port(match.group(2), CalvinCB(
        func=self.storage_cb, handle=handle))

