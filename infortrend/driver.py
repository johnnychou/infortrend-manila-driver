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

from oslo_config import cfg
from oslo_log import log

from manila.share.drivers.infortrend import infortrend_nas
from manila import exception
from manila.i18n import _
from manila.share import driver

LOG = log.getLogger(__name__)

infortrend_nas_opts = [
    cfg.StrOpt('infortrend_nas_ip',
               default=None,
               help='Infortrend nas ip. '
               'It is the ip for management.'),
    cfg.StrOpt('infortrend_nas_user',
               default='manila',
               help='Infortrend nas username.'),
    cfg.StrOpt('infortrend_nas_password',
               default=None,
               help='Infortrend nas password. '
               'This is not necessary '
               'if infortrend_nas_ssh_key is set.'),
    cfg.StrOpt('infortrend_nas_ssh_key',
               default=None,
               help='Infortrend nas ssh key.'),
    cfg.StrOpt('infortrend_share_pools',
               default=None,
               help='Infortrend nas pool name list. '
               'It is separated with comma.'),
    cfg.StrOpt('infortrend_share_channels',
               default=None,
               help='Infortrend channels for file service. '
               'It is separated with comma.'),
    cfg.IntOpt('infortrend_cli_max_retries',
               default=5,
               help='Maximum retry times for cli.'),
    cfg.IntOpt('infortrend_cli_timeout',
               default=30,
               help='CLI timeout in seconds.'),
]

CONF = cfg.CONF
CONF.register_opts(infortrend_nas_opts)


