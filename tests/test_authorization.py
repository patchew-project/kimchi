#
# Project Kimchi
#
# Copyright IBM Corp, 2014-2016
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

from tests.utils import get_fake_user, patch_auth
from tests.utils import request, run_server, wait_task

from wok.plugins.kimchi import mockmodel

from iso_gen import construct_fake_iso


test_server = None
model = None
fake_iso = '/tmp/fake.iso'


def setUpModule():
    global test_server, model

    patch_auth(sudo=False)
    model = mockmodel.MockModel('/tmp/obj-store-test')
    test_server = run_server(test_mode=True, model=model)

    # Create fake ISO to do the tests
    construct_fake_iso(fake_iso, True, '12.04', 'ubuntu')


def tearDownModule():
    test_server.stop()
    os.unlink('/tmp/obj-store-test')
    os.unlink(fake_iso)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.request = partial(request)
        model.reset()

    def test_nonroot_access(self):
        # Non-root users can not create or delete network (only get)
        resp = self.request('/plugins/kimchi/networks', '{}', 'GET')
        self.assertEquals(200, resp.status)
        resp = self.request('/plugins/kimchi/networks', '{}', 'POST')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/networks/default/activate', '{}',
                            'POST')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/networks/default', '{}', 'DELETE')
        self.assertEquals(403, resp.status)

        # Non-root users can not create or delete storage pool (only get)
        resp = self.request('/plugins/kimchi/storagepools', '{}', 'GET')
        self.assertEquals(200, resp.status)
        resp = self.request('/plugins/kimchi/storagepools', '{}', 'POST')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/storagepools/default/activate',
                            '{}', 'POST')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/storagepools/default', '{}',
                            'DELETE')
        self.assertEquals(403, resp.status)

        # Non-root users can not update or delete a template
        # but he can get and create a new one
        resp = self.request('/plugins/kimchi/templates', '{}', 'GET')
        self.assertEquals(403, resp.status)
        req = json.dumps({'name': 'test', 'source_media': fake_iso})
        resp = self.request('/plugins/kimchi/templates', req, 'POST')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/templates/test', '{}', 'PUT')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/templates/test', '{}', 'DELETE')
        self.assertEquals(403, resp.status)

        # Non-root users can only get vms authorized to them
        model.templates_create({'name': u'test',
                                'source_media': {'type': 'disk',
                                                 'path': fake_iso}})

        task_info = model.vms_create({
            'name': u'test-me',
            'template': '/plugins/kimchi/templates/test'
        })
        wait_task(model.task_lookup, task_info['id'])

        fake_user = get_fake_user()

        model.vm_update(u'test-me',
                        {'users': [fake_user.keys()[0]],
                         'groups': []})

        task_info = model.vms_create({
            'name': u'test-usera',
            'template': '/plugins/kimchi/templates/test'
        })
        wait_task(model.task_lookup, task_info['id'])

        non_root = list(set(model.users_get_list()) - set(['root']))[0]
        model.vm_update(u'test-usera', {'users': [non_root], 'groups': []})

        task_info = model.vms_create({
            'name': u'test-groupa',
            'template': '/plugins/kimchi/templates/test'
        })
        wait_task(model.task_lookup, task_info['id'])
        a_group = model.groups_get_list()[0]
        model.vm_update(u'test-groupa', {'groups': [a_group]})

        resp = self.request('/plugins/kimchi/vms', '{}', 'GET')
        self.assertEquals(200, resp.status)
        vms_data = json.loads(resp.read())
        self.assertEquals([u'test-groupa', u'test-me'],
                          sorted([v['name'] for v in vms_data]))
        resp = self.request('/plugins/kimchi/vms', req, 'POST')
        self.assertEquals(403, resp.status)

        # Create a vm using mockmodel directly to test Resource access
        task_info = model.vms_create({
            'name': 'kimchi-test',
            'template': '/plugins/kimchi/templates/test'
        })
        wait_task(model.task_lookup, task_info['id'])
        resp = self.request('/plugins/kimchi/vms/kimchi-test', '{}', 'PUT')
        self.assertEquals(403, resp.status)
        resp = self.request('/plugins/kimchi/vms/kimchi-test', '{}', 'DELETE')
        self.assertEquals(403, resp.status)

        # Non-root users can only update VMs authorized by them
        resp = self.request('/plugins/kimchi/vms/test-me/start', '{}', 'POST')
        self.assertEquals(200, resp.status)
        resp = self.request('/plugins/kimchi/vms/test-usera/start', '{}',
                            'POST')
        self.assertEquals(403, resp.status)

        model.template_delete('test')
        model.vm_delete('test-me')
