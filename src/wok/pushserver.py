#
# Project Wok
#
# Copyright IBM Corp, 2017
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#

import cherrypy
import os
import select
import socket
import threading

import websocket
from utils import wok_log


BASE_DIRECTORY = '/run'
TOKEN_NAME = 'woknotifications'


class PushServer(object):

    def set_socket_file(self):
        if not os.path.isdir(BASE_DIRECTORY):
            try:
                os.mkdir(BASE_DIRECTORY)
            except OSError:
                raise RuntimeError('PushServer base UNIX socket dir %s '
                                   'not found.' % BASE_DIRECTORY)

        self.server_addr = os.path.join(BASE_DIRECTORY, TOKEN_NAME)

        if os.path.exists(self.server_addr):
            try:
                os.remove(self.server_addr)
            except:
                raise RuntimeError('There is an existing connection in %s' %
                                   self.server_addr)

    def __init__(self):
        self.set_socket_file()

        websocket.add_proxy_token(TOKEN_NAME, self.server_addr, True)

        self.connections = []

        self.server_running = True
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET,
                                      socket.SO_REUSEADDR, 1)
        self.server_socket.bind(self.server_addr)
        self.server_socket.listen(10)
        wok_log.info('Push server created on address %s' % self.server_addr)

        self.connections.append(self.server_socket)
        cherrypy.engine.subscribe('stop', self.close_server, 1)

        server_loop = threading.Thread(target=self.listen)
        server_loop.start()

    def listen(self):
        try:
            while self.server_running:
                read_ready, _, _ = select.select(self.connections,
                                                 [], [], 1)
                for sock in read_ready:
                    if not self.server_running:
                        break

                    if sock == self.server_socket:

                        new_socket, addr = self.server_socket.accept()
                        self.connections.append(new_socket)
                    else:
                        try:
                            data = sock.recv(4096)
                        except:
                            try:
                                self.connections.remove(sock)
                            except ValueError:
                                pass

                            continue
                        if data and data == 'CLOSE':
                            sock.send('ACK')
                            try:
                                self.connections.remove(sock)
                            except ValueError:
                                pass
                            sock.close()

        except Exception as e:
            raise RuntimeError('Exception ocurred in listen() of pushserver '
                               'module: %s' % e.message)

    def send_notification(self, message):
        for sock in self.connections:
            if sock != self.server_socket:
                try:
                    sock.send(message)
                except IOError as e:
                    if 'Broken pipe' in str(e):
                        sock.close()
                        try:
                            self.connections.remove(sock)
                        except ValueError:
                            pass

    def close_server(self):
        try:
            self.server_running = False
            self.server_socket.shutdown(socket.SHUT_RDWR)
            self.server_socket.close()
            os.remove(self.server_addr)
        except:
            pass
        finally:
            cherrypy.engine.unsubscribe('stop', self.close_server)
