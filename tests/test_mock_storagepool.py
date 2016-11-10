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
import unittest
from functools import partial

from tests.utils import patch_auth, request, run_server

from wok.plugins.kimchi.mockmodel import MockModel


model = None
test_server = None


def setUpModule():
    global test_server, model

    patch_auth()
    model = MockModel('/tmp/obj-store-test')
    test_server = run_server(test_mode=True, model=model)


def tearDownModule():
    test_server.stop()
    os.unlink('/tmp/obj-store-test')


class MockStoragepoolTests(unittest.TestCase):
    def setUp(self):
        self.request = partial(request)
        model.reset()

    def _task_lookup(self, taskid):
        return json.loads(
            self.request('/plugins/kimchi/tasks/%s' % taskid).read()
        )

    def test_storagepool(self):
        # MockModel always returns 2 VGs (hostVG, kimchiVG)
        vgs = json.loads(self.request('/plugins/kimchi/host/vgs').read())
        vg_names = [vg['name'] for vg in vgs]

        # MockModel always returns 2 partitions (vdx, vdz)
        partitions = json.loads(
            self.request('/plugins/kimchi/host/partitions').read()
        )
        devs = [dev['path'] for dev in partitions]

        # MockModel always returns 3 FC devices
        fc_devs = json.loads(
            self.request('/plugins/kimchi/host/devices?_cap=fc_host').read()
        )
        fc_devs = [dev['name'] for dev in fc_devs]

        poolDefs = [
            {'type': 'dir', 'name': u'kīмсhīUnitTestDirPool',
             'path': '/tmp/kimchi-images'},
            {'type': 'netfs', 'name': u'kīмсhīUnitTestNSFPool',
             'source': {'host': 'localhost',
                        'path': '/var/lib/kimchi/nfs-pool'}},
            {'type': 'scsi', 'name': u'kīмсhīUnitTestSCSIFCPool',
             'source': {'adapter_name': fc_devs[0]}},
            {'type': 'iscsi', 'name': u'kīмсhīUnitTestISCSIPool',
             'source': {'host': '127.0.0.1',
                        'target': 'iqn.2015-01.localhost.kimchiUnitTest'}},
            {'type': 'logical', 'name': u'kīмсhīUnitTestLogicalPool',
             'source': {'devices': [devs[0]]}},
            {'type': 'logical', 'name': vg_names[0],
             'source': {'from_vg': True}}]

        def _do_test(params):
            name = params['name']
            uri = '/plugins/kimchi/storagepools/%s' % name.encode('utf-8')

            req = json.dumps(params)
            resp = self.request('/plugins/kimchi/storagepools', req, 'POST')
            self.assertEquals(201, resp.status)

            # activate the storage pool
            resp = self.request(uri + '/activate', '{}', 'POST')
            storagepool = json.loads(self.request(uri).read())
            self.assertEquals('active', storagepool['state'])

            # Set autostart flag of an active storage pool
            for autostart in [True, False]:
                t = {'autostart': autostart}
                req = json.dumps(t)
                resp = self.request(uri, req, 'PUT')
                storagepool = json.loads(self.request(uri).read())
                self.assertEquals(autostart, storagepool['autostart'])

            # Extend an active logical pool
            if params['type'] == 'logical':
                t = {'disks': [devs[1]]}
                req = json.dumps(t)
                resp = self.request(uri, req, 'PUT')
                self.assertEquals(200, resp.status)

            # Deactivate the storage pool
            resp = self.request(uri + '/deactivate', '{}', 'POST')
            storagepool = json.loads(self.request(uri).read())
            self.assertEquals('inactive', storagepool['state'])

            # Set autostart flag of an inactive storage pool
            for autostart in [True, False]:
                t = {'autostart': autostart}
                req = json.dumps(t)
                resp = self.request(uri, req, 'PUT')
                storagepool = json.loads(self.request(uri).read())
                self.assertEquals(autostart, storagepool['autostart'])

            # Extend an inactive logical pool
            if params['type'] == 'logical':
                t = {'disks': [devs[1]]}
                req = json.dumps(t)
                resp = self.request(uri, req, 'PUT')
                self.assertEquals(200, resp.status)

            # Delete the storage pool
            resp = self.request(uri, '{}', 'DELETE')
            self.assertEquals(204, resp.status)

        for pool in poolDefs:
            _do_test(pool)
