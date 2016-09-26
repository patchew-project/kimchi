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

import os
import string
from lxml import etree

from wok.exception import InvalidOperation, InvalidParameter, NotFoundError
from wok.exception import OperationFailed
from wok.utils import wok_log

from wok.plugins.kimchi.model.config import CapabilitiesModel
from wok.plugins.kimchi.model.diskutils import get_disk_used_by
from wok.plugins.kimchi.model.storagevolumes import StorageVolumeModel
from wok.plugins.kimchi.model.utils import get_vm_config_flag
from wok.plugins.kimchi.model.vms import DOM_STATE_MAP, VMModel
from wok.plugins.kimchi.osinfo import lookup
from wok.plugins.kimchi.utils import create_disk_image, is_s390x
from wok.plugins.kimchi.xmlutils.disk import get_device_node, get_disk_xml
from wok.plugins.kimchi.xmlutils.disk import get_vm_disk_info, get_vm_disks


HOTPLUG_TYPE = ['scsi', 'virtio']


def _get_device_bus(dev_type, dom):
    try:
        version, distro = VMModel.vm_get_os_metadata(dom)
    except:
        version, distro = ('unknown', 'unknown')
    return lookup(distro, version)[dev_type+'_bus']


class VMStoragesModel(object):
    def __init__(self, **kargs):
        self.conn = kargs['conn']
        self.objstore = kargs['objstore']
        self.caps = CapabilitiesModel(**kargs)

    def _get_available_bus_address(self, bus_type, vm_name):
        if bus_type not in ['ide']:
            return dict()
        # libvirt limitation of just 1 ide controller
        # each controller have at most 2 buses and each bus 2 units.
        dom = VMModel.get_vm(vm_name, self.conn)
        disks = self.get_list(vm_name)
        valid_id = [('0', '0'), ('0', '1'), ('1', '0'), ('1', '1')]
        controller_id = '0'
        for dev_name in disks:
            disk = get_device_node(dom, dev_name)
            if disk.target.attrib['bus'] == 'ide':
                controller_id = disk.address.attrib['controller']
                bus_id = disk.address.attrib['bus']
                unit_id = disk.address.attrib['unit']
                if (bus_id, unit_id) in valid_id:
                    valid_id.remove((bus_id, unit_id))
                    continue
        if not valid_id:
            raise OperationFailed('KCHVMSTOR0014E',
                                  {'type': 'ide', 'limit': 4})
        else:
            address = {'controller': controller_id,
                       'bus': valid_id[0][0], 'unit': valid_id[0][1]}
            return dict(address=address)

    def create(self, vm_name, params):
        vol_model = None
        # Path will never be blank due to API.json verification.
        # There is no need to cover this case here.
        if not ('vol' in params) ^ ('path' in params):

            if not is_s390x():
                raise InvalidParameter("KCHVMSTOR0017E")

            if 'dir_path' not in params:
                raise InvalidParameter("KCHVMSTOR0019E")

        dom = VMModel.get_vm(vm_name, self.conn)
        params['bus'] = _get_device_bus(params['type'], dom)

        if is_s390x() and params['type'] == 'disk' and 'dir_path' in params:
            if 'format' not in params:
                raise InvalidParameter("KCHVMSTOR0020E")
            size = params['size']
            name = params['name']
            dir_path = params.get('dir_path')
            params['path'] = dir_path + "/" + name
            if os.path.exists(params['path']):
                raise InvalidParameter("KCHVMSTOR0021E",
                                       {'disk_path': params['path']})
            create_disk_image(format_type=params['format'],
                              path=params['path'], capacity=size)
        else:
            params['format'] = 'raw'

        dev_list = [dev for dev, bus in get_vm_disks(dom).iteritems()
                    if bus == params['bus']]
        dev_list.sort()
        if len(dev_list) == 0:
            params['index'] = 0
        else:
            char = dev_list.pop()[2]
            params['index'] = string.ascii_lowercase.index(char) + 1

        if (params['bus'] not in HOTPLUG_TYPE and
           DOM_STATE_MAP[dom.info()[0]] != 'shutoff'):
            raise InvalidOperation('KCHVMSTOR0011E')

        if params.get('vol'):
            try:
                pool = params['pool']
                vol_model = StorageVolumeModel(conn=self.conn,
                                               objstore=self.objstore)
                vol_info = vol_model.lookup(pool, params['vol'])
            except KeyError:
                raise InvalidParameter("KCHVMSTOR0012E")
            except Exception as e:
                raise InvalidParameter("KCHVMSTOR0015E", {'error': e})
            if len(vol_info['used_by']) != 0:
                raise InvalidParameter("KCHVMSTOR0016E")

            valid_format = {
                "disk": ["raw", "qcow", "qcow2", "qed", "vmdk", "vpc"],
                "cdrom": "iso"}

            if vol_info['type'] == 'file':
                if (params['type'] == 'disk' and
                        vol_info['format'] in valid_format[params['type']]):
                    params['format'] = vol_info['format']
                else:
                    raise InvalidParameter("KCHVMSTOR0018E",
                                           {"format": vol_info['format'],
                                            "type": params['type']})

            if (params['format'] == 'raw' and not vol_info['isvalid']):
                message = 'This is not a valid RAW disk image.'
                raise OperationFailed('KCHVMSTOR0008E', {'error': message})

            params['path'] = vol_info['path']
            params['disk'] = vol_info['type']

        params.update(self._get_available_bus_address(params['bus'], vm_name))

        # Add device to VM
        dev, xml = get_disk_xml(params)
        try:
            dom = VMModel.get_vm(vm_name, self.conn)
            dom.attachDeviceFlags(xml, get_vm_config_flag(dom, 'all'))
        except Exception as e:
            raise OperationFailed("KCHVMSTOR0008E", {'error': e.message})

        # Don't put a try-block here. Let the exception be raised. If we
        #   allow disks used_by to be out of sync, data corruption could
        #   occour if a disk is added to two guests unknowingly.
        if params.get('vol'):
            used_by = vol_info['used_by']
            used_by.append(vm_name)

        return dev

    def get_list(self, vm_name):
        dom = VMModel.get_vm(vm_name, self.conn)
        return get_vm_disks(dom).keys()


