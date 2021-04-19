from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import google_auth_oauthlib.flow
from streamer import Streamer
import json
import pickle
import os
import pytchat
with open('client_secret.json', 'r') as f:
    file = json.load(f)
    CLIENT_ID = file["installed"]["client_id"]
    CLIENT_SECRET = file["installed"]["client_secret"]
    API_KEY = file["installed"]["api_key"]
    CLIENT_SECRET_FILE = 'client_secret.json'


class YTBot:
    def __init__(self):
        self.yt = self.youtube_auth()

        # Список всех стримеров, которые используют бота
        self.streamers = self._loadStreamersFromPickles()

    def youtube_auth(self):
        """Полноценная авторизация бота и консервирование его данных"""
        creds = None
        if os.path.isfile('creds/core/ytbot_build.pickle'):
            with open('creds/core/ytbot_build.pickle', 'rb') as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                scope = ["https://www.googleapis.com/auth/youtube"]
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, scope)
                creds = flow.run_console()
            # Консервируем данные на потом
            with open('creds/core/ytbot_build.pickle', 'wb') as f:
                pickle.dump(creds, f)

        return build('youtube', 'v3', credentials=creds, developerKey=API_KEY)

    # !!!DO NOT USE
    # Квота сгорит к чертям за несколько секунд, 10.000 units per day
    # Quick quota exceed!!!
    # def listen(self):
    #     """Эта функция постоянно возвращает сообщения из всех активных чатов"""
    #     page_tokens = dict()
    #     for streamer in self.streamers:
    #         page_tokens[streamer.liveChatId] = None
    #
    #     while True:
    #         for liveChatId, nextPageToken in page_tokens.items():
    #             response = self.listMessages(liveChatId=liveChatId, nextPageToken=nextPageToken)
    #
    #             page_tokens[liveChatId] = response["nextPageToken"]
    #             if response["items"]:
    #                 yield response["items"]

    def listen(self):
        chats = dict()
        broadcast_to_chat = dict()
        for streamer in self.streamers:
            chats[streamer.liveBroadcastId] = pytchat.create(video_id=streamer.liveBroadcastId)
            broadcast_to_chat[streamer.liveBroadcastId] = streamer.liveChatId
        while True:
            for liveBroadcastId, chat in chats.items():
                if chat.is_alive():
                    for c in chat.get().sync_items():
                        yield c, broadcast_to_chat[liveBroadcastId]

    def listMessages(self, liveChatId: str, nextPageToken=None):
        """:liveChatId: - id чата, куда бот отправит сообщение,
           :nextPageToken: - этот токен позволяет отсечь уже проверенные сообщения"""
        try:
            if nextPageToken is None:
                request = self.yt.liveChatMessages().list(
                    liveChatId=liveChatId,
                    part='snippet'
                )
            else:
                request = self.yt.liveChatMessages().list(
                    liveChatId=liveChatId,
                    part='snippet',
                    pageToken=nextPageToken
                )
            response = request.execute()
            return response
        except Exception as e:
            print(f'Error from YTBot.listMessages(): {e.__class__.__name__} {e}')

    def deleteMessage(self, id: str):
        """:id: - id сообщения, которое нужно удалить"""
        try:
            request = self.yt.liveChatMessages().delete(
                id=id
            )
            response = request.execute()
            return response
        except Exception as e:
            print(f'Error from YTBot.deleteMessage(): {e.__class__.__name__} {e}')

    def sendMessage(self, text: str, liveChatId: str):
        """:text: - Текст сообщения
           :liveChatId: - id чата, куда бот отправит сообщение"""
        request_body = {
            "snippet": {
                "liveChatId": liveChatId,
                "type": "textMessageEvent",
                "textMessageDetails": {
                    "messageText": text
                }
            }
        }
        try:
            request = self.yt.liveChatMessages().insert(
                part='snippet',
                body=request_body
            )
            response = request.execute()
            return response
        except Exception as e:
            print(f'Error from YTBot.sendMessage(): {e.__class__.__name__} {e}')

    def _loadStreamersFromPickles(self):
        """Эта функция создаёт авторизованные сессии всех стримеров,
        которые есть в системе, а после возвращает их список.
        Загрузка идёт из файлов pickle"""

        with open('db/db.json', encoding='UTF-8') as f:
            streamers_ids = json.load(f)

        streamers_sessions = []
        for id in streamers_ids['streamers']:
            streamers_sessions.append(Streamer(id))
        return streamers_sessions

    def unbanUser(self, liveChatBanId: str):
        """:liveChatBanId: - id объекта блокировки. Не путать с id чата и id человека!
           Каждому бану Ютуб присваивает уникальный id для его отслеживания.

           id объекта блокировки можно получить из объекта, который возвращается при вызове
           функции YTBot.banUser() по ключам {'id': liveChatBanId}"""
        try:
            request = self.yt.liveChatBans().delete(
                id=liveChatBanId
            )
            request.execute()  # разбан не возвращает объектов
        except Exception as e:
            print(f'Error from YTBot.unbanUser(): {e.__class__.__name__} {e}')

    def banUser(self, liveChatId: str, userToBanId: str, duration=300, temp=False):
        """:liveChatId: - id чата, где нужно заблокировать человека
           :userToBanId: - id человека, которого нужно заблокировать
           :temp: - вид блокировки, если temp == True - временная блокировка, иначе навсегда
           :duration: - длительность временной блокировки в секундах

           Функция для блокировки человека в чате, доступна только при наличии у бота прав модератора."""
        request_body = {
            'snippet': {
                'liveChatId': liveChatId,
                'bannedUserDetails': {
                    'channelId': userToBanId
                }
            }
        }

        if not temp:
            request_body['snippet']['type'] = 'permanent'
        else:
            request_body['snippet']['type'] = 'temporary'
            request_body['snippet']['banDurationSeconds'] = int(duration)

        try:
            request = self.yt.liveChatBans().insert(
                part='snippet',
                body=request_body
            )
            response = request.execute()  # Объект liveChatBans, здесь важно достать id бана

            liveChatBan_id = response['id']
            # !!!
            # sql work, save ban id to delete it later
            # key: userToBan; values: liveChatBan_id
            # !!!
            return response
        except Exception as e:
            print(f'Error from YTBot.banUser(): {e.__class__.__name__} {e}')
