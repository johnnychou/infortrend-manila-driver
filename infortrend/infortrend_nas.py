# Copyright (c) 2017 Infortrend Technology, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from oslo_config import cfg
from oslo_log import log
from oslo_utils import excutils
from oslo_utils import importutils
from oslo_utils import units
from oslo_concurrency import processutils
import six

from manila.common import constants
from manila import exception
from manila.i18n import _, _LE, _LI, _LW
from manila.share import driver
from manila import utils as mutils

LOG = log.getLogger(__name__)
DEFAULT_RETRY_TIME = 5

def retry_cli(func):
    def inner(self, *args, **kwargs):
        total_retry_time = self.cli_retry_time

        if total_retry_time is None:
            total_retry_time = DEFAULT_RETRY_TIME

        retry_time = 0
        while retry_time < total_retry_time:
            rc, out = func(self, *args, **kwargs)
            retry_time += 1

            if rc == 0:
                break

            LOG.error(_LE(
                'Retry %(retry)s times: %(method)s Failed '
                '%(rc)s: %(reason)s'), {
                    'retry': retry_time,
                    'method': self.__class__.__name__,
                    'rc': rc,
                    'reason': out})
        LOG.debug(
            'Method: %(method)s Return Code: %(rc)s '
            'Output: %(out)s', {
                'method': self.__class__.__name__, 'rc': rc, 'out': out})
        return rc, out
    return inner

def bi_to_gi(bi_size):
    return bi_size / units.Gi


class InfortrendNAS(object):

    def __init__(self, nas_ip, username, password, ssh_key,
                 retries, timeout, pool_list):
        self.nas_ip = nas_ip
        self.username = username
        self.password = password
        self.ssh_key = ssh_key
        self.cli_retry_time = retries
        self.cli_timeout = timeout
        self.pool_list = pool_list
        self.command = ""
        self.sshpool = None
        self.location = 'a@0'

    def _execute(self, command_line):
        commands = ' '.join(command_line)
        mutils.check_ssh_injection(commands)
        LOG.debug('Executing: %(command)s', {'command': commands})

        rc, result = self._ssh_execute(commands)

        if rc != 0:
            msg = _('Failed to execute commands: [%(command)s].') % {
                        'command': commands}
            LOG.error(msg)
            raise exception.InfortrendNASException(
                err=msg, rc=rc, out=out)

        return result

    @retry_cli
    def _ssh_execute(self, commands):
        if not self.sshpool:
            self.sshpool = utils.SSHPool(ip=self.nas_ip,
                                         port=self.port,
                                         conn_timeout=None,
                                         login=self.username,
                                         password=self.password,
                                         privatekey=self.ssh_key)

        with self.sshpool.item() as ssh:
            try:
                out, err = processutils.ssh_execute(
                    ssh, commands, check_exit_code=True)
                rc, result = self._parser(out)
            except processutils.ProcessExecutionError as pe:
                rc = pe.exit_code
                result = pe.stdout
                result = result.replace('\n', '\\n')
                LOG.error(_LE(
                    'Error on execute ssh command. '
                    'Error code: %(exit_code)d Error msg: %(result)s'), {
                        'exit_code': pe.exit_code, 'result': result})

            return rc, result

    def _parser(self, content=None):

        content = content.replace("\r", "")
        content = content.strip()
        LOG.debug(content)

        if content:
            try:
                content_dict = eval(content)
            except:
                msg = _('Failed to parse data: %(content)s to dictionary') % {
                            'content': content}
                LOG.error(msg)
                raise exception.InfortrendNASException(err=msg)

            rc = int(content_dict['cliCode'][0]['Return'], 16)
            if rc == 0:
                result = content_dict['data']
            else:
                result = content_dict['cliCode'][0]['CLI']
        else:
            rc = -1
            result = None

        return rc, result

    def check_for_setup_error(self):
        self._check_pools_setup()

    def _check_pools_setup(self):
        pool_list = self.pool_list[:]
        pool_data = self._execute(command_line)
        for pool_info in pool_data:
            pool_name = self._extract_pool_name(pool_info)
            if pool_name in self.pool_list:
                pool_list.remove(pool_name)
            if len(pool_list) == 0:
                break

        if len(pool_list) != 0:
            msg = _('Please create %(pool_list)s pool in advance!') % {
                        'pool_list': pool_list}
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

    def _extract_pool_name(self, pool_info):
        return pool_info['directory'].split('/')[2]

    def _extract_lv_name(self, pool_info):
        return pool_info['directory'].split('/')[1]

    def update_pools_stats(self):
        pools = []
        command_line = ['folder', 'status', '-z', self.location]
        pools_data = self._execute(command_line)

        for pool_info in pools_data:
            pool_name = self._extract_pool_name(pool_info)

            if pool_name in self.pool_list:
                total_space = float(pool_info['size'])
                available_space = float(pool_info['free'])

                total_capacity_gb = round(bi_to_gi(total_space), 2)
                free_capacity_gb = round(bi_to_gi(available_space), 2)

                pool = {
                    'pool_name': pool_name,
                    'total_capacity_gb': total_capacity_gb,
                    'free_capacity_gb': free_capacity_gb,
                    'reserved_percentage': 0,
                    'qos': False,
                    'dedupe': False,
                    'compression': False,
                    'snapshot_support': False,
                    'thin_provisioning': False,
                    'replication_type': None,
                }
                pools.append(pool)

        return pools

    def create_folder(self):
        command_line = ['folder', 'options', pool_name, volume_name, '-c', share_name, '-z', self.location]
    
    def delete_folder(self):
        command_line = ['folder', 'options', pool_name, volume_name, '-d', share_name, '-z', self.location]

    def create_user(self):


    def allow_access(self):


    def deny_access(self):

