# -*- coding: utf-8 -*-
"""Resource class containing all logic for creating, checking, and updating resources."""
import logging
import zipfile
from os import unlink
from os.path import join, splitext
from tempfile import gettempdir
from typing import Optional, List, Tuple, Dict

from hdx.utilities import raisefrom
from hdx.utilities.downloader import Download
from hdx.utilities.loader import load_yaml, load_json
from hdx.utilities.path import script_dir_plus_file
from tabulator import Stream

import hdx.data.dataset
from hdx.data.hdxobject import HDXObject, HDXError
from hdx.hdx_configuration import Configuration

logger = logging.getLogger(__name__)


class Resource(HDXObject):
    """Resource class containing all logic for creating, checking, and updating resources.

    Args:
        initial_data (Optional[Dict]): Initial resource metadata dictionary. Defaults to None.
        configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.
    """

    def __init__(self, initial_data=None, configuration=None):
        # type: (Optional[Dict], Optional[Configuration]) -> None
        if not initial_data:
            initial_data = dict()
        super(Resource, self).__init__(initial_data, configuration=configuration)
        self.file_to_upload = None

    @staticmethod
    def actions():
        # type: () -> Dict[str, str]
        """Dictionary of actions that can be performed on object

        Returns:
            Dict[str, str]: Dictionary of actions that can be performed on object
        """
        return {
            'show': 'resource_show',
            'update': 'resource_update',
            'create': 'resource_create',
            'delete': 'resource_delete',
            'search': 'resource_search',
            'patch': 'resource_patch',
            'datastore_delete': 'datastore_delete',
            'datastore_create': 'datastore_create',
            'datastore_insert': 'datastore_insert',
            'datastore_upsert': 'datastore_upsert'
        }

    def update_from_yaml(self, path=join('config', 'hdx_resource_static.yml')):
        # type: (str) -> None
        """Update resource metadata with static metadata from YAML file

        Args:
            path (Optional[str]): Path to YAML dataset metadata. Defaults to config/hdx_resource_static.yml.

        Returns:
            None
        """
        super(Resource, self).update_from_yaml(path)

    def update_from_json(self, path=join('config', 'hdx_resource_static.json')):
        # type: (str) -> None
        """Update resource metadata with static metadata from JSON file

        Args:
            path (Optional[str]): Path to JSON dataset metadata. Defaults to config/hdx_resource_static.json.

        Returns:
            None
        """
        super(Resource, self).update_from_json(path)

    @staticmethod
    def read_from_hdx(identifier, configuration=None):
        # type: (str, Optional[Configuration]) -> Optional['Resource']
        """Reads the resource given by identifier from HDX and returns Resource object

        Args:
            identifier (str): Identifier of resource
            configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.

        Returns:
            Optional[Resource]: Resource object if successful read, None if not
        """

        resource = Resource(configuration=configuration)
        result = resource._load_from_hdx('resource', identifier)
        if result:
            return resource
        return None

    def get_file_type(self):
        # type: () -> Optional[str]
        """Get the resource's file type

        Returns:
            Optional[str]: Returns the resource's file type or None if it has not been set
        """
        return self.data.get('format')

    def set_file_type(self, file_type):
        # type: (str) -> None
        """Set the resource's file type

        Args:
            file_type (str): resource's file type

        Returns:
            None
        """
        self.data['format'] = file_type.lower()

    def get_file_to_upload(self):
        # type: () -> Optional[str]
        """Get the file uploaded

        Returns:
            Optional[str]: The file that will be or has been uploaded or None if there isn't one
        """
        return self.file_to_upload

    def set_file_to_upload(self, file_to_upload):
        # type: (str) -> None
        """Set the file uploaded to the local path provided

        Args:
            file_to_upload (str): Local path to file to upload

        Returns:
            None
        """
        self.file_to_upload = file_to_upload

    def check_required_fields(self, ignore_fields=list()):
        # type: (List[str]) -> None
        """Check that metadata for resource is complete and add resource_type and url_type if not supplied.
        The parameter ignore_fields should be set if required to any fields that should be ignored for the particular
        operation.

        Args:
            ignore_fields (List[str]): Fields to ignore. Default is [].

        Returns:
            None
        """
        if self.file_to_upload is None:
            if 'url' in self.data:
                if 'resource_type' not in self.data:
                    self.data['resource_type'] = 'api'
                if 'url_type' not in self.data:
                    self.data['url_type'] = 'api'
            else:
                raise HDXError('Either a url or a file to upload must be supplied!')
        else:
            if 'url' not in self.data:
                self.data['url'] = 'ignore'  # must be set even though overwritten
            if 'resource_type' not in self.data:
                self.data['resource_type'] = 'file.upload'
            if 'url_type' not in self.data:
                self.data['url_type'] = 'upload'
            if 'tracking_summary' in self.data:
                del self.data['tracking_summary']
        self._check_required_fields('resource', ignore_fields)

    def update_in_hdx(self):
        # type: () -> None
        """Check if resource exists in HDX and if so, update it

        Returns:
            None
        """
        self._update_in_hdx('resource', 'id', self.file_to_upload)

    def create_in_hdx(self):
        # type: () -> None
        """Check if resource exists in HDX and if so, update it, otherwise create it

        Returns:
            None
        """
        self._create_in_hdx('resource', 'id', 'name', self.file_to_upload)

    def delete_from_hdx(self):
        # type: () -> None
        """Deletes a resource from HDX

        Returns:
            None
        """
        self._delete_from_hdx('resource', 'id')

    def get_dataset(self):
        # type: () -> hdx.data.dataset.Dataset
        """Return dataset containing this resource

        Returns:
            hdx.data.dataset.Dataset: Dataset containing this resource
        """
        package_id = self.data.get('package_id')
        if package_id is None:
            raise HDXError('Resource has no package id!')
        return hdx.data.dataset.Dataset.read_from_hdx(package_id)

    @staticmethod
    def search_in_hdx(query, configuration=None, **kwargs):
        # type: (str, Optional[Configuration], ...) -> List['Resource']
        """Searches for resources in HDX. NOTE: Does not search dataset metadata!

        Args:
            query (str): Query
            configuration (Optional[Configuration]): HDX configuration. Defaults to global configuration.
            **kwargs: See below
            order_by (str): A field on the Resource model that orders the results
            offset (int): Apply an offset to the query
            limit (int): Apply a limit to the query
        Returns:
            List[Resource]: List of resources resulting from query
        """

        resources = []
        resource = Resource(configuration=configuration)
        success, result = resource._read_from_hdx('resource', query, 'query', Resource.actions()['search'])
        if result:
            count = result.get('count', None)
            if count:
                for resourcedict in result['results']:
                    resource = Resource(resourcedict, configuration=configuration)
                    resources.append(resource)
        else:
            logger.debug(result)
        return resources

    def download(self, folder=None):
        # type: (Optional[str]) -> Tuple[str, str]
        """Download resource store to provided folder or temporary folder if no folder supplied

        Args:
            folder (Optional[str]): Folder to download resource to. Defaults to None.

        Returns:
            Tuple[str, str]: (URL downloaded, Path to downloaded file)

        """
        # Download the resource
        url = self.data.get('url', None)
        if not url:
            raise HDXError('No URL to download!')
        logger.debug('Downloading %s' % url)
        with Download() as download:
            path = download.download_file(url, folder)
            return url, path

    def delete_datastore(self):
        # type: () -> None
        """Delete a resource from the HDX datastore

        Returns:
            None
        """
        success, result = self._read_from_hdx('datastore', self.data['id'], 'resource_id',
                                              self.actions()['datastore_delete'],
                                              force=True)
        if not success:
            logger.debug(result)

    def create_datastore(self, schema=None, primary_key=None,
                         delete_first=0, path=None):
        # type: (Optional[List[Dict]], Optional[str], int, Optional[str]) -> None
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX. If no schema is provided
        all fields are assumed to be text. If path is not supplied, the file is first downloaded from HDX.

        Args:
            schema (List[Dict]): List of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}. Defaults to None.
            primary_key (Optional[str]): Primary key of schema. Defaults to None.
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        if delete_first == 0:
            pass
        elif delete_first == 1:
            self.delete_datastore()
        elif delete_first == 2:
            if primary_key is None:
                self.delete_datastore()
        else:
            raise HDXError('delete_first must be 0, 1 or 2! (0 = No, 1 = Yes, 2 = Delete if no primary key)')
        if path is None:
            # Download the resource
            url, path = self.download()
            delete_after_download = True
        else:
            url = self.data.get('url', None)
            if not url:
                raise HDXError('No URL to download!')
            delete_after_download = False

        zip_path = None
        stream = None
        try:
            extension = splitext(path)[1]
            if extension.lower() == '.zip':
                zip_file = zipfile.ZipFile(path)
                filename = zip_file.namelist()[0]
                tempdir = gettempdir()
                zip_file.extract(filename, tempdir)
                zip_path = path
                path = join(tempdir, filename)

            def convert_to_text(extended_rows):
                for number, headers, row in extended_rows:
                    for i, val in enumerate(row):
                        row[i] = str(val)
                    yield (number, headers, row)

            stream = Stream(path, headers=1, post_parse=[convert_to_text], bytes_sample_size=1000000)
            stream.open()
            nonefieldname = False
            if schema is None:
                schema = list()
                for fieldname in stream.headers:
                    if fieldname is not None:
                        schema.append({'id': fieldname, 'type': 'text'})
                    else:
                        nonefieldname = True
            data = {'resource_id': self.data['id'], 'force': True, 'fields': schema, 'primary_key': primary_key}
            self._write_to_hdx('datastore_create', data, 'resource_id')
            if primary_key is None:
                method = 'insert'
            else:
                method = 'upsert'
            logger.debug('Uploading data from %s to datastore' % url)
            offset = 0
            chunksize = 100
            rowset = stream.read(keyed=True, limit=chunksize)
            while len(rowset) != 0:
                if nonefieldname:
                    for row in rowset:
                        del row[None]
                data = {'resource_id': self.data['id'], 'force': True, 'method': method, 'records': rowset}
                self._write_to_hdx('datastore_upsert', data, 'resource_id')
                rowset = stream.read(keyed=True, limit=chunksize)
                logger.debug('Uploading: %s' % offset)
                offset += chunksize
        except Exception as e:
            raisefrom(HDXError, 'Upload to datastore of %s failed!' % url, e)
        finally:
            if stream:
                stream.close()
            if delete_after_download:
                unlink(path)
                if zip_path:
                    unlink(zip_path)
            else:
                if zip_path:
                    unlink(path)  # ie. we keep the zip but remove the extracted file

    def create_datastore_from_dict_schema(self, data, delete_first=0, path=None):
        # type: (dict, int, Optional[str]) -> None
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX from a dictionary
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            data (dict): Dictionary containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        schema = data['schema']
        primary_key = data.get('primary_key')
        self.create_datastore(schema, primary_key, delete_first, path=path)

    def create_datastore_from_yaml_schema(self, yaml_path, delete_first=0,
                                          path=None):
        # type: (str, Optional[int], Optional[str]) -> None
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX from a YAML file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            yaml_path (str): Path to YAML file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        data = load_yaml(yaml_path)
        self.create_datastore_from_dict_schema(data, delete_first, path=path)

    def create_datastore_from_json_schema(self, json_path, delete_first=0, path=None):
        # type: (str, int, Optional[str]) -> None
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX from a JSON file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            json_path (str): Path to JSON file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        data = load_json(json_path)
        self.create_datastore_from_dict_schema(data, delete_first, path=path)

    def create_datastore_for_topline(self, delete_first=0, path=None):
        # type: (int, Optional[str]) -> None
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX using the built in
        YAML definition for a topline. If path is not supplied, the file is first downloaded from HDX.

        Args:
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        data = load_yaml(script_dir_plus_file(join('..', 'hdx_datasource_topline.yml'), Resource))
        self.create_datastore_from_dict_schema(data, delete_first, path=path)

    def update_datastore(self, schema=None, primary_key=None,
                         path=None):
        # type: (Optional[List[Dict]], Optional[str], Optional[str]) -> None
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX. If no schema is provided
        all fields are assumed to be text. If path is not supplied, the file is first downloaded from HDX.

        Args:
            schema (List[Dict]): List of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}. Defaults to None.
            primary_key (Optional[str]): Primary key of schema. Defaults to None.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore(schema, primary_key, 2, path=path)

    def update_datastore_from_dict_schema(self, data, path=None):
        # type: (dict, Optional[str]) -> None
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX from a dictionary
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            data (dict): Dictionary containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_from_dict_schema(data, 2, path=path)

    def update_datastore_from_yaml_schema(self, yaml_path, path=None):
        # type: (str, Optional[str]) -> None
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX from a YAML file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            yaml_path (str): Path to YAML file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_from_yaml_schema(yaml_path, 2, path=path)

    def update_datastore_from_json_schema(self, json_path, path=None):
        # type: (str, Optional[str]) -> None
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX from a JSON file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            json_path (str): Path to JSON file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_from_json_schema(json_path, 2, path=path)

    def update_datastore_for_topline(self, path=None):
        # type: (Optional[str]) -> None
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX using the built in YAML
        definition for a topline. If path is not supplied, the file is first downloaded from HDX.

        Args:
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_for_topline(2, path=path)

    def touch(self):
        # type: () -> None
        """Touch resource

        Returns:
            None
        """
        self._read_from_hdx('resource', self.data['id'], action=self.actions()['patch'])
