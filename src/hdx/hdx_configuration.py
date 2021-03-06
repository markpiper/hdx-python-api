# -*- coding: utf-8 -*-
"""Configuration for HDX"""
import six

from hdx.utilities.email import Email
from hdx.utilities.session import get_session

if six.PY2:
    from UserDict import IterableUserDict as UserDict
else:
    from collections import UserDict


import logging
from base64 import b64decode
from os.path import expanduser, join
from typing import Optional

import ckanapi

from hdx.utilities.dictandlist import merge_two_dictionaries
from hdx.utilities.loader import load_yaml, load_json, load_file_to_str
from hdx.utilities.path import script_dir_plus_file

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    pass


class Configuration(UserDict, object):
    """Configuration for HDX

    Args:
        **kwargs: See below
        hdx_site (Optional[str]): HDX site to use eg. prod, test. Defaults to test.
        hdx_read_only (bool): Whether to access HDX in read only mode. Defaults to False.
        hdx_key (Optional[str]): Your HDX key. Ignored if hdx_read_only = True.
        hdx_key_file (Optional[str]): Path to HDX key file. Ignored if hdx_read_only = True or hdx_key supplied. Defaults to ~/.hdxkey.
        hdx_config_dict (dict): HDX configuration dictionary OR
        hdx_config_json (str): Path to JSON HDX configuration OR
        hdx_config_yaml (str): Path to YAML HDX configuration. Defaults to library's internal hdx_configuration.yml.
        project_config_dict (dict): Project configuration dictionary OR
        project_config_json (str): Path to JSON Project configuration OR
        project_config_yaml (str): Path to YAML Project configuration
    """

    _configuration = None
    default_hdx_key_file = join(expanduser('~'), '.hdxkey')

    def __init__(self, **kwargs):
        # type: (...) -> None
        super(Configuration, self).__init__()

        self._remoteckan = None
        self._emailer = None

        hdx_config_found = False
        hdx_config_dict = kwargs.get('hdx_config_dict', None)
        if hdx_config_dict:
            hdx_config_found = True
            logger.info('Loading HDX configuration from dictionary')

        hdx_config_json = kwargs.get('hdx_config_json', '')
        if hdx_config_json:
            if hdx_config_found:
                raise ConfigurationError('More than one HDX configuration given!')
            hdx_config_found = True
            logger.info('Loading HDX configuration from: %s' % hdx_config_json)
            hdx_config_dict = load_json(hdx_config_json)

        hdx_config_yaml = kwargs.get('hdx_config_yaml', '')
        if hdx_config_found:
            if hdx_config_yaml:
                raise ConfigurationError('More than one HDX configuration given!')
        else:
            if not hdx_config_yaml:
                logger.info('No HDX configuration parameter. Using default.')
                hdx_config_yaml = script_dir_plus_file('hdx_configuration.yml', Configuration)
            logger.info('Loading HDX configuration from: %s' % hdx_config_yaml)
            hdx_config_dict = load_yaml(hdx_config_yaml)

        project_config_found = False
        project_config_dict = kwargs.get('project_config_dict', None)
        if project_config_dict is not None:
            project_config_found = True
            logger.info('Loading project configuration from dictionary')

        project_config_json = kwargs.get('project_config_json', '')
        if project_config_json:
            if project_config_found:
                raise ConfigurationError('More than one project configuration given!')
            project_config_found = True
            logger.info('Loading project configuration from: %s' % project_config_json)
            project_config_dict = load_json(project_config_json)

        project_config_yaml = kwargs.get('project_config_yaml', '')
        if project_config_found:
            if project_config_yaml:
                raise ConfigurationError('More than one project configuration given!')
        else:
            if project_config_yaml:
                logger.info('Loading project configuration from: %s' % project_config_yaml)
                project_config_dict = load_yaml(project_config_yaml)
            else:
                project_config_dict = dict()

        self.data = merge_two_dictionaries(hdx_config_dict, project_config_dict)

        self.hdx_read_only = kwargs.get('hdx_read_only', False)
        if not self.hdx_read_only:
            if 'hdx_key' in kwargs:
                self.data['api_key'] = kwargs.get('hdx_key')
            else:
                hdx_key_file = kwargs.get('hdx_key_file', None)
                if not hdx_key_file:
                    logger.info('No HDX key or key file given. Using default key file path.')
                    hdx_key_file = Configuration.default_hdx_key_file
                self.data['api_key'] = self.load_api_key(hdx_key_file)

        self.hdx_site = 'hdx_%s_site' % kwargs.get('hdx_site', 'test')
        if self.hdx_site not in self.data:
            raise ConfigurationError('%s not defined in configuration!' % self.hdx_site)

    def set_read_only(self, read_only=True):
        # type: (bool) -> None
        """
        Set HDX read only flag

        Args:
            read_only (bool): Value to set HDX read only flag. Defaults to True.
        Returns:
            None

        """
        self.hdx_read_only = read_only

    def set_api_key(self, apikey):
        # type: (str) -> None
        """
        Set HDX api key

        Args:
            apikey (str): Value to set api key.
        Returns:
            None

        """
        self.data['api_key'] = apikey

    def get_api_key(self):
        # type: () -> Optional[str]
        """
        Return HDX api key or None if read only

        Returns:
            Optional[str]: HDX api key or None if read only

        """
        if self.hdx_read_only:
            return None
        return self.data['api_key']

    def get_hdx_site_url(self):
        # type: () -> str
        """
        Return HDX web site url

        Returns:
            str: HDX web site url

        """
        return self.data[self.hdx_site]['url']

    def _get_credentials(self):
        # type: () -> tuple
        """
        Return HDX site username and password

        Returns:
            tuple: HDX site username and password

        """
        site = self.data[self.hdx_site]
        username = site['username']
        if username:
            return b64decode(username).decode('utf-8'), b64decode(site['password']).decode('utf-8')
        else:
            return '', ''

    def remoteckan(self):
        # type: () -> ckanapi.RemoteCKAN
        """
        Return the remote CKAN object (see ckanapi library)

        Returns:
            ckanapi.RemoteCKAN: The remote CKAN object

        """
        if self._remoteckan is None:
            raise ConfigurationError('There is no remote CKAN set up! Use Configuration.create(**kwargs)')
        return self._remoteckan

    def call_remoteckan(self, *args, **kwargs):
        # type: (...) -> Dict
        """
        Calls the remote CKAN

        Args:
            *args: Arguments to pass to remote CKAN call_action method
            **kwargs: Keyword arguments to pass to remote CKAN call_action method

        Returns:
            Dict: The response from the remote CKAN call_action method

        """
        requests_kwargs = kwargs.get('requests_kwargs', dict())
        requests_kwargs['auth'] = self._get_credentials()
        kwargs['requests_kwargs'] = requests_kwargs
        apikey = kwargs.get('apikey', self.get_api_key())
        kwargs['apikey'] = apikey
        return self.remoteckan().call_action(*args, **kwargs)

    def create_remoteckan(self, session=get_session(method_whitelist=frozenset(['HEAD', 'TRACE', 'GET', 'POST', 'PUT',
                                                                                'OPTIONS', 'DELETE']))):
        # type: () -> ckanapi.RemoteCKAN
        """
        Create remote CKAN instance from configuration

        Args:
            session: requests Session object to use. Defaults to calling hdx.utilities.session.get_session()

        Returns:
            ckanapi.RemoteCKAN: Remote CKAN instance

        """
        version_file = open(script_dir_plus_file('version.txt', Configuration))
        version = version_file.read().strip()
        return ckanapi.RemoteCKAN(self.get_hdx_site_url(), session=session,
                                  user_agent='HDXPythonLibrary/%s' % version)

    def setup_remoteckan(self, remoteckan=None):
        # type: (Optional[ckanapi.RemoteCKAN]) -> None
        """
        Set up remote CKAN from provided CKAN or by creating from configuration

        Args:
            remoteckan (Optional[ckanapi.RemoteCKAN]): CKAN instance. Defaults to setting one up from configuration.

        Returns:
            None

        """
        if remoteckan is None:
            self._remoteckan = self.create_remoteckan()
        else:
            self._remoteckan = remoteckan

    def emailer(self):
        # type: () -> Email
        """
        Return the Email object (see :any:`Email`)

        Returns:
            Email: The email object

        """
        if self._emailer is None:
            raise ConfigurationError('There is no emailer set up! Use setup_emailer(...)')
        return self._emailer

    def setup_emailer(self, **kwargs):
        # type: (...) -> None
        """
        Set up emailer. Parameters in dictionary or file (eg. yaml below):
        | connection_type: "ssl"   ("ssl" for smtp ssl or "lmtp", otherwise basic smtp is assumed)
        | host: "localhost"
        | port: 123
        | local_hostname: "mycomputer.fqdn.com"
        | timeout: 3
        | username: "user"
        | password: "pass"

        Args:
            **kwargs: See below
            email_config_dict (dict): HDX configuration dictionary OR
            email_config_json (str): Path to JSON HDX configuration OR
            email_config_yaml (str): Path to YAML HDX configuration. Defaults to ~/hdx_email_configuration.yml.

        Returns:
            None
        """
        self._emailer = Email(**kwargs)

    @staticmethod
    def load_api_key(path):
        # type: (str) -> str
        """
        Load HDX api key

        Args:
            path (str): Path to HDX key

        Returns:
            str: HDX api key

        """
        logger.info('Loading HDX api key from: %s' % path)
        apikey = load_file_to_str(path)
        return apikey

    @classmethod
    def read(cls):
        # type: () -> 'Configuration'
        """
        Read the HDX configuration

        Returns:
            Configuration: The HDX configuration

        """
        if cls._configuration is None:
            raise ConfigurationError('There is no HDX configuration! Use Configuration.create(**kwargs)')
        return cls._configuration

    @classmethod
    def setup(cls, configuration=None, **kwargs):
        # type: (Optional['Configuration'], ...) -> None
        """
        Set up the HDX configuration

        Args:
            configuration (Optional[Configuration]): Configuration instance. Defaults to setting one up from passed arguments.
            **kwargs: See below
            hdx_site (Optional[str]): HDX site to use eg. prod, test. Defaults to test.
            hdx_read_only (bool): Whether to access HDX in read only mode. Defaults to False.
            hdx_key (Optional[str]): Your HDX key. Ignored if hdx_read_only = True.
            hdx_key_file (Optional[str]): Path to HDX key file. Ignored if hdx_read_only = True or hdx_key supplied. Defaults to ~/.hdxkey.
            hdx_config_dict (dict): HDX configuration dictionary OR
            hdx_config_json (str): Path to JSON HDX configuration OR
            hdx_config_yaml (str): Path to YAML HDX configuration. Defaults to library's internal hdx_configuration.yml.
            project_config_dict (dict): Project configuration dictionary OR
            project_config_json (str): Path to JSON Project configuration OR
            project_config_yaml (str): Path to YAML Project configuration

        Returns:
            None

        """
        if configuration is None:
            cls._configuration = Configuration(**kwargs)
        else:
            cls._configuration = configuration

    @classmethod
    def _create(cls, configuration=None, remoteckan=None, **kwargs):
        # type: (Optional['Configuration'], Optional[ckanapi.RemoteCKAN], ...) -> str
        """
        Create HDX configuration

        Args:
            configuration (Optional[Configuration]): Configuration instance. Defaults to setting one up from passed arguments.
            remoteckan (Optional[ckanapi.RemoteCKAN]): CKAN instance. Defaults to setting one up from configuration.
            **kwargs: See below
            hdx_site (Optional[str]): HDX site to use eg. prod, test. Defaults to test.
            hdx_read_only (bool): Whether to access HDX in read only mode. Defaults to False.
            hdx_key (Optional[str]): Your HDX key. Ignored if hdx_read_only = True.
            hdx_key_file (Optional[str]): Path to HDX key file. Ignored if hdx_read_only = True or hdx_key supplied. Defaults to ~/.hdxkey.
            hdx_config_dict (dict): HDX configuration dictionary OR
            hdx_config_json (str): Path to JSON HDX configuration OR
            hdx_config_yaml (str): Path to YAML HDX configuration. Defaults to library's internal hdx_configuration.yml.
            project_config_dict (dict): Project configuration dictionary OR
            project_config_json (str): Path to JSON Project configuration OR
            project_config_yaml (str): Path to YAML Project configuration

        Returns:
            str: HDX site url

        """
        cls.setup(configuration, **kwargs)
        cls._configuration.setup_remoteckan(remoteckan)
        return cls._configuration.get_hdx_site_url()

    @classmethod
    def create(cls, configuration=None, remoteckan=None, **kwargs):
        # type: (Optional['Configuration'], Optional[ckanapi.RemoteCKAN], ...) -> str
        """
        Create HDX configuration. Can only be called once (will raise an error if called more than once).

        Args:
            configuration (Optional[Configuration]): Configuration instance. Defaults to setting one up from passed arguments.
            remoteckan (Optional[ckanapi.RemoteCKAN]): CKAN instance. Defaults to setting one up from configuration.
            **kwargs: See below
            hdx_site (Optional[str]): HDX site to use eg. prod, test. Defaults to test.
            hdx_read_only (bool): Whether to access HDX in read only mode. Defaults to False.
            hdx_key (Optional[str]): Your HDX key. Ignored if hdx_read_only = True.
            hdx_key_file (Optional[str]): Path to HDX key file. Ignored if hdx_read_only = True or hdx_key supplied. Defaults to ~/.hdxkey.
            hdx_config_dict (dict): HDX configuration dictionary OR
            hdx_config_json (str): Path to JSON HDX configuration OR
            hdx_config_yaml (str): Path to YAML HDX configuration. Defaults to library's internal hdx_configuration.yml.
            project_config_dict (dict): Project configuration dictionary OR
            project_config_json (str): Path to JSON Project configuration OR
            project_config_yaml (str): Path to YAML Project configuration

        Returns:
            str: HDX site url

        """
        if cls._configuration is not None:
            raise ConfigurationError('Configuration already created!')
        return cls._create(configuration=configuration, remoteckan=remoteckan, **kwargs)

    @classmethod
    def delete(cls):
        # type: () -> None
        """
        Delete global HDX configuration.

        Returns:
            None

        """
        cls._configuration = None