class VMStorageModel(object):
    def __init__(self, **kargs):
        self.conn = kargs['conn']
        self.objstore = kargs['objstore']
        self.caps = CapabilitiesModel(**kargs)

    def lookup(self, vm_name, dev_name):
        # Retrieve disk xml and format return dict
        dom = VMModel.get_vm(vm_name, self.conn)
        return get_vm_disk_info(dom, dev_name)

    def delete(self, vm_name, dev_name):
        try:
            bus_type = self.lookup(vm_name, dev_name)['bus']
            dom = VMModel.get_vm(vm_name, self.conn)
        except NotFoundError:
            raise

        if (bus_type not in HOTPLUG_TYPE and
                DOM_STATE_MAP[dom.info()[0]] != 'shutoff'):
            raise InvalidOperation('KCHVMSTOR0011E')

        try:
            disk = get_device_node(dom, dev_name)
            path = get_vm_disk_info(dom, dev_name)['path']
            if path is None or len(path) < 1:
                path = self.lookup(vm_name, dev_name)['path']
            # This has to be done before it's detached. If it wasn't
            #   in the obj store, its ref count would have been updated
            #   by get_disk_used_by()
            if path is not None:
                used_by = get_disk_used_by(self.conn, path)
            else:
                wok_log.error("Unable to decrement volume used_by on"
                              " delete because no path could be found.")
            dom.detachDeviceFlags(etree.tostring(disk),
                                  get_vm_config_flag(dom, 'all'))
        except Exception as e:
            raise OperationFailed("KCHVMSTOR0010E", {'error': e.message})

        if used_by is not None and vm_name in used_by:
            used_by.remove(vm_name)
        else:
            wok_log.error("Unable to update %s:%s used_by on delete."
                          % (vm_name, dev_name))

    def update(self, vm_name, dev_name, params):
        old_disk_used_by = None
        new_disk_used_by = None

        dom = VMModel.get_vm(vm_name, self.conn)

        dev_info = self.lookup(vm_name, dev_name)
        if dev_info['type'] != 'cdrom':
            raise InvalidOperation("KCHVMSTOR0006E")

        params['path'] = params.get('path', '')
        old_disk_path = dev_info['path']
        new_disk_path = params['path']
        if new_disk_path != old_disk_path:
            # An empty path means a CD-ROM was empty or ejected:
            if old_disk_path is not '':
                old_disk_used_by = get_disk_used_by(self.conn, old_disk_path)
            if new_disk_path is not '':
                new_disk_used_by = get_disk_used_by(self.conn, new_disk_path)

        dev_info.update(params)
        dev, xml = get_disk_xml(dev_info)

        try:
            dom.updateDeviceFlags(xml, get_vm_config_flag(dom, 'all'))
        except Exception as e:
            raise OperationFailed("KCHVMSTOR0009E", {'error': e.message})

        try:
            if old_disk_used_by is not None and \
               vm_name in old_disk_used_by:
                old_disk_used_by.remove(vm_name)
            if new_disk_used_by is not None:
                new_disk_used_by.append(vm_name)
        except Exception as e:
            wok_log.error("Unable to update dev used_by on update due to"
                          " %s:" % e.message)
        return dev
