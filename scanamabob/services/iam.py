import boto3
import time

__cache_all_users = {}
__cache_credential_report = {}


def client(context, profile=None):
    ''' Return an IAM client handle for the given context and profile '''
    access_key, secret = context.get_credentials(profile)
    return boto3.client('iam',
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret)


def resources(context, profile=None):
    ''' Return an IAM resource handle for the given context and profile '''
    access_key, secret = context.get_credentials(profile)
    return boto3.resource('iam',
                          aws_access_key_id=access_key,
                          aws_secret_access_key=secret)


def get_all_users(context, profile=None):
    ''' Gets a list of all users. Caches results '''
    # Use cached list if available
    if profile in __cache_all_users:
        return __cache_all_users[profile]

    iam = client(context, profile)

    # Iterate through pages to gather the list of users
    usernames = []
    for page in iam.get_paginator('list_users').paginate(MaxItems=1000):
        for user in page['Users']:
            usernames.append(user['UserName'])

    # Cache result for future requests
    __cache_all_users[profile] = usernames
    return usernames


def get_credential_report(context, profile=None):
    ''' Get the latest credential report from IAM. Caches results '''
    # Use cached report if available
    if profile in __cache_credential_report:
        return __cache_credential_report[profile]

    iam = client(context, profile)

    # Use existing report if one already exists
    try:
        creds_csv = iam.get_credential_report()['Content'].decode('UTF-8')
        __cache_credential_report[profile] = creds_csv
        return creds_csv
    except iam.exceptions.CredentialReportNotPresentException:
        # This is normal when there's no existing report
        pass

    # Generate a new credential report
    report_state = iam.generate_credential_report()['State']

    # Poll for report completion
    generating = report_state != 'COMPLETE'
    while generating:
        time.sleep(0.5)
        report_state = iam.generate_credential_report()['State']
        generating = report_state != 'COMPLETE'

    # Get report CSV
    creds_csv = iam.get_credential_report()['Content'].decode('UTF-8')

    # Cache result for future requests
    __cache_credential_report[profile] = creds_csv
    return creds_csv