from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
import json
from apps.rodina_app.models import CommonUser
from apps.chats_and_notifications.models import Chat, Message
from api.v1.serializers import ShortCommonUserSerializer


class ChatConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = self.scope.get('common_user')
        self.user_id = str(self.user.id)

    async def websocket_connect(self, message):
        await super().websocket_connect(message)
        await self.change_user_online_status(online_status=True)
        await self.channel_layer.group_add(
                    self.user_id,
                    self.channel_name
                )
        self.groups.append(self.user_id)
        new_messages = await self.user_new_messages_count()
        await self.send(json.dumps({'type': 'information', 'new_messages': new_messages}))

    async def websocket_disconnect(self, message):
        await self.change_user_online_status(online_status=False)
        await super().websocket_disconnect(message)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            bytes_data = bytes()
            text_data = bytes_data.decode("utf-8")
        text_data_json = json.loads(text_data)
        message_text = text_data_json['text']
        receiver_id = str(text_data_json['receiver'])
        if receiver_id != self.user_id:
            sender_serialized_message, receiver_serialized_message = await self.get_user_message(
                message_text=message_text,
                receiver_id=receiver_id
            )
            await self.channel_layer.group_send(
                self.user_id,
                sender_serialized_message
            )
            await self.channel_layer.group_send(
                receiver_id,
                receiver_serialized_message
            )

    @database_sync_to_async
    def change_user_online_status(self, online_status):
        """
        update current user online status via socket
        :param online_status:
        :return:
        """
        self.user.online_status = online_status
        self.user.save(update_fields=('online_status', ))

    @database_sync_to_async
    def user_new_messages_count(self):
        """
        update new messages counter via socket
        :return:
        """
        return self.user.get_new_messages_count()

    @database_sync_to_async
    def get_user_message(self, message_text, receiver_id):
        """
        generate two messages data: for sender and for receiver
        :param message_text:
        :param receiver_id:
        :return:
        """
        receiver = CommonUser.objects.get(id=receiver_id)
        for_message_chat, is_new = Chat.get_or_create(self.user, receiver)

        message_instance = Message.create(
            text=message_text,
            sender=self.user,
            receiver=receiver,
            chat=for_message_chat
        )
        chat_information = {
            'id': for_message_chat.id,
        }
        sender_chat_information = chat_information.copy()
        receiver_chat_information = chat_information.copy()
        sender_chat_information['user'] = ShortCommonUserSerializer(receiver).data
        receiver_chat_information['user'] = ShortCommonUserSerializer(self.user).data
        serialized_message = {
            'type': 'chat_message',
            'message_information': message_instance.to_gifted_chat_dict(),
            'new_chat': is_new
        }

        sender_serialized_message = serialized_message.copy()
        receiver_serialized_message = serialized_message.copy()
        sender_serialized_message['chat_information'] = sender_chat_information
        receiver_serialized_message['chat_information'] = receiver_chat_information
        return sender_serialized_message, receiver_serialized_message

    async def chat_message(self, event):
        """
        Receive message from room group
        :param event:
        :return:
        """
        # Send message to WebSocket
        msg_for_send = json.dumps(event)
        await self.send(msg_for_send)
