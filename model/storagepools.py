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

import libvirt
import lxml.etree as ET
from lxml.builder import E

from wok.asynctask import add_task
from wok.exception import InvalidOperation, MissingParameter
from wok.exception import NotFoundError, OperationFailed
from wok.utils import run_command, wok_log
from wok.xmlutils.utils import xpath_get_text

from wok.plugins.kimchi.config import config, get_kimchi_version, kimchiPaths
from wok.plugins.kimchi.model.config import CapabilitiesModel
from wok.plugins.kimchi.model.host import DeviceModel
from wok.plugins.kimchi.model.libvirtstoragepool import StoragePoolDef
from wok.plugins.kimchi.osinfo import defaults as tmpl_defaults
from wok.plugins.kimchi.scan import Scanner
from wok.plugins.kimchi.utils import pool_name_from_uri


ISO_POOL_NAME = u'kimchi_isos'

POOL_STATE_MAP = {0: 'inactive',
                  1: 'initializing',
                  2: 'active',
                  3: 'degraded',
                  4: 'inaccessible'}

# Types of pools supported
STORAGE_SOURCES = {'netfs': {'addr': '/pool/source/host/@name',
                             'path': '/pool/source/dir/@path'},
                   'iscsi': {'addr': '/pool/source/host/@name',
                             'port': '/pool/source/host/@port',
                             'path': '/pool/source/device/@path'},
                   'scsi': {'adapter_type': '/pool/source/adapter/@type',
                            'adapter_name': '/pool/source/adapter/@name',
                            'wwnn': '/pool/source/adapter/@wwnn',
                            'wwpn': '/pool/source/adapter/@wwpn'}}


