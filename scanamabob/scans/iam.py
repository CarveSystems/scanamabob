import time
import boto3
from scanamabob.scans import Finding, Scan, ScanSet

iam = boto3.client('iam')
resources = boto3.resource('iam')


def _get_usernames():
    ''' Gets a list of users, caching the result '''
    usernames = []
    # TODO properly handle pagination
    for page in iam.get_paginator('list_users').paginate(MaxItems=1000):
        for user in page['Users']:
            usernames.append(user['UserName'])
    return usernames


class MfaScan(Scan):
    title = 'AWS users without Multi-Factor Authentication'
    permissions = ['iam:ListUsers', 'iam:ListMFADevices',
                   'iam:GetLoginProfile']

    def run(self):
        usernames = _get_usernames()
        users_without_mfa = []

        for username in usernames:
            user = resources.User(username)

            # Determine if user has a login profile
            try:
                profile = iam.get_login_profile(UserName=username)
            except iam.exceptions.NoSuchEntityException:
                # This user does not have access to the AWS Console
                continue
            except Exception as err:
                print(f'ERROR: {err}')
                continue

            # Check if user has any MFA devices registered
            mfa_devices = list(user.mfa_devices.all())
            if len(mfa_devices) < 1:
                users_without_mfa.append(username)

        # If any users have a login profile, but no MFA, generate a finding
        if len(users_without_mfa):
            finding = Finding('iam_mfa', self.title, 'HIGH', users=users_without_mfa)
            return [finding]

        return []


class CredentialReport(Scan):
    title = 'AWS Account has an enabled Root Access Key'
    permissions = ['iam:GenerateCredentialReport', 'iam:GetCredentialReport']

    def run(self):
        report_state = iam.generate_credential_report()['State']
        generating = report_state != 'COMPLETE'
        while generating:
            time.sleep(0.25)
            report_state = iam.generate_credential_report()['State']
            generating = report_state != 'COMPLETE'
        creds_csv = iam.get_credential_report()['Content'].decode('UTF-8')
        for row in creds_csv.split('\n')[1:]:
            col = row.split(',')
            user = col[0]
            if user == '<root_account>':
                key1 = col[8]
                key2 = col[13]
                if key1 == 'true' or key2 == 'true':
                    return [Finding('iam_rootkey', self.title, 'HIGH')]
        return []


class PasswordPolicy(Scan):
    title = 'Checking AWS account password policies'
    permissions = ['iam:GetAccountPasswordPolicy']

    def run(self):
        try:
            policy = resources.AccountPasswordPolicy()
            policy.load()
        except iam.exceptions.NoSuchEntityException:
            return [Finding('iam_no_passpol',
                            'No AWS account-level password policy', 'MEDIUM')]
        # TODO define and add findings for weak password policies
        return []


scans = ScanSet('IAM Scans',
                MfaScan(),
                CredentialReport(),
                PasswordPolicy())