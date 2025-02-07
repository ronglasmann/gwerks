import urllib.request
import urllib.parse
import json


def slack_send_msg(channel, message, auth_token):

    data = {'token': auth_token, 'channel': channel, 'text': message}
    # r = requests.post("https://slack.com/api/chat.postMessage", data=data)
    resp = _http_post("https://slack.com/api/chat.postMessage", data=data)
    result = json.loads(resp)

    # print(f'{result}')
    if not result['ok']:
        raise Exception("ERROR from Slack api: " + result['error'])

    return result


def _http_post(url, data=None, headers=None):

    if data is None:
        data = {}
    if headers is None:
        headers = {}

    headers['Content-Type'] = 'application/x-www-form-urlencoded'

    data_encoded = urllib.parse.urlencode(data).encode('utf-8')
    print(f"POST: {url} data: {data} headers: {headers}")
    req = urllib.request.Request(url, data=data_encoded, headers=headers, method='POST')

    with urllib.request.urlopen(req) as response:
        response_data = response.read().decode('utf-8')

    print(f"response: {response_data}")
    return response_data
