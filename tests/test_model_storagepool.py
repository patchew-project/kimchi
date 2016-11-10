# -*- coding: utf-8 -*-
#
# Project Kimchi
#
# Copyright IBM Corp, 2015-2016
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

import json
import os
import shutil
import tempfile
import unittest
from functools import partial

from wok.rollbackcontext import RollbackContext

from wok.plugins.kimchi.model.model import Model

from tests.utils import patch_auth, request
from tests.utils import run_server


model = None
test_server = None


def setUpModule():
    global test_server, model

    patch_auth()
    model = Model(None, '/tmp/obj-store-test')
    test_server = run_server(test_mode=True, model=model)


def tearDownModule():
    test_server.stop()
    os.unlink('/tmp/obj-store-test')


class StoragepoolTests(unittest.TestCase):
    def setUp(self):
        self.request = partial(request)

    def test_get_storagepools(self):
        storagepools = json.loads(
            self.request('/plugins/kimchi/storagepools').read()
        )
        self.assertIn('default', [pool['name'] for pool in storagepools])

        with RollbackContext() as rollback:
            # Now add a couple of storage pools
            for i in xrange(3):
                name = u'kīмсhī-storagepool-%i' % i
                path = '/var/lib/libvirt/images/%i' % i
                req = json.dumps({'name': name, 'type': 'dir', 'path': path})
                resp = self.request('/plugins/kimchi/storagepools', req,
                                    'POST')
                rollback.prependDefer(model.storagepool_delete, name)
                rollback.prependDefer(shutil.rmtree, path)

                self.assertEquals(201, resp.status)

                # Pool name must be unique
                req = json.dumps({'name': name, 'type': 'dir',
                                  'path': '/var/lib/libvirt/images/%i' % i})
                resp = self.request('/plugins/kimchi/storagepools', req,
                                    'POST')
                self.assertEquals(400, resp.status)

                # Verify pool information
                resp = self.request('/plugins/kimchi/storagepools/%s' %
                                    name.encode("utf-8"))
                p = json.loads(resp.read())
                keys = [u'name', u'state', u'capacity', u'allocated',
                        u'available', u'path', u'source', u'type',
                        u'nr_volumes', u'autostart', u'persistent', 'in_use']
                self.assertEquals(sorted(keys), sorted(p.keys()))
                self.assertEquals(name, p['name'])
                self.assertEquals('inactive', p['state'])
                self.assertEquals(True, p['persistent'])
                self.assertEquals(True, p['autostart'])
                self.assertEquals(0, p['nr_volumes'])

            pools = json.loads(
                self.request('/plugins/kimchi/storagepools').read()
            )
            self.assertEquals(len(storagepools) + 3, len(pools))

            # Create a pool with an existing path
            tmp_path = tempfile.mkdtemp(dir='/var/lib/kimchi')
            rollback.prependDefer(os.rmdir, tmp_path)
            req = json.dumps({'name': 'existing_path', 'type': 'dir',
                              'path': tmp_path})
            resp = self.request('/plugins/kimchi/storagepools', req, 'POST')
            rollback.prependDefer(model.storagepool_delete, 'existing_path')
            self.assertEquals(201, resp.status)

            # Reserved pool return 400
            req = json.dumps({'name': 'kimchi_isos', 'type': 'dir',
                              'path': '/var/lib/libvirt/images/%i' % i})
            resp = request('/plugins/kimchi/storagepools', req, 'POST')
            self.assertEquals(400, resp.status)