class StoragePoolsModel(object):
    def __init__(self, **kargs):
        self.conn = kargs['conn']
        self.objstore = kargs['objstore']
        self.scanner = Scanner(self._clean_scan)
        self.scanner.delete()
        self.caps = CapabilitiesModel(**kargs)
        self.device = DeviceModel(**kargs)

        if self.conn.get() is not None:
            if self.conn.isQemuURI():
                self._check_default_pools()

    def _check_default_pools(self):
        pools = {}

        default_pool = tmpl_defaults['disks'][0]['pool']['name']
        default_pool = default_pool.split('/')[-1]

        pools[default_pool] = {}
        if default_pool == 'default':
            pools[default_pool] = {'path': '/var/lib/libvirt/images'}

        if config.get('kimchi', {}).get('create_iso_pool', False):
            pools['ISO'] = {'path': '/var/lib/kimchi/isos'}

        conn = self.conn.get()
        for pool_name in pools:
            error_msg = ("Storage pool %s does not exist or is not "
                         "active. Please, check the configuration in "
                         "%s/template.conf to ensure it lists only valid "
                         "networks." % (pool_name, kimchiPaths.sysconf_dir))
            try:
                pool = conn.storagePoolLookupByName(pool_name)
            except libvirt.libvirtError, e:
                pool_path = pools[pool_name].get('path')
                if pool_path is None:
                    msg = "Fatal: Unable to find storage pool %s. "
                    wok_log.error(msg % pool_name)
                    wok_log.error("Details: %s", e.message)
                    raise Exception(error_msg)

                # Try to create the pool
                pool = E.pool(E.name(pool_name), type='dir')
                pool.append(E.target(E.path(pool_path)))
                xml = ET.tostring(pool)
                try:
                    pool = conn.storagePoolDefineXML(xml, 0)
                except libvirt.libvirtError, e:
                    msg = "Fatal: Unable to create storage pool %s. "
                    wok_log.error(msg % pool_name)
                    wok_log.error("Details: %s", e.message)
                    raise Exception(error_msg)

                # Build and set autostart value to pool
                # Ignore error as the pool was already successfully created
                try:
                    # Add build step to make sure target directory created
                    # The build process may fail when the pool directory
                    # already exists on system
                    pool.build(libvirt.VIR_STORAGE_POOL_BUILD_NEW)
                    pool.setAutostart(1)
                except:
                    pass

            if pool.isActive() == 0:
                try:
                    pool.create(0)
                except libvirt.libvirtError, e:
                    msg = "Fatal: Unable to craete storage pool %s. "
                    wok_log.error(msg % pool_name)
                    wok_log.error("Details: %s", e.message)
                    raise Exception(error_msg)

    def get_list(self):
        try:
            conn = self.conn.get()
            names = conn.listStoragePools()
            names += conn.listDefinedStoragePools()
            return sorted(map(lambda x: x.decode('utf-8'), names))
        except libvirt.libvirtError as e:
            raise OperationFailed("KCHPOOL0006E",
                                  {'err': e.get_error_message()})

    def _check_lvm(self, name, from_vg):
        vgdisplay_cmd = ['vgdisplay', name.encode('utf-8')]
        output, error, returncode = run_command(vgdisplay_cmd)
        # From vgdisplay error codes:
        # 1  error reading VGDA
        # 2  volume group doesn't exist
        # 3  not all physical volumes of volume group online
        # 4  volume group not found
        # 5  no volume groups found at all
        # 6  error reading VGDA from lvmtab
        if from_vg and returncode in [2, 4, 5]:
            raise InvalidOperation("KCHPOOL0038E", {'name': name})

        if not from_vg and returncode not in [2, 4, 5]:
            raise InvalidOperation("KCHPOOL0036E", {'name': name})

    def create(self, params):
        task_id = None
        conn = self.conn.get()
        from_vg = params.get('source', {}).get('from_vg', False)

        try:
            name = params['name']
            if name == ISO_POOL_NAME:
                raise InvalidOperation("KCHPOOL0031E")

            # The user may want to create a logical pool with the same name
            # used before but a volume group will already exist with this name
            # So check the volume group does not exist to create the pool
            if params['type'] == 'logical':
                self._check_lvm(name, from_vg)

            if params['type'] == 'kimchi-iso':
                task_id = self._do_deep_scan(params)

            if params['type'] == 'scsi':
                adapter_name = params['source']['adapter_name']
                extra_params = self.device.lookup(adapter_name)
                # Adds name, adapter_type, wwpn and wwnn to source information
                params['source'].update(extra_params)
                params['fc_host_support'] = self.caps.fc_host_support

            poolDef = StoragePoolDef.create(params)
            poolDef.prepare(conn)
            xml = poolDef.xml.encode("utf-8")
        except KeyError, item:
            raise MissingParameter("KCHPOOL0004E",
                                   {'item': str(item), 'name': name})

        if name in self.get_list():
            raise InvalidOperation("KCHPOOL0001E", {'name': name})

        try:
            if task_id:
                # Create transient pool for deep scan
                conn.storagePoolCreateXML(xml, 0)
                return name

            pool = conn.storagePoolDefineXML(xml, 0)
        except libvirt.libvirtError as e:
            wok_log.error("Problem creating Storage Pool: %s", e)
            raise OperationFailed("KCHPOOL0007E",
                                  {'name': name, 'err': e.get_error_message()})

        # Build and set autostart value to pool
        # Ignore error as the pool was already successfully created
        # The build process fails when the pool directory already exists
        try:
            if params['type'] in ['logical', 'dir', 'netfs', 'scsi']:
                pool.build(libvirt.VIR_STORAGE_POOL_BUILD_NEW)
                pool.setAutostart(1)
            else:
                pool.setAutostart(0)
        except:
            pass

        if params['type'] == 'netfs':
            output, error, returncode = run_command(['setsebool', '-P',
                                                    'virt_use_nfs=1'])
            if error or returncode:
                wok_log.error("Unable to set virt_use_nfs=1. If you use "
                              "SELinux, this may prevent NFS pools from "
                              "being used.")
        return name

    def _clean_scan(self, pool_name):
        try:
            conn = self.conn.get()
            pool = conn.storagePoolLookupByName(pool_name.encode("utf-8"))
            pool.destroy()
            with self.objstore as session:
                session.delete('scanning', pool_name)
        except Exception, e:
            err = "Exception %s occured when cleaning scan result"
            wok_log.debug(err % e.message)

    def _do_deep_scan(self, params):
        scan_params = dict(ignore_list=[])
        scan_params['scan_path'] = params['path']
        params['type'] = 'dir'

        for pool in self.get_list():
            try:
                res = StoragePoolModel(conn=self.conn,
                                       objstore=self.objstore).lookup(pool)
                if res['state'] == 'active':
                    scan_params['ignore_list'].append(res['path'])
            except Exception, e:
                err = "Exception %s occured when get ignore path"
                wok_log.debug(err % e.message)

        params['path'] = self.scanner.scan_dir_prepare(params['name'])
        scan_params['pool_path'] = params['path']
        task_id = add_task('/plugins/kimchi/storagepools/%s' % ISO_POOL_NAME,
                           self.scanner.start_scan, self.objstore, scan_params)
        # Record scanning-task/storagepool mapping for future querying
        try:
            with self.objstore as session:
                session.store('scanning', params['name'], task_id,
                              get_kimchi_version())
            return task_id
        except Exception as e:
            raise OperationFailed('KCHPOOL0037E', {'err': e.message})


