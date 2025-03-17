import json

from gwerks import http_post
from gwerks.util.sys import exec_cmd
from gwerks.packaging import VCS


class GitHub(VCS):
    def __init__(self, auth_token):
        super().__init__()
        self._auth_token = auth_token
        self._remote_origin_url = exec_cmd("git config --get remote.origin.url")

        url_parts = self._remote_origin_url.split("/")
        self._owner = url_parts[3]
        self._repo = url_parts[4][:-5]

    def get_remote_origin_url(self):
        return self._remote_origin_url

    def release_create(self, version):
        headers = {'Authorization': f'Bearer {self._auth_token}',
                   'X-GitHub-Api-Version': '2022-11-28',
                   'Content-Type': 'application/json'}
        data = {
            'tag_name': f'v{version}',
            # 'name': f'v{pkg.get_version()}',
            # 'body': f'v{pkg.get_version()}',
            # 'target_commitish': 'main'
        }
        data_bytes = json.dumps(data).encode('utf-8')
        http_post(f'https://api.github.com/repos/{self._owner}/{self._repo}/releases', data=data_bytes, headers=headers)

    # def repos(self):
    #
    #     headers = {'Authorization': f'token {self._auth_token}'}
    #     response_str = http_get('https://api.github.com/user/repos', headers=headers)
    #     repos = json.loads(response_str)
    #     for repo in repos:
    #         print(repo['name'])