class InfortrendNASDriver(driver.ShareDriver):

    """Infortrend Share Driver for GS/GSe Family using NASCLI.

    Version history:
        1.0.0 - Initial driver
    """

    VERSION = "1.0.0"
    PROTOCOL = "NFS_CIFS"

    def __init__(self, *args, **kwargs):
        super(InfortrendNASDriver, self).__init__(False, *args, **kwargs)
        self.configuration.append_config_values(infortrend_nas_opts)

        nas_ip = self.configuration.safe_get('infortrend_nas_ip')
        username = self.configuration.safe_get('infortrend_nas_user')
        password = self.configuration.safe_get('infortrend_nas_password')
        ssh_key = self.configuration.safe_get('infortrend_nas_ssh_key')
        retries = self.configuration.safe_get('infortrend_cli_max_retries')
        timeout = self.configuration.safe_get('infortrend_cli_timeout')
        self.backend_name = self.configuration.safe_get('share_backend_name')

        if not nas_ip:
            msg = _('The infortrend_nas_ip is not set.')
            raise exception.InvalidParameterValue(err=msg)

        if not (password or ssh_key):
            msg = _('Either infortrend_nas_password or infortrend_nas_ssh_key '
                    'should be set.')
            raise exception.InvalidParameterValue(err=msg)

        pool_dict = self._init_pool_dict()
        channel_dict = self._init_channel_dict()
        self.ift_nas = infortrend_nas.InfortrendNAS(nas_ip, username, password,
                                                    ssh_key, retries, timeout,
                                                    pool_dict, channel_dict)

    def _init_pool_dict(self):
        temp_pool_dict = {}
        pools_name = self.configuration.safe_get('infortrend_share_pools')
        if not pools_name:
            msg = _('The infortrend_share_pools is not set.')
            raise exception.InvalidParameterValue(err=msg)

        tmp_pool_list = pools_name.split(',')
        for pool in tmp_pool_list:
            temp_pool_dict[pool.strip()] = {}

        return temp_pool_dict

    def _init_channel_dict(self):
        temp_ch_dict = {}
        channels = self.configuration.safe_get('infortrend_share_channels')
        if not channels:
            msg = _('The infortrend_share_channels is not set.')
            raise exception.InvalidParameterValue(err=msg)

        tmp_ch_list = channels.split(',')
        for channel in tmp_ch_list:
            temp_ch_dict[channel.strip()] = ''

        return temp_ch_dict

    def do_setup(self, context):
        """Any initialization the share driver does while starting."""
        LOG.debug('Infortrend NAS do_setup start.')
        self.ift_nas.do_setup()

    def check_for_setup_error(self):
        """Check for setup error."""
        LOG.debug('Infortrend NAS check_for_setup_error start.')
        self.ift_nas.check_for_setup_error()

    def _update_share_stats(self):
        """Retrieve stats info from share group."""

        LOG.debug('Updating Infortrend share stats.')

        data = dict(share_backend_name=self.backend_name,
                    vendor_name='Infortrend',
                    driver_version=self.VERSION,
                    storage_protocol=self.PROTOCOL,
                    total_capacity_gb=0.0,
                    free_capacity_gb=0.0,
                    reserved_percentage=0,
                    pools=self.ift_nas.update_pools_stats())
        LOG.debug('Infortrend pools status: %s' % data['pools'])

        super(InfortrendNASDriver, self)._update_share_stats(data)

    def update_access(self, context, share, access_rules, add_rules,
                      delete_rules, share_server=None):
        """Update access rules for given share.

        :param context: Current context
        :param share: Share model with share data.
        :param access_rules: All access rules for given share
        :param add_rules: Empty List or List of access rules which should be
               added. access_rules already contains these rules.
        :param delete_rules: Empty List or List of access rules which should be
               removed. access_rules doesn't contain these rules.
        :param share_server: Not used by this driver.

        :returns: None, or a dictionary of ``access_id``, ``access_key`` as
                  key: value pairs for the rules added, where, ``access_id``
                  is the UUID (string) of the access rule, and ``access_key``
                  is the credential (string) of the entity granted access.
                  During recovery after error, the returned dictionary must
                  contain ``access_id``, ``access_key`` for all the rules that
                  the driver is ordered to resync, i.e. rules in the
                  ``access_rules`` parameter.
        """
        LOG.debug(
            'Update access rules for share: %(share)s, '
            'access_rules: %(access_rules)s, '
            'add_rules: %(add_rules)s, '
            'delete_rules: %(delete_rules)s', {
                'share': dict(share),
                'access_rules': self._list_of_dict(access_rules),
                'add_rules': self._list_of_dict(add_rules),
                'delete_rules': self._list_of_dict(delete_rules),
            })
        return self.ift_nas.update_access(share, access_rules, add_rules,
                                          delete_rules, share_server)

    def _list_of_dict(self, list_of_dict):
        temp_list = []
        for data in list_of_dict:
            temp_dict = dict(data)
            temp_list.append(temp_dict)
        return temp_list

    def create_share(self, context, share, share_server=None):
        """Is called to create share."""

        LOG.debug('Creating share: %s.' % dict(share))

        return self.ift_nas.create_share(share, share_server)

    def delete_share(self, context, share, share_server=None):
        """Is called to remove share."""

        LOG.debug('Deleting share: %s.' % dict(share))

        return self.ift_nas.delete_share(share, share_server)

    def get_pool(self, share):
        """Return pool name where the share resides on.

        :param share: The share hosted by the driver.
        """
        return self.ift_nas.get_pool(share)

    def ensure_share(self, context, share, share_server=None):
        """Invoked to ensure that share is exported.

        Driver can use this method to update the list of export locations of
        the share if it changes. To do that, you should return list with
        export locations.

        :return None or list with export locations
        """
        return self.ift_nas.ensure_share(share, share_server)

    def allow_access(self, context, share, access, share_server=None):
        """Allow access to the share."""
        return self.ift_nas.allow_access(share, access, share_server)

    def deny_access(self, context, share, access, share_server=None):
        """Deny access to the share."""
        return self.ift_nas.deny_access(share, access, share_server)

    def manage_existing(self, share, driver_options):
        """Brings an existing share under Manila management.

        If the provided share is not valid, then raise a
        ManageInvalidShare exception, specifying a reason for the failure.

        If the provided share is not in a state that can be managed, such as
        being replicated on the backend, the driver *MUST* raise
        ManageInvalidShare exception with an appropriate message.

        The share has a share_type, and the driver can inspect that and
        compare against the properties of the referenced backend share.
        If they are incompatible, raise a
        ManageExistingShareTypeMismatch, specifying a reason for the failure.

        :param share: Share model
        :param driver_options: Driver-specific options provided by admin.
        :return: share_update dictionary with required key 'size',
                 which should contain size of the share.
        """
        LOG.debug(
            'Manage existing for share: %(share)s, '
            'driver_options: %(driver_options)s, ', {
                'share': dict(share),
                'driver_options': dict(driver_options),
            })
        return self.ift_nas.manage_existing(share, driver_options)

    def unmanage(self, share):
        """Removes the specified share from Manila management.

        Does not delete the underlying backend share.

        For most drivers, this will not need to do anything.  However, some
        drivers might use this call as an opportunity to clean up any
        Manila-specific configuration that they have associated with the
        backend share.

        If provided share cannot be unmanaged, then raise an
        UnmanageInvalidShare exception, specifying a reason for the failure.
        """
        LOG.debug(
            'Unmanage share: %(share)s', {
                'share': dict(share),
            })
        return self.ift_nas.unmanage(share)

    def extend_share(self, share, new_size, share_server=None):
        """Extends size of existing share.

        :param share: Share model
        :param new_size: New size of share (new_size > share['size'])
        :param share_server: Optional -- Share server model
        """
        return self.ift_nas.extend_share(share, new_size, share_server)