class StoragePoolModel(object):
    def __init__(self, **kargs):
        self.conn = kargs['conn']
        self.objstore = kargs['objstore']

    @staticmethod
    def get_storagepool(name, conn):
        conn = conn.get()
        try:
            return conn.storagePoolLookupByName(name.encode("utf-8"))
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_STORAGE_POOL:
                raise NotFoundError("KCHPOOL0002E", {'name': name})
            else:
                raise

    def _get_storagepool_vols_num(self, pool):
        if not pool.isActive():
            return 0

        try:
            pool.refresh(0)

        except Exception, e:
            wok_log.error("Pool refresh failed: %s" % str(e))

        return pool.numOfVolumes()

    def _get_storage_source(self, pool_type, pool_xml):
        source = {}
        if pool_type not in STORAGE_SOURCES:
            return source

        for key, val in STORAGE_SOURCES[pool_type].items():
            res = xpath_get_text(pool_xml, val)
            if len(res) == 1:
                source[key] = res[0]
            elif len(res) == 0:
                source[key] = ""
            else:
                source[key] = res
        return source

    def _nfs_status_online(self, pool, poolArgs=None):
        if not poolArgs:
            xml = pool.XMLDesc(0)
            pool_type = xpath_get_text(xml, "/pool/@type")[0]
            source = self._get_storage_source(pool_type, xml)
            poolArgs = {}
            poolArgs['name'] = pool.name()
            poolArgs['type'] = pool_type
            poolArgs['source'] = {'path': source['path'],
                                  'host': source['addr']}
        conn = self.conn.get()
        poolDef = StoragePoolDef.create(poolArgs)
        try:
            poolDef.prepare(conn)
            return True
        except Exception:
            return False

    def lookup(self, name):
        pool = self.get_storagepool(name, self.conn)
        info = pool.info()
        autostart = True if pool.autostart() else False
        persistent = True if pool.isPersistent() else False
        xml = pool.XMLDesc(0)
        path = xpath_get_text(xml, "/pool/target/path")[0]
        pool_type = xpath_get_text(xml, "/pool/@type")[0]
        source = self._get_storage_source(pool_type, xml)
        # FIXME: nfs workaround - prevent any libvirt operation
        # for a nfs if the corresponding NFS server is down.
        if pool_type == 'netfs' and not self._nfs_status_online(pool):
            wok_log.debug("NFS pool %s is offline, reason: NFS "
                          "server %s is unreachable.", name, source['addr'])
            # Mark state as '4' => inaccessible.
            info[0] = 4
            # skip calculating volumes
            nr_volumes = 0
        else:
            nr_volumes = self._get_storagepool_vols_num(pool)

        res = {'state': POOL_STATE_MAP[info[0]],
               'path': path,
               'source': source,
               'type': pool_type,
               'autostart': autostart,
               'capacity': info[1],
               'allocated': info[2],
               'available': info[3],
               'nr_volumes': nr_volumes,
               'persistent': persistent,
               'in_use': self._pool_used_by_template(name)}

        if not pool.isPersistent():
            # Deal with deep scan generated pool
            try:
                with self.objstore as session:
                    task_id = session.get('scanning', name)
                res['task_id'] = str(task_id)
                res['type'] = 'kimchi-iso'
            except NotFoundError:
                # User created normal pool
                pass
        return res

    def _update_lvm_disks(self, pool_name, disks):
        # check if all the disks/partitions exists in the host
        for disk in disks:
            lsblk_cmd = ['lsblk', disk]
            output, error, returncode = run_command(lsblk_cmd)
            if returncode != 0:
                wok_log.error('%s is not a valid disk/partition. Could not '
                              'add it to the pool %s.', disk, pool_name)
                raise OperationFailed('KCHPOOL0027E', {'disk': disk,
                                                       'pool': pool_name})
        # add disks to the lvm pool using vgextend + virsh refresh
        vgextend_cmd = ["vgextend", pool_name]
        vgextend_cmd += disks
        output, error, returncode = run_command(vgextend_cmd)
        if returncode != 0:
            msg = "Could not add disks to pool %s, error: %s"
            wok_log.error(msg, pool_name, error)
            raise OperationFailed('KCHPOOL0028E', {'pool': pool_name,
                                                   'err': error})
        # refreshing pool state
        pool = self.get_storagepool(pool_name, self.conn)
        if pool.isActive():
            pool.refresh(0)

    def update(self, name, params):
        pool = self.get_storagepool(name, self.conn)
        if 'autostart' in params:
            if params['autostart']:
                pool.setAutostart(1)
            else:
                pool.setAutostart(0)

        if 'disks' in params:
            # check if pool is type 'logical'
            xml = pool.XMLDesc(0)
            pool_type = xpath_get_text(xml, "/pool/@type")[0]
            if pool_type != 'logical':
                raise InvalidOperation('KCHPOOL0029E')
            self._update_lvm_disks(name, params['disks'])
        ident = pool.name()
        return ident.decode('utf-8')

    def activate(self, name):
        pool = self.get_storagepool(name, self.conn)
        # FIXME: nfs workaround - do not activate a NFS pool
        # if the NFS server is not reachable.
        xml = pool.XMLDesc(0)
        pool_type = xpath_get_text(xml, "/pool/@type")[0]
        if pool_type == 'netfs' and not self._nfs_status_online(pool):
            # block the user from activating the pool.
            source = self._get_storage_source(pool_type, xml)
            raise OperationFailed("KCHPOOL0032E",
                                  {'name': name, 'server': source['addr']})
            return
        try:
            pool.create(0)
        except libvirt.libvirtError as e:
            raise OperationFailed("KCHPOOL0009E",
                                  {'name': name, 'err': e.get_error_message()})

    def _pool_used_by_template(self, pool_name):
        with self.objstore as session:
            templates = session.get_list('template')
            for tmpl in templates:
                t_info = session.get('template', tmpl)
                for disk in t_info['disks']:
                    t_pool = disk['pool']['name']
                    if pool_name_from_uri(t_pool) == pool_name:
                        return True
            return False

    def deactivate(self, name):
        if self._pool_used_by_template(name):
            raise InvalidOperation('KCHPOOL0034E', {'name': name})

        pool = self.get_storagepool(name, self.conn)
        # FIXME: nfs workaround - do not try to deactivate a NFS pool
        # if the NFS server is not reachable.
        xml = pool.XMLDesc(0)
        pool_type = xpath_get_text(xml, "/pool/@type")[0]
        if pool_type == 'netfs' and not self._nfs_status_online(pool):
            # block the user from dactivating the pool.
            source = self._get_storage_source(pool_type, xml)
            raise OperationFailed("KCHPOOL0033E",
                                  {'name': name, 'server': source['addr']})
            return
        try:
            persistent = pool.isPersistent()
            pool.destroy()
        except libvirt.libvirtError as e:
            raise OperationFailed("KCHPOOL0010E",
                                  {'name': name, 'err': e.get_error_message()})
        # If pool was not persistent, then it was erased by destroy() and
        # must return nothing here, to trigger _redirect() and avoid errors
        if not persistent:
            return ""

    def delete(self, name):
        if self._pool_used_by_template(name):
            raise InvalidOperation('KCHPOOL0035E', {'name': name})

        pool = self.get_storagepool(name, self.conn)
        if pool.isActive():
            raise InvalidOperation("KCHPOOL0005E", {'name': name})
        try:
            pool.undefine()
        except libvirt.libvirtError as e:
            raise OperationFailed("KCHPOOL0011E",
                                  {'name': name, 'err': e.get_error_message()})


class IsoPoolModel(object):
    def __init__(self, **kargs):
        pass

    def lookup(self, name):
        return {'state': 'active',
                'type': 'kimchi-iso'}
