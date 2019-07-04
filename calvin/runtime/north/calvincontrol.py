# -*- coding: utf-8 -*-

# Copyright (c) 2015-2016 Ericsson AB
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
import socket
from urllib.parse import urlparse

from calvin.common.calvinlogger import get_logger
from calvin.common.calvin_callback import CalvinCB
from calvin.runtime.south import asynchronous
from calvin.common import calvinresponse
from calvin.common import calvinconfig
from calvin.runtime.north.calvin_proto import TunnelHandler
#
# Dynamically build selected set of APIs
#
from .control_apis import routes
from .control_apis import runtime_api
from .control_apis import application_api
from .control_apis import documentation_api
from .control_apis import logging_api
from .control_apis import registry_api
from .control_apis import uicalvinsys_api
from .control_apis import proxyhandler_api

_log = get_logger(__name__)
_conf = calvinconfig.get()

def factory(node, use_proxy, uri, external_control_uri=None):
    if use_proxy:
        return CalvinControlTunnelClient(node, uri)
    else:
        return CalvinControl(node, uri, external_control_uri)


class CalvinControlBase(object):

    """
    Common functionality for CalvinControl and CalvinControlTunnelClient
    Subclass and override: start, stop, send_response, send_streamheader, send_optionsheader
    """

    def __init__(self, node, uri):
        self.node = node
        self.loggers = {}
        self.routes = routes.install_handlers(self)
        self.uri = uri

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def send_response(self, handle, data, status=200, content_type=None):
        raise NotImplementedError

    def send_streamheader(self, handle):
        raise NotImplementedError

    def send_streamdata(self, handle, data):
        raise NotImplementedError

    def send_optionsheader(self, handle, hdr):
        raise NotImplementedError

    def close_log_tunnel(self, handle):
        """ Close log tunnel
        """
        for user_id, logger in self.loggers:
            if logger.handle == handle:
                del self.loggers[user_id]

    def _handler_for_route(self, command):
        for re_route, handler in self.routes:
            match_object = re_route.match(command)
            if match_object:
                # FIXME: Return capture groups instead
                return handler, match_object
        return None, None

    # FIXME: For now, make this a callback from the server object
    def route_request(self, handle, command, headers, data):
        if self.node.quitting:
            # Answer internal error on all requests while quitting, assume client can handle that
            # TODO: Answer permantely moved (301) instead with header Location: <another-calvin-runtime>???
            self.send_response(handle, None, status=calvinresponse.INTERNAL_ERROR)
            return
        handler, match = self._handler_for_route(command)
        if not handler:
            _log.error("No route found for: %s\n%s" % (command, data))
            self.send_response(handle, None, status=404)
            return
        try:
            data = json.loads(data or 'null')
            _log.debug("Calvin control handles:%s\n%s\n---------------" % (command, data))
            handler(handle, match, data, headers)
        except Exception as err:
            _log.error("Failed to parse request", err)
            self.send_response(handle, None, status=calvinresponse.BAD_REQUEST)

    def prepare_response(self, data, status, content_type):
        content_type = content_type or "Content-Type: application/json"
        content_type += "\n"

        # No data return 204 no content
        if data is None and status in range(200, 207):
            status = 204

        header = "HTTP/1.0 " + \
            str(status) + " " + calvinresponse.RESPONSE_CODES[status] + \
            "\n" + ("" if data is None else content_type ) + \
            "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\n" + \
            "Access-Control-Allow-Origin: *\r\n" + "\n"

        return header, data

    def prepare_streamheader(self):
        response = "HTTP/1.0 200 OK\n" + "Content-Type: text/event-stream\n" + \
            "Access-Control-Allow-Origin: *\r\n" + "\n"
        return response

    def prepare_optionsheader(self, hdr):
        response = "HTTP/1.1 200 OK\n"
        # Copy the content of Access-Control-Request-Headers to the response
        if 'access-control-request-headers' in hdr:
            response += "Access-Control-Allow-Headers: " + \
                        hdr['access-control-request-headers'] + "\n"

        response += "Content-Length: 0\n" \
                    "Access-Control-Allow-Origin: *\n" \
                    "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\n" \
                    "Content-Type: *\n" \
                    "\n\r\n"
        return response

    #
    # Logging hooks
    #
    def log_actor_firing(self, actor_id, action_method, tokens_produced, tokens_consumed, production):
        pass

    def log_actor_new(self, actor_id, actor_name, actor_type):
        pass

    def log_actor_destroy(self, actor_id):
        pass

    def log_actor_migrate(self, actor_id, dest_node_id):
        pass

    def log_application_new(self, application_id, application_name):
        pass

    def log_application_destroy(self, application_id):
        pass

    def log_link_connected(self, peer_id, uri):
        pass

    def log_link_disconnected(self, peer_id):
        pass

    def log_log_message(self, message):
        pass


