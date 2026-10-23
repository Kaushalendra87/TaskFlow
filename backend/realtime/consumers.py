import json

from django.contrib.auth.models import AnonymousUser

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer, WebsocketConsumer

from jobs.models import Job
from jobs.services.realtime import job_group_name


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Authenticated WebSocket connection for notifications and
    real-time job progress updates.
    """

    async def connect(self):
        user = self.scope.get("user")

        if (
            user is None
            or isinstance(user, AnonymousUser)
            or not user.is_authenticated
            or not user.is_active
        ):
            await self.close(code=4401)
            return

        self.user_id = user.pk

        self.notification_group_name = (
            f"notifications_user_{self.user_id}"
        )

        self.job_updates_group_name = (
            f"job_updates_user_{self.user_id}"
        )

        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name,
        )

        await self.channel_layer.group_add(
            self.job_updates_group_name,
            self.channel_name,
        )

        await self.accept()

        await self.send_json(
            {
                "type": "connection.established",
                "message": (
                    "Connected to TaskFlow notifications "
                    "and job updates."
                ),
            }
        )

    async def disconnect(self, close_code):
        notification_group = getattr(
            self,
            "notification_group_name",
            None,
        )

        job_updates_group = getattr(
            self,
            "job_updates_group_name",
            None,
        )

        if notification_group:
            await self.channel_layer.group_discard(
                notification_group,
                self.channel_name,
            )

        if job_updates_group:
            await self.channel_layer.group_discard(
                job_updates_group,
                self.channel_name,
            )

    async def receive_json(self, content, **kwargs):
        """
        Accept a simple ping for connection checks.
        Clients cannot choose groups or publish job updates.
        """

        if content.get("action") == "ping":
            await self.send_json(
                {
                    "type": "pong",
                }
            )
            return

        await self.send_json(
            {
                "type": "error",
                "message": "Unsupported WebSocket action.",
            }
        )

    async def notification_message(self, event):
        """
        Handle messages sent to notifications_user_<user_id>.
        """

        await self.send_json(
            {
                "type": "notification",
                "notification": event["notification"],
                "unread_count": event["unread_count"],
            }
        )

    async def job_update(self, event):
        """
        Handle messages sent to job_updates_user_<user_id>.
        """

        await self.send_json(
            {
                "type": "job_update",
                "data": event["data"],
            }
        )


class JobConsumer(WebsocketConsumer):

    def connect(self):

        user = self.scope.get("user")

        if not user or user.is_anonymous:
            self.close(code=4001)
            return

        self.job_id =  self.scope["url_route"]["kwargs"]["job_id"]

        try:
            self.job = Job.objects.get(
                id = self.job_id,
            )

        except Job.DoesNotExist:
            self.close(code=4004)
            return

        if self.job.user_id != user.id:
            self.close(code=4003)
            return
        

        self.room_group_name = job_group_name(self.job_id)

        async_to_sync(
            self.channel_layer.group_add
        )(
            self.room_group_name,
            self.channel_name,
        )

        self.accept()

        self.send(
            text_data=json.dumps(
                {
                    "type": "connection",
                    "message": f"Connected to Job {self.job_id}",
                    "job_id": int(self.job_id),
                }
            )
        )

        self.job.refresh_from_db()

        self.send_job_state(
            message_type="job.state",
        )

    def receive(
            self,
            text_data=None,
            bytes_data=None,
    ):
        """
        Handle client heartbeat messages.

        Expsected JSON:
        {"type": "ping"}
        """

        if not text_data:
            return

        try:
            message = json.loads(text_data)
        except json.JsonDecodeError:
            self.send_json({
                "type": "error",
                "message": "Invalid JSON message"
            })
            return

        message_type = message.get("type")

        if message_type == "ping":
            self.send_json({
                "type":"pong",
            })

        else:
            self.send_json({
                "type":"error",
                "message":"Unsupported message type",
            })
            

    def job_update(self, event):

        self.send(
            text_data=json.dumps(
                {
                    "type": "job.update",
                    "data": {
                        "job_id": event["job_id"],
                        "status": event["status"],
                        "progress": event["progress"],
                        "error_message": event[
                            "error_message"
                        ],
                        "cancel_requested": event.get(
                            "cancel_requested",
                            False,
                        ),
                    },
                }
            )
        )

    def send_job_state(self, message_type):
        """
        Send the latest persisted job state.
        """

        self.send_json({
            "type": message_type,
            "data":{
                "job_id":self.job.id,
                "status":self.job.status,
                "progress":self.job.progress,
                "error_message":self.job.error_message,
                "created_at":self.job.created_at.isoformat(),
                "completed_at":(
                    self.job.completed_at.isoformat()
                    if self.job.completed_at
                    else None
                ),
            },
        })

    def send_json(self,data):
        """
        Serialize Python data into a JSON Websocket message.
        """

        self.send(
            text_data= json.dumps(data),
        )

    def disconnect(self, close_code):

        # Only discard connections that joined a group.
        if hasattr(self, "room_group_name"):

            async_to_sync(
                self.channel_layer.group_discard
            )(
                self.room_group_name,
                self.channel_name,
            )