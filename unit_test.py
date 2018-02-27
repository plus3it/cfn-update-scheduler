"""Perform unit test on cfn_auto_update_broker.py."""

import zipfile
import io
import mock
import pytest
import boto3
import os
from moto import mock_events, mock_sts, mock_lambda
from ast import literal_eval
import json

# mock env vars before import
mock_env = mock.patch.dict(
  os.environ, {
                'FUNCTION_NAME': 'cfn-update-scheduler-dev-cwe_update_target',
                'REGION': 'us-east-1',
                }
            )
mock_env.start()

from cfn_auto_update_broker import get_lambda_arn, create_event, put_targets, delete_event

mock = mock_sts()
mock.start()
account_id = boto3.client('sts').get_caller_identity().get('Account')
mock.stop()


# TestFunction plagarized from:
# https://github.com/spulec/moto/issues/1338
def _process_lambda(func_str):
    zip_output = io.BytesIO()
    zip_file = zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED)
    zip_file.writestr('lambda_function.py', func_str)
    zip_file.close()
    zip_output.seek(0)
    return zip_output.read()


def get_test_zip_file1():
    """Return test zip file."""
    pfunc = """
def lambda_handler(event, context):
    return event
"""
    return _process_lambda(pfunc)


class TestGetFunction(object):
    """Create mock lambda function."""

    @mock_lambda
    def test_function_response(self):
        """Test that the function is created."""
        # create lambda function in current aws accoint
        client = boto3.client('lambda', region_name='us-east-1')
        self.create_test_function(client)
        # confirm test function exists and validate get_lambda_arn
        lambda_arn = get_lambda_arn('test_function')
        test_arn = self.get_test_function_arn(client)
        assert lambda_arn == test_arn

    @pytest.fixture(scope="session")
    def create_test_function(self, client):
        """Create mock the lambda function."""
        # create function
        response = client.create_function(
            FunctionName='test_function',
            Runtime='python2.7',
            Role='test_role',
            Handler='test_handler',
            Code={
                'ZipFile': get_test_zip_file1(),
            }
        )
        print('response=', response)

    def get_test_function_arn(self, client):
        """Get arn of test function."""
        response = client.get_function(FunctionName='test_function')
        test_arn = response['Configuration']['FunctionArn']
        return test_arn


class TestEventActions(object):
    """Create mock Cloudwatch event."""

    @mock_events
    @pytest.fixture
    def set_up(self):
        """Create event."""
        self.event = boto3.client('events', region_name='us-east-1')
        self.stack_name = 'test-stack'
        self.event_name = "auto-update-{}".format(self.stack_name)
        self.toggle_parameter = 'TestToggleParameter'
        self.toggle_values = literal_eval("['A','B']")
        self.lambda_arn = "arn:aws:lambda:us-east-1:123456789012:function:test_function:$LATEST"

    @pytest.fixture
    def local_event(self, set_up):
        """Create a local test event to validate against."""
        event_description = "trigger for {} auto update".format('test-stack')
        response = self.event.put_rule(
                                Name='auto-update-test-stack',
                                ScheduleExpression="rate(5 minutes)",
                                State='ENABLED',
                                Description=event_description
                            )
        return response

    def test_create_event(self, set_up):
        """Test cfn_auto_update_broker create_event."""
        response = create_event('test-stack', 'rate(5 minutes)',
                                'TestToggleParameter', self.toggle_values)
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200

    def test_put_targets(self, local_event):
        """Test put_targets."""
        response = put_targets(self.stack_name,
                               self.lambda_arn,
                               self.toggle_parameter,
                               self.toggle_values)
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200

    def test_delete_event(self, set_up):
        """Test delete_event."""
        response = delete_event(self.stack_name)
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200


def test_lambda_add_resource_policy():
    """Test lambda_add_resource_policy."""


def test_lambda_remove_resource_policy():
    """Test lambda_remove_resource_policy."""


def test_change_toggle():
    """Test change_toggle."""


def test_update_stack():
    """Test update_stack."""


def test_lambda_handler():
    """Test delete_event."""
