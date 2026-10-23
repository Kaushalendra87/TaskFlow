import asyncio
import json
import shutil
import tempfile

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application
from jobs.models import Job
from jobs.services.realtime import send_job_update


User = get_user_model()


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    },
)
class JobConsumerAuthTests(TestCase):
    """
    The consumer reaches the database (it looks up the Job and compares
    owners), so these are TestCase tests rather than SimpleTestCase ones.

    JobConsumer is a synchronous WebsocketConsumer, so database access from
    inside the consumer is safe; only the test body itself is async.
    """

    def setUp(self):
        # Keep uploaded test files out of the real media directory.
        self.media_dir = tempfile.mkdtemp()
        media_override = override_settings(MEDIA_ROOT=self.media_dir)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_dir, True)

        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="TestPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="TestPass123!",
        )
        self.inactive_user = User.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            password="TestPass123!",
            is_active=False,
        )
        self.job = Job.objects.create(
            user=self.owner,
            file=SimpleUploadedFile(
                "test.csv",
                b"col1,col2\nval1,val2\n",
                content_type="text/csv",
            ),
        )

    def token_for(self, user):
        return str(AccessToken.for_user(user))

    async def open_socket(self, token, job_id):
        """
        Connect to the WebSocket route and return the communicator, the
        connection result, and the close code when the connection is refused.
        """
        path = f"/ws/jobs/{job_id}/"
        if token is not None:
            path += f"?token={token}"

        communicator = WebsocketCommunicator(application, path)
        connected, close_code = await communicator.connect()

        return communicator, connected, close_code

    async def drain_connect_messages(self, communicator):
        """
        A successful connection emits the banner followed by the initial
        job.state snapshot. Return both.
        """
        banner = json.loads(await communicator.receive_from(timeout=2))
        state = json.loads(await communicator.receive_from(timeout=2))

        return banner, state

    def test_owner_connects_to_own_job(self):
        async def exercise():
            communicator, connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            try:
                self.assertTrue(connected)

                banner = json.loads(
                    await communicator.receive_from(timeout=2)
                )
                self.assertEqual(banner["type"], "connection")
                self.assertEqual(banner["job_id"], self.job.id)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_initial_job_state_is_sent_after_connection(self):
        self.job.status = Job.Status.PROCESSING
        self.job.progress = 40
        self.job.save(update_fields=["status", "progress"])

        async def exercise():
            communicator, connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            try:
                self.assertTrue(connected)

                _, state = await self.drain_connect_messages(communicator)

                self.assertEqual(state["type"], "job.state")
                self.assertEqual(state["data"]["job_id"], self.job.id)
                self.assertEqual(state["data"]["status"], Job.Status.PROCESSING)
                self.assertEqual(state["data"]["progress"], 40)
                self.assertIn("created_at", state["data"])
                self.assertIn("completed_at", state["data"])
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_reconnect_delivers_latest_persisted_state(self):
        """
        Job state recovery: a client that drops and reconnects must be told
        the current state, not the state from its first connection.
        """
        def connect_and_read_state():
            """Connect, read the state snapshot, then disconnect."""
            async def exercise():
                communicator, connected, _ = await self.open_socket(
                    self.token_for(self.owner),
                    self.job.id,
                )
                try:
                    self.assertTrue(connected)
                    return await self.drain_connect_messages(communicator)
                finally:
                    await communicator.disconnect()

            return async_to_sync(exercise)()

        # First connection sees the initial pending state.
        _, initial = connect_and_read_state()
        self.assertEqual(initial["data"]["status"], Job.Status.PENDING)

        # The job advances while nobody is connected. This runs outside the
        # async block so the ORM call is allowed.
        self.job.status = Job.Status.COMPLETED
        self.job.progress = 100
        self.job.save(update_fields=["status", "progress"])

        # Reconnecting must report the newer persisted state.
        _, recovered = connect_and_read_state()
        self.assertEqual(recovered["type"], "job.state")
        self.assertEqual(recovered["data"]["status"], Job.Status.COMPLETED)
        self.assertEqual(recovered["data"]["progress"], 100)

    def test_ping_is_answered_with_pong(self):
        async def exercise():
            communicator, connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            try:
                self.assertTrue(connected)
                await self.drain_connect_messages(communicator)

                await communicator.send_json_to({"type": "ping"})

                response = json.loads(
                    await communicator.receive_from(timeout=2)
                )
                self.assertEqual(response, {"type": "pong"})
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_unsupported_message_type_returns_error(self):
        async def exercise():
            communicator, connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            try:
                self.assertTrue(connected)
                await self.drain_connect_messages(communicator)

                await communicator.send_json_to({"type": "nonsense"})

                response = json.loads(
                    await communicator.receive_from(timeout=2)
                )
                self.assertEqual(response["type"], "error")
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_update_carries_cancel_requested(self):
        """job.update frames must expose the cancellation flag."""
        # Set the flag in the sync context: a thread would get its own
        # connection and could not see this test's transaction.
        self.job.cancel_requested = True
        self.job.save(update_fields=["cancel_requested"])

        async def exercise():
            communicator, connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            try:
                self.assertTrue(connected)
                await self.drain_connect_messages(communicator)

                await asyncio.to_thread(send_job_update, self.job)

                update = json.loads(
                    await communicator.receive_from(timeout=2)
                )
                self.assertEqual(update["type"], "job.update")
                self.assertEqual(update["data"]["cancel_requested"], True)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_disconnect_removes_client_from_group(self):
        """
        Group cleanup: once the socket closes it must no longer receive
        group broadcasts.
        """
        async def exercise():
            communicator, connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            self.assertTrue(connected)
            await self.drain_connect_messages(communicator)

            # While connected, a group broadcast arrives.
            await asyncio.to_thread(send_job_update, self.job)
            update = json.loads(await communicator.receive_from(timeout=2))
            self.assertEqual(update["type"], "job.update")

            await communicator.disconnect()

            # After disconnecting the consumer is gone, so a further
            # broadcast must not be delivered to it.
            await asyncio.to_thread(send_job_update, self.job)
            await communicator.receive_nothing(timeout=0.1)

        async_to_sync(exercise)()

    def test_anonymous_connection_is_rejected(self):
        async def exercise():
            communicator, connected, close_code = await self.open_socket(
                None,
                self.job.id,
            )
            try:
                self.assertFalse(connected)
                self.assertEqual(close_code, 4001)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_invalid_token_is_rejected(self):
        async def exercise():
            communicator, connected, close_code = await self.open_socket(
                "not-a-valid-jwt",
                self.job.id,
            )
            try:
                self.assertFalse(connected)
                self.assertEqual(close_code, 4001)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_inactive_user_is_rejected(self):
        async def exercise():
            communicator, connected, close_code = await self.open_socket(
                self.token_for(self.inactive_user),
                self.job.id,
            )
            try:
                self.assertFalse(connected)
                self.assertEqual(close_code, 4001)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_other_users_job_is_rejected(self):
        async def exercise():
            communicator, connected, close_code = await self.open_socket(
                self.token_for(self.other_user),
                self.job.id,
            )
            try:
                self.assertFalse(connected)
                self.assertEqual(close_code, 4003)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_missing_job_is_rejected(self):
        async def exercise():
            communicator, connected, close_code = await self.open_socket(
                self.token_for(self.owner),
                self.job.id + 99999,
            )
            try:
                self.assertFalse(connected)
                self.assertEqual(close_code, 4004)
            finally:
                await communicator.disconnect()

        async_to_sync(exercise)()

    def test_update_is_json_and_isolated_to_job_group(self):
        other_job = Job.objects.create(
            user=self.owner,
            file=SimpleUploadedFile(
                "other.csv",
                b"col1,col2\nval1,val2\n",
                content_type="text/csv",
            ),
        )

        async def exercise():
            target, target_connected, _ = await self.open_socket(
                self.token_for(self.owner),
                self.job.id,
            )
            unrelated, unrelated_connected, _ = await self.open_socket(
                self.token_for(self.owner),
                other_job.id,
            )
            try:
                self.assertTrue(target_connected)
                self.assertTrue(unrelated_connected)

                # Drain each connection's banner and initial state snapshot.
                await self.drain_connect_messages(target)
                await self.drain_connect_messages(unrelated)

                await asyncio.to_thread(
                    send_job_update,
                    self.job,
                )

                update = json.loads(
                    await target.receive_from(timeout=2)
                )
                self.assertEqual(
                    update,
                    {
                        "type": "job.update",
                        "data": {
                            "job_id": self.job.id,
                            "status": Job.Status.PENDING,
                            "progress": 0,
                            "error_message": None,
                            "cancel_requested": False,
                        },
                    },
                )

                await unrelated.receive_nothing(timeout=0.05)
            finally:
                await target.disconnect()
                await unrelated.disconnect()

        async_to_sync(exercise)()


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class NotificationWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ws_user",
            email="ws-user@example.com",
            password="TestPassword123!",
        )

        self.access_token = str(
            AccessToken.for_user(self.user)
        )

    async def test_authenticated_user_can_connect(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/?token={self.access_token}",
        )

        connected, _ = await communicator.connect()

        self.assertTrue(connected)

        response = await communicator.receive_json_from()

        self.assertEqual(
            response["type"],
            "connection.established",
        )

        await communicator.disconnect()

    async def test_missing_token_is_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/",
        )

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_invalid_token_is_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/?token=invalid-token",
        )

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_connected_user_receives_notification(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/?token={self.access_token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Consume the connection-established message.
        await communicator.receive_json_from()

        channel_layer = get_channel_layer()

        await channel_layer.group_send(
            f"notifications_user_{self.user.pk}",
            {
                "type": "notification.message",
                "notification": {
                    "id": 1,
                    "title": "Job Completed",
                    "message": "Your job has completed successfully.",
                    "job_id": 10,
                    "event_id": 20,
                    "is_read": False,
                    "created_at": "2026-10-21T10:00:00+00:00",
                },
                "unread_count": 1,
            },
        )

        response = await communicator.receive_json_from()

        self.assertEqual(response["type"], "notification")
        self.assertEqual(
            response["notification"]["title"],
            "Job Completed",
        )
        self.assertEqual(response["unread_count"], 1)

        await communicator.disconnect()


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class JobProgressWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="progress_user",
            email="progress-user@example.com",
            password="TestPassword123!",
        )

        self.token = str(AccessToken.for_user(self.user))

    async def test_authenticated_user_can_connect(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/?token={self.token}",
        )

        connected, _ = await communicator.connect()

        self.assertTrue(connected)

        response = await communicator.receive_json_from()

        self.assertEqual(
            response["type"],
            "connection.established",
        )

        await communicator.disconnect()

    async def test_missing_token_is_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/",
        )

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_invalid_token_is_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/?token=invalid-token",
        )

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_user_receives_job_update(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/?token={self.token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Consume the connection-established message.
        await communicator.receive_json_from()

        channel_layer = get_channel_layer()

        await channel_layer.group_send(
            f"job_updates_user_{self.user.pk}",
            {
                "type": "job.update",
                "data": {
                    "job_id": 42,
                    "event": "progress",
                    "status": "PROCESSING",
                    "progress": 50,
                    "message": "Processing 50% complete.",
                    "updated_at": "2026-10-22T07:00:00+00:00",
                },
            },
        )

        response = await communicator.receive_json_from()

        self.assertEqual(response["type"], "job_update")
        self.assertEqual(response["data"]["job_id"], 42)
        self.assertEqual(response["data"]["progress"], 50)
        self.assertEqual(response["data"]["status"], "PROCESSING")

        await communicator.disconnect()