class ControlTunnelHandler(TunnelHandler):
    """docstring for ControlTunnelHandler"""
    def __init__(self, proto, host, external_host):
        super(ControlTunnelHandler, self).__init__(proto, 'control', {})
        self.host = host
        self.external_host = external_host
        self.controltunnels = {}

    def tunnel_request_handler(self, tunnel):
        """ Incoming tunnel request for control proxy server
            Start a socket server and update peer node with control uri
        """
        # FIXME: Move to tunnel up?
        self.controltunnels[tunnel.peer_node_id] = CalvinControlTunnelServer(tunnel, self.host, self.external_host)
        return super().tunnel_request_handler(tunnel)

    def tunnel_down(self, tunnel):
        """ Callback that the tunnel is not accepted or is going down """
        server = self.controltunnels.pop(tunnel.peer_node_id)
        server.close()
        return super().tunnel_down(tunnel)

    def tunnel_recv_handler(self, tunnel, payload):
        self.controltunnels[tunnel.peer_node_id].handle_response(payload)

    def stop(self):
        for _, control in self.controltunnels.items():
            control.close()


class CalvinControl(CalvinControlBase):
    """ An HTTP REST API for calvin nodes
    """
    def __init__(self, node, uri, external_control_uri=None):
        super(CalvinControl, self).__init__(node, uri)
        self.server = None
        url = urlparse(self.uri)
        self.host = url.hostname
        self.port = int(url.port)
        self.tunnel_handler = None
        self.external_host = urlparse(external_control_uri).hostname if external_control_uri is not None else self.host

    def start(self):
        """ Start listening on uri and handle http requests."""
        _log.info("Control API listening on: %s:%s" % (self.host, self.port))
        self.server = asynchronous.HTTPServer(self.route_request, self.host, self.port, node_name=self.node.node_name)
        self.server.start()

        if self.external_host is not None:
            self.tunnel_handler = ControlTunnelHandler(self.node.proto, self.host, self.external_host)

    def stop(self):
        """ Stop """
        self.server.stop()
        if self.tunnel_handler:
            self.tunnel_handler.stop()

    def send_response(self, handle, data, status=200, content_type=None):
        """ Send response header text/html
        """
        header, data = self.prepare_response(data, status, content_type)
        self.server.send_response(handle, header, data)

    def send_streamheader(self, handle):
        """ Send response header for text/event-stream
        """
        response = self.prepare_streamheader()
        self.server.send_response(handle, response, None, close_connection=False)

    def send_streamdata(self, handle, data):
        """ Send stream data
        """
        return self.server.send_response(handle, "data: %s\n\n" % data, None, close_connection=False)

    def send_optionsheader(self, handle, hdr):
        """ Send response header for options
        """
        response = self.prepare_optionsheader(hdr)
        self.server.send_response(handle, response)



class CalvinControlTunnelServer(object):

    """ A Calvin control socket to tunnel proxy
    """

    def __init__(self, tunnel, host, external_host):
        self.tunnel = tunnel
        self.connections = {}
        self.host = host
        self.external_host = external_host

        # Start a socket server on same interface as calvincontrol
        for x in range(5100, 5200):
            try:
                self.port = x
                self.server = asynchronous.HTTPServer(self.handle_request, self.host, self.port, node_name=None)
                self.server.start()
                _log.info("Control proxy for %s listening on: %s:%s" % (tunnel.peer_node_id, self.host, self.port))
                break
            except Exception as exc:
                _log.exception(exc)
        else:
            raise Exception("Could not find free socket")

        # Tell peer node that we are listening and on what uri
        msg = {"cmd": "started", "controluri": "http://" + self.external_host + ":" + str(self.port)}
        self.tunnel.send(msg)

    def close(self):
        self.server.stop()

    def handle_request(self, msg_id, command, headers, data):
        """ Handle connections and tunnel requests
        """
        msg = {"cmd": "httpreq",
               "msgid": msg_id,
               "command": command,
               "headers": headers,
               "data": data}
        self.tunnel.send(msg)

    def handle_response(self, payload):
        """ Handle a tunnel response
        """
        msgid = payload.get("msgid")

        if "cmd" in payload and "header" in payload and "data" in payload:

            cmd = payload["cmd"]
            if cmd == "httpresp":
                self.server.send_response(msgid, payload["header"], payload["data"], True)
                return

            if cmd == "logresp":
                self.server.send_response(msgid, payload["header"], payload["data"], False)
                return

            if cmd == "logevent":
                result = self.server.send_response(msgid, payload["header"], payload["data"], False)
                if not result:
                    msg = {"cmd": "logclose"}
                    self.tunnel.send(msg)
                return

        _log.error("Malformed %s" % payload)


class ControlTunnelProvider(object):
    """docstring for ControlTunnelProvider"""
    def __init__(self, name, cmd_map):
        super(ControlTunnelProvider, self).__init__()
        self.name = name
        self.cmd_map = cmd_map
        self.tunnel = None
        self.max_retries = _conf.get('global', 'storage_retries') or -1
        self.retries = 0

    def start(self, network, uri, proto, callback=None):
        self.network = network
        self.uri = uri
        self.proto = proto
        o = urlparse(self.uri)
        fqdn = socket.getfqdn(o.hostname)
        self._server_node_name = fqdn.encode('ascii').decode('unicode-escape') # TODO: Really?
        self.network.join([self.uri],
                               callback=CalvinCB(self._start_link_cb, org_cb=callback),
                               corresponding_server_node_names=[self._server_node_name])
        
    def _got_link(self, peer_node_id, org_cb):
        _log.debug("_got_link %s, %s" % (peer_node_id, org_cb))
        self.tunnel = self.proto.tunnel_new(peer_node_id, self.name, {})
        self.tunnel.register_tunnel_down(CalvinCB(self.tunnel_down, org_cb=org_cb))
        self.tunnel.register_tunnel_up(CalvinCB(self.tunnel_up, org_cb=org_cb))
        self.tunnel.register_recv(self.tunnel_recv_handler)

    def _start_link_cb(self, status, uri, peer_node_id, org_cb):
        if status != 200:
            self.retries += 1

            if self.max_retries - self.retries != 0:
                delay = 0.5 * self.retries if self.retries < 20 else 10
                _log.info("Link to proxy failed, retrying in {}".format(delay))
                asynchronous.DelayedCall(delay, self.network.join,
                    [self.uri], callback=CalvinCB(self._start_link_cb, org_cb=org_cb),
                    corresponding_server_node_names=[self._server_node_name])
                return
            else :
                _log.info("Link to proxy still failing, giving up")
                if org_cb:
                    org_cb(False)
                return

        # Got link set up tunnel
        self._got_link(peer_node_id, org_cb)        

    def tunnel_down(self, org_cb):
        """ Callback that the tunnel is not accepted or is going down """
        self.tunnel = None
        # FIXME assumes that the org_cb is the callback given by storage when starting, can only be called once
        # not future up/down
        if org_cb:
            org_cb(value=calvinresponse.CalvinResponse(False))
        # We should always return True which sends an ACK on the destruction of the tunnel
        return True

    def tunnel_up(self, org_cb):
        """ Callback that the tunnel is working """
        # FIXME assumes that the org_cb is the callback given by storage when starting, can only be called once
        # not future up/down
        if org_cb:
            org_cb(value=calvinresponse.CalvinResponse(True))
        # We should always return True which sends an ACK on the destruction of the tunnel
        return True

    def tunnel_recv_handler(self, payload):
        """ Gets called when a peer replies"""
        try:
            cmd = payload['cmd']
        except:
            _log.error("Missing 'cmd' in payload")
            return
        cmd_handler = self.cmd_map.get(cmd, self._bad_command)
        cmd_handler(payload)
            
    def _bad_command(self, payload):    
        _log.error(f"{self.__class__.__name__} received unknown command {payload['cmd']}")

    def send(self, msg):
        if not self.tunnel:
            _log.error(f"{self.__class__.__name__} send called but no tunnel connected")
            return
        self.tunnel.send(msg)

class CalvinControlTunnelClient(CalvinControlBase):
    """ A Calvin control tunnel client
    """
    def __init__(self, node, uri):
        super(CalvinControlTunnelClient, self).__init__(node, uri)
        _log.info("Control tunnel client with proxy %s" % uri)
        cmd_map = {
            'httpreq': self.handle_httpreq, 
            'started': self.handle_started, 
            'logclose': self.handle_logclose,
        }
        self.tunnel_provider = ControlTunnelProvider('control', cmd_map)

    def start(self):
        self.tunnel_provider.start(self.node.network, self.uri, self.node.proto)
        
    def stop(self):
        pass

    def send_response(self, handle, data, status=200, content_type=None):
        """ Send response header text/html
        """
        header, data = self.prepare_response(data, status, content_type)
        msg = {"cmd": "httpresp", "msgid": handle, "header": header, "data": data}
        self.tunnel_provider.send(msg)

    def send_streamheader(self, handle):
        """ Send response header for text/event-stream
        """
        response = self.prepare_streamheader()
        msg = {"cmd": "logresp", "msgid": handle, "header": response, "data": None}
        self.tunnel_provider.send(msg)

    def send_streamdata(self, handle, data):
        """ Send stream data
        """
        self.tunnel_provider.send({"cmd": "logevent", "msgid": handle, "header": None, "data": "data: %s\n\n" % data})

    def send_optionsheader(self, handle, hdr):
        """ Send response header for options
        """
        response = self.prepare_optionsheader()
        msg = {"cmd": "httpresp", "msgid": handle, "header": response, "data": None}
        self.tunnel_provider.send(msg)
    
    def handle_httpreq(self, payload):
        try:
            self.route_request(
                handle=payload["msgid"], 
                command=payload["command"], 
                headers=payload["headers"], 
                data=payload["data"]
            )
        except:
            _log.error(f"No route for message {payload['msgid']}")
            self.send_response(payload["msgid"], None, status=calvinresponse.INTERNAL_ERROR)

    def handle_started(self, payload):
        self.node.external_control_uri = payload["controluri"]
        # FIXME: Add node to storage when we get ACK that we have storage, not here!
        self.node.storage.add_node(self.node)

    def handle_logclose(self, payload):
        self.close_log_tunnel(payload["msg_id"])
