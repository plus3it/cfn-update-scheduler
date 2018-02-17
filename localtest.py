"""list stacks."""

import boto3
import json

cloudformation = boto3.resource('cloudformation')
client = boto3.client('cloudformation')


def get_stacks():
    """Find stacks that meet requirements."""
    stacksToUpdate = []
    paginator = client.get_paginator('list_stacks')
    response_iterator = paginator.paginate(
      StackStatusFilter=[
        "CREATE_COMPLETE",
        "UPDATE_COMPLETE",
        "ROLLBACK_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE"
        ])
    for page in response_iterator:
        stack = page['StackSummaries']
        for output in stack:
            stack = cloudformation.Stack(output['StackName'])
            keys = [li['Key'] for li in stack.tags]
            if 'MySuperCustomKeyName' in keys:
                stacksToUpdate.append(output['StackName'])

    return stacksToUpdate


def change_toggle(flagged_stack):
    """Change stack update toggle."""
    flagged_stack = cloudformation.Stack(flagged_stack)
    parameterlist = flagged_stack.parameters
    for index, dictionary in enumerate(parameterlist):
        key = dictionary['ParameterKey']
        value = dictionary['ParameterValue']
        if key == 'ForceUpdateToggle' and value == 'B':
            parameterlist[index] = (
             {'ParameterKey': 'ForceUpdateToggle', 'ParameterValue': 'A'})
        elif key == 'ForceUpdateToggle' and value == 'A':
            parameterlist[index] = (
              {'ParameterKey': 'ForceUpdateToggle', 'ParameterValue': 'B'})
        else:
            continue

    return parameterlist


def update_stack(stack_name):
    """Update stack."""
    # skip the update if the stack_name is None
    if not stack_name:
        return
    stack_parameters = change_toggle(stack_name)
    stack = cloudformation.Stack(stack_name)
    kwargs = {
              'StackName': stack_name,
              'UsePreviousTemplate': True,
              'Parameters': stack_parameters,
              'Capabilities': [
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM'
                ],
              'Tags': stack.tags
    }
    # print(kwargs)
    response = client.update_stack(**kwargs)
    return response


def list_check(stack_list):
    """Check if stack_list is a list."""
    if type(stack_list) is list:
        for stackName in stack_list:
            update_stack(stackName)
    else:
        update_stack(stack_list)


update_stack(list_check(get_stacks()))
