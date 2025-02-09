import json

from gwerks import http_post


def slack_send_msg(channel, message, auth_token):

    data = {'token': auth_token, 'channel': channel, 'text': message}
    # r = requests.post("https://slack.com/api/chat.postMessage", data=data)
    resp = http_post("https://slack.com/api/chat.postMessage", data=data)
    result = json.loads(resp)

    # print(f'{result}')
    if not result['ok']:
        raise Exception("ERROR from Slack api: " + result['error'])

    return result



