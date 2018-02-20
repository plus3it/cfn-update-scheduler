"""Perform unit test on auto-update-cfn-stack.py."""

import mock
import boto3
import os
from moto import mock_events
from ast import literal_eval

# mock env vars before import
mock_env = mock.patch.dict(
  os.environ, {
                'STAGE': 'dev',
                'REGION': 'us-east-1',
                'SERVICE': 'cfn-stack-update',
                'FUNCTION_NAME': 'auto_update_cfn_stack',
                'ACCOUNT_ID': '665544332211'
                }
            )
mock_env.start()

from auto_update_cfn_stack import create_event


@mock_events
def test_create_event():
    """Test create_event."""
    event = boto3.client('events', region_name='us-east-1')
    event_name = "auto-update-{}".format('test-stack')
    event_description = "trigger for {} auto update".format('test-stack')
    test_event = event.put_rule(
                            Name=event_name,
                            ScheduleExpression="rate(5 minutes)",
                            State='ENABLED',
                            Description=event_description
                        )
    test_list = literal_eval("['A','B']")
    test_create_event_instance = create_event('test-stack', 'rate(5 minutes)',
                                              'TestToggleParameter',
                                              test_list)
    # print("test_event: {}".format(test_event))
    # print("test_create_event_instance: {}".format(test_create_event_instance))
    assert test_event == test_create_event_instance


def test_put_targets():
    """Test put_targets."""


def test_lambda_add_resource_policy():
    """Test lambda_add_resource_policy."""


def test_lambda_remove_resource_policy():
    """Test lambda_remove_resource_policy."""


def test_remove_targets():
    """Test remove_targets."""


def test_delete_event():
    """Test delete_event."""


def test_change_toggle():
    """Test change_toggle."""


def test_update_stack():
    """Test update_stack."""


def test_lambda_handler():
    """Test delete_event."""


test_create_event()